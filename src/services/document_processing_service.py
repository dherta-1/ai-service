"""Document extraction flow service."""

from __future__ import annotations

import asyncio
import io
import logging
import os
import uuid
from pathlib import Path
from typing import Any, Optional

import fitz
from PIL import Image

from src.ocr.dtos import OCRImageRequest

logger = logging.getLogger(__name__)


class DocumentProcessingService:
    """Process uploaded documents into structured exam JSON."""

    def __init__(self, ocr_client, s3_client, s3_bucket: Optional[str] = None):
        self.ocr_client = ocr_client
        self.s3_client = s3_client
        self.s3_bucket = s3_bucket
        self.output_dir = Path("output")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def process_document(
        self,
        local_file_path: str,
        original_filename: str,
        s3_bucket: Optional[str] = None,
        s3_prefix: str = "document-extraction",
    ) -> dict[str, Any]:
        """Main flow: open file, render pages, run OCR, and crop image blocks."""
        file_id = str(uuid.uuid4())
        file_path = Path(local_file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"Uploaded file not found: {local_file_path}")

        bucket = s3_bucket or self.s3_bucket
        if bucket:
            key = f"{s3_prefix}/{file_id}/input/{original_filename}"
            self.s3_client.upload_file(str(file_path), bucket, key)

        doc = fitz.open(str(file_path))
        all_exam_data: list[dict[str, Any]] = []
        crops: list[dict[str, Any]] = []

        try:
            # Render all pages to image files for OCR processing.
            page_image_paths: list[Path] = []
            for page_index in range(doc.page_count):
                page = doc[page_index]
                image_path = self._render_page_to_image(file_id, page_index, page)
                page_image_paths.append(image_path)

            crop_dir = self.output_dir / file_id / "crops"
            crop_dir.mkdir(parents=True, exist_ok=True)

            for page_index, image_path in enumerate(page_image_paths):
                page_items = await self._extract_page_with_ocr(image_path, page_index)
                all_exam_data.extend(page_items)

                image_items = [item for item in page_items if item["content_type"] == "image"]
                for image_idx, item in enumerate(image_items, start=1):
                    bbox = item.get("bbox")
                    if not self._is_valid_box(bbox):
                        continue

                    crop_path = self._crop_image_region(
                        image_path=image_path,
                        bbox=bbox,
                        crop_dir=crop_dir,
                        page_index=page_index,
                        item_index=image_idx,
                    )
                    if not crop_path:
                        continue

                    item["illustration_local_path"] = str(crop_path)
                    crop_meta = {
                        "page_number": page_index + 1,
                        "path": str(crop_path),
                    }

                    if bucket:
                        key = f"{s3_prefix}/{file_id}/crops/{crop_path.name}"
                        self.s3_client.upload_file(str(crop_path), bucket, key)
                        item["illustration_s3_key"] = key
                        crop_meta["s3_key"] = key

                    crops.append(crop_meta)

            return {
                "file_id": file_id,
                "filename": original_filename,
                "exam_data": all_exam_data,
                "crops": crops,
            }
        finally:
            doc.close()

    def _render_page_to_image(self, file_id: str, page_index: int, page: fitz.Page) -> Path:
        """Render a PDF page to PIL image and save locally."""
        # Use 2x scaling for better OCR quality
        matrix = fitz.Matrix(2.0, 2.0)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        pil_image = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")

        image_dir = self.output_dir / file_id / "pages"
        image_dir.mkdir(parents=True, exist_ok=True)
        image_path = image_dir / f"page_{page_index + 1}.png"
        pil_image.save(image_path, format="PNG")
        return image_path

    async def _extract_page_with_ocr(
        self, image_path: Path, page_index: int
    ) -> list[dict[str, Any]]:
        """Extract OCR blocks from a rendered page image."""
        request = OCRImageRequest(image_path=image_path)
        ocr_result = await asyncio.to_thread(self.ocr_client.extract, request)

        page_items: list[dict[str, Any]] = []
        for page in ocr_result.pages:
            for item in page.items:
                page_items.append(
                    {
                        "page_number": page_index + 1,
                        "bbox": {
                            "x1": item.bbox.x1,
                            "y1": item.bbox.y1,
                            "x2": item.bbox.x2,
                            "y2": item.bbox.y2,
                        },
                        "content": item.content,
                        "content_type": item.content_type,
                        "accuracy": float(item.accuracy),
                    }
                )

        logger.info(
            "OCR extracted %s blocks for page %s",
            len(page_items),
            page_index + 1,
        )
        return page_items

    def _crop_image_region(
        self,
        image_path: Path,
        bbox: dict[str, Any],
        crop_dir: Path,
        page_index: int,
        item_index: int,
    ) -> Optional[Path]:
        """Crop image region from page image using pixel-space bbox."""
        x1 = max(0, int(float(bbox.get("x1", 0))))
        y1 = max(0, int(float(bbox.get("y1", 0))))
        x2 = max(0, int(float(bbox.get("x2", 0))))
        y2 = max(0, int(float(bbox.get("y2", 0))))
        if x2 <= x1 or y2 <= y1:
            return None

        with Image.open(image_path) as page_image:
            width, height = page_image.size
            x1 = min(x1, width)
            y1 = min(y1, height)
            x2 = min(x2, width)
            y2 = min(y2, height)
            if x2 <= x1 or y2 <= y1:
                return None

            crop = page_image.crop((x1, y1, x2, y2))
            crop_path = crop_dir / f"crop_p{page_index + 1}_{item_index}.png"
            crop.save(crop_path, format="PNG")
            return crop_path

    @staticmethod
    def _is_valid_box(box: Any) -> bool:
        if not isinstance(box, dict):
            return False
        required = ("x1", "y1", "x2", "y2")
        return all(k in box and box[k] is not None for k in required)
