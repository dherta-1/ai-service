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

from src.shared.utils.json_normalize import extract_json_object, normalize_exam_payload
from src.prompts.document_extraction import document_extraction_prompt

logger = logging.getLogger(__name__)


class DocumentProcessingService:
    """Process uploaded documents into structured exam JSON."""

    def __init__(self, llm_client, s3_client, s3_bucket: Optional[str] = None):
        self.llm_client = llm_client
        self.s3_client = s3_client
        self.s3_bucket = s3_bucket
        self.output_dir = Path("output")
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.extraction_prompt = document_extraction_prompt

    async def process_document(
        self,
        local_file_path: str,
        original_filename: str,
        s3_bucket: Optional[str] = None,
        s3_prefix: str = "document-extraction",
    ) -> dict[str, Any]:
        """Main flow: open file, render pages, call LLM concurrently, merge JSON, crop figures."""
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
            # Render all pages and extract LLM data concurrently
            page_tasks = []
            for page_index in range(doc.page_count):
                page = doc[page_index]
                image_path, pil_image = self._render_page_to_image(
                    file_id, page_index, page
                )
                task = self._extract_page_with_llm(image_path, pil_image, page_index)
                page_tasks.append(task)

            # Run all LLM extractions concurrently
            llm_results = await asyncio.gather(*page_tasks)

            # Merge results from all pages
            for page_index, llm_json in enumerate(llm_results):
                for item in llm_json.get("exam_data", []):
                    if isinstance(item, dict):
                        item["page_number"] = page_index + 1
                        all_exam_data.append(item)

            crop_dir = self.output_dir / file_id / "crops"
            crop_dir.mkdir(parents=True, exist_ok=True)
            for idx, item in enumerate(all_exam_data):
                box = item.get("illustration_box")
                page_number = int(item.get("page_number", 1))
                if not self._is_valid_box(box):
                    continue

                crop_path = self._crop_illustration(
                    doc, page_number - 1, box, crop_dir, idx
                )
                if crop_path:
                    item["illustration_local_path"] = str(crop_path)
                    crops.append(
                        {
                            "question_number": item.get("question_number", ""),
                            "page_number": page_number,
                            "path": str(crop_path),
                        }
                    )

                    if s3_bucket:
                        key = f"{s3_prefix}/{file_id}/crops/{crop_path.name}"
                        self.s3_client.upload_file(str(crop_path), s3_bucket, key)
                        item["illustration_s3_key"] = key

            return {
                "file_id": file_id,
                "filename": original_filename,
                "exam_data": all_exam_data,
                "crops": crops,
            }
        finally:
            doc.close()

    def _render_page_to_image(
        self, file_id: str, page_index: int, page: fitz.Page
    ) -> tuple[Path, Image.Image]:
        """Render a PDF page to PIL image and save locally."""
        # Use 2x scaling for better OCR quality
        matrix = fitz.Matrix(2.0, 2.0)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        pil_image = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")

        image_dir = self.output_dir / file_id / "pages"
        image_dir.mkdir(parents=True, exist_ok=True)
        image_path = image_dir / f"page_{page_index + 1}.png"
        pil_image.save(image_path, format="PNG")
        return image_path, pil_image

    async def _extract_page_with_llm(
        self, image_path: Path, pil_image: Image.Image, page_index: int
    ) -> dict[str, Any]:
        """Call LLM using page image and normalize JSON payload (async)."""
        _ = pil_image  # image object is created and available for providers that can use direct image inputs

        raw = self.llm_client.generate_file(
            file_path=str(image_path),
            prompt=self.extraction_prompt,
        )

        logger.debug(f"LLM raw response for page {page_index + 1}: {raw[:500]}")

        parsed = extract_json_object(raw)
        return normalize_exam_payload(parsed)

    def _crop_illustration(
        self,
        doc: fitz.Document,
        page_index: int,
        box: dict[str, Any],
        crop_dir: Path,
        item_index: int,
    ) -> Optional[Path]:
        """Crop illustration based on 0-1000 normalized box and save file."""
        page = doc[page_index]
        page_rect = page.rect

        x1 = self._clamp_0_1000(box.get("x1"))
        y1 = self._clamp_0_1000(box.get("y1"))
        x2 = self._clamp_0_1000(box.get("x2"))
        y2 = self._clamp_0_1000(box.get("y2"))
        if x2 <= x1 or y2 <= y1:
            return None

        rect = fitz.Rect(
            page_rect.x0 + (x1 / 1000.0) * page_rect.width,
            page_rect.y0 + (y1 / 1000.0) * page_rect.height,
            page_rect.x0 + (x2 / 1000.0) * page_rect.width,
            page_rect.y0 + (y2 / 1000.0) * page_rect.height,
        )

        pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0), clip=rect, alpha=False)
        crop_path = crop_dir / f"crop_p{page_index + 1}_{item_index + 1}.png"
        pix.save(str(crop_path))
        return crop_path

    @staticmethod
    def _clamp_0_1000(value: Any) -> int:
        try:
            num = int(float(value))
        except (TypeError, ValueError):
            num = 0
        return max(0, min(1000, num))

    @staticmethod
    def _is_valid_box(box: Any) -> bool:
        if not isinstance(box, dict):
            return False
        required = ("x1", "y1", "x2", "y2")
        return all(k in box and box[k] is not None for k in required)
