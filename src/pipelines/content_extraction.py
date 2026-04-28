from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Callable, Optional, TypedDict

from PIL import Image

from src.ocr.dtos import OCRImageRequest
from src.shared.base.base_pipeline import BasePipeline
from src.shared.helpers.debug_export import export_pipeline_debug

logger = logging.getLogger(__name__)


class ContentExtractionInput(TypedDict):
    image_path: Path
    page_index: int
    crop_dir: Path
    file_id: str
    s3_prefix: str
    bucket: Optional[str]
    # Optional callback: (object_key, name, size, mime_type) -> file_metadata_id str
    on_image_saved: Optional[Callable[[str, str, int, str], str]]


class ContentExtractionOutput(TypedDict):
    page_number: int
    markdown_content: str
    # Maps S3 object key -> file_metadata id for images saved this page
    image_file_ids: dict[str, str]


class ContentExtractionPipeline(
    BasePipeline[ContentExtractionInput, ContentExtractionOutput]
):
    """Extract OCR page content and build merged markdown output."""

    def __init__(self, ocr_client, s3_client):
        self.ocr_client = ocr_client
        self.s3_client = s3_client

    def validate(self, payload: ContentExtractionInput) -> None:
        image_path = payload.get("image_path")
        if not isinstance(image_path, Path) or not image_path.exists():
            raise FileNotFoundError(f"Image path not found: {image_path}")

    def postprocess(self, result: ContentExtractionOutput) -> ContentExtractionOutput:
        """Validate output structure before returning."""
        if not isinstance(result, dict):
            logger.error(
                f"ContentExtractionPipeline postprocess: Invalid result type {type(result)}"
            )
            return {"page_number": 0, "markdown_content": ""}

        if "page_number" not in result or "markdown_content" not in result:
            logger.error(
                f"ContentExtractionPipeline postprocess: Missing required keys. Got: {list(result.keys())}"
            )
            return {"page_number": result.get("page_number", 0), "markdown_content": ""}

        return result

    async def process(self, payload: ContentExtractionInput) -> ContentExtractionOutput:
        image_path = payload["image_path"]
        page_index = payload["page_index"]
        crop_dir = payload["crop_dir"]
        file_id = payload["file_id"]
        s3_prefix = payload["s3_prefix"]
        bucket = payload["bucket"]
        on_image_saved: Optional[Callable[[str, str, int, str], str]] = payload.get(
            "on_image_saved"
        )

        export_pipeline_debug(
            "content_extraction",
            "input",
            {
                "image_path": str(image_path),
                "page_index": page_index,
                "file_id": file_id,
            },
            page_index + 1,
        )

        page_items = await self._extract_page_with_ocr(image_path, page_index)

        image_file_ids: dict[str, str] = {}
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

            if bucket:
                key = f"{s3_prefix}/{file_id}/crops/{crop_path.name}"
                self.s3_client.upload_file(str(crop_path), bucket, key)
                item["illustration_s3_key"] = key

                # Register in file_metadata and get back a stable file id
                if on_image_saved:
                    size = crop_path.stat().st_size
                    fm_id = on_image_saved(key, crop_path.name, size, "image/png")
                    item["illustration_file_id"] = fm_id
                    image_file_ids[key] = fm_id

        markdown_content = self._generate_page_markdown(page_items)
        result = {
            "page_number": page_index + 1,
            "markdown_content": markdown_content,
            "image_file_ids": image_file_ids,
        }

        export_pipeline_debug(
            "content_extraction",
            "output",
            {
                "page_number": result["page_number"],
                "markdown_length": len(markdown_content),
                "image_count": len(image_file_ids),
                "markdown_preview": markdown_content[:500],
            },
            page_index + 1,
        )

        return result

    async def _extract_page_with_ocr(
        self, image_path: Path, page_index: int
    ) -> list[dict[str, Any]]:
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

    @staticmethod
    def _generate_page_markdown(items: list[dict[str, Any]]) -> str:
        if not items:
            return ""

        markdown_parts: list[str] = []

        for item in items:
            content = item.get("content", "").strip()
            if not content:
                continue

            content_type = item.get("content_type", "text").lower()

            if content_type in {"text", "table", "formula"}:
                markdown_parts.append(content)
                continue

            if content_type in {"image", "figure", "chart", "graphic"}:
                file_id = item.get("illustration_file_id")
                if file_id:
                    markdown_parts.append(f"<dh-image>{file_id}</dh-image>")
                else:
                    markdown_parts.append(f"[{content_type.capitalize()}]")
                continue

            if content_type == "seal":
                continue

            markdown_parts.append(content)

        return "\n".join(markdown_parts).strip()
