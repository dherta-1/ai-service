"""Document extraction flow service."""

from __future__ import annotations

import io
import logging
import uuid
from pathlib import Path
from typing import Optional

import fitz
from PIL import Image

from src.pipelines.content_extraction import ContentExtractionPipeline
from src.pipelines.question_extraction import QuestionExtractionPipeline
from src.pipelines.content_validation import ContentValidationPipeline
from src.prompts.content_validation_prompt import content_validation_prompt
from src.prompts.question_extraction_prompt import question_extraction_prompt

logger = logging.getLogger(__name__)


class DocumentProcessingService:
    """Process uploaded documents into normalized markdown per page."""

    def __init__(
        self,
        ocr_client,
        s3_client,
        llm_client=None,
        s3_bucket: Optional[str] = None,
    ):
        self.ocr_client = ocr_client
        self.s3_client = s3_client
        self.llm_client = llm_client
        self.s3_bucket = s3_bucket
        self.output_dir = Path("output")
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.extraction_pipeline = ContentExtractionPipeline(
            ocr_client=self.ocr_client,
            s3_client=self.s3_client,
        )
        self.validation_pipeline = ContentValidationPipeline(
            llm_client=self.llm_client,
            prompt_template=content_validation_prompt,
        )
        self.question_pipeline = QuestionExtractionPipeline(
            llm_client=self.llm_client,
            prompt_template=question_extraction_prompt,
        )

    async def process_document(
        self,
        local_file_path: str,
        original_filename: str,
        s3_bucket: Optional[str] = None,
        s3_prefix: str = "document-extraction",
    ) -> dict[str, object]:
        """Main flow: render pages, OCR extraction, then multimodal normalization."""
        file_id = str(uuid.uuid4())
        file_path = Path(local_file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"Uploaded file not found: {local_file_path}")

        bucket = s3_bucket or self.s3_bucket
        if bucket:
            key = f"{s3_prefix}/{file_id}/input/{original_filename}"
            self.s3_client.upload_file(str(file_path), bucket, key)

        doc = fitz.open(str(file_path))

        try:
            page_image_paths: list[Path] = []
            for page_index in range(doc.page_count):
                page = doc[page_index]
                image_path = self._render_page_to_image(file_id, page_index, page)
                page_image_paths.append(image_path)

            crop_dir = self.output_dir / file_id / "crops"
            crop_dir.mkdir(parents=True, exist_ok=True)

            pages_output: list[dict[str, object]] = []

            for page_index, image_path in enumerate(page_image_paths):
                extracted = await self.extraction_pipeline.run(
                    {
                        "image_path": image_path,
                        "page_index": page_index,
                        "crop_dir": crop_dir,
                        "file_id": file_id,
                        "s3_prefix": s3_prefix,
                        "bucket": bucket,
                    }
                )

                validated = await self.validation_pipeline.run(
                    {
                        "image_path": image_path,
                        "page_number": extracted["page_number"],
                        "markdown_content": extracted["markdown_content"],
                    }
                )

                questions = await self.question_pipeline.run(
                    {
                        "image_path": image_path,
                        "page_number": extracted["page_number"],
                        "markdown_content": validated["content"],
                    }
                )

                pages_output.append(
                    {
                        "page_number": validated["page_number"],
                        "content": validated["content"],
                        "questions": questions["questions"],
                    }
                )

            return {
                "file_id": file_id,
                "filename": original_filename,
                "pages": pages_output,
            }
        finally:
            doc.close()

    def _render_page_to_image(
        self, file_id: str, page_index: int, page: fitz.Page
    ) -> Path:
        """Render a PDF page to PIL image and save locally."""
        matrix = fitz.Matrix(2.0, 2.0)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        pil_image = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")

        image_dir = self.output_dir / file_id / "pages"
        image_dir.mkdir(parents=True, exist_ok=True)
        image_path = image_dir / f"page_{page_index + 1}.png"
        pil_image.save(image_path, format="PNG")
        return image_path
