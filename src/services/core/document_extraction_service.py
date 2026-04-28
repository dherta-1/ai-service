"""OCR + Validate Worker core service.

Specification (Worker 1):
  Lấy event → Xử lý trích xuất nội dung từng trang + validate → pass page_id qua event
"""

from __future__ import annotations

import asyncio
import io
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Callable, List, Optional
from uuid import UUID

import fitz
from PIL import Image

from src.entities.document import Document
from src.entities.page import Page
from src.entities.task import Task
from src.pipelines.content_extraction import ContentExtractionPipeline
from src.pipelines.content_validation import ContentValidationPipeline
from src.pipelines.page_head_overlap import PageHeadOverlapPipeline
from src.prompts.content_validation_prompt import content_validation_prompt
from src.repos.document_repo import DocumentRepository
from src.repos.file_metadata_repo import FileMetadataRepository
from src.repos.page_repo import PageRepository
from src.repos.task_repo import TaskRepository
from src.shared.constants.general import Status
from src.shared.helpers.task_logger import TaskLogger

logger = logging.getLogger(__name__)


class ExtractedPageResult:
    """Result of extracting and validating a single page."""

    def __init__(self, page: Page, is_final: bool):
        self.page = page
        self.is_final = is_final


class DocumentExtractionService:
    """OCR + Validate Worker.

    Extracts page content from a PDF, validates via LLM, saves Page records,
    creates a Task record, and calls on_page_ready for each page so the caller
    can publish events or chain the next worker.
    """

    def __init__(
        self,
        ocr_client,
        llm_client,
        s3_client,
        s3_bucket: Optional[str] = None,
        page_overlap_char_count: int = 500,
    ):
        self._ocr_client = ocr_client
        self._llm_client = llm_client
        self._s3_client = s3_client
        self._s3_bucket = s3_bucket

        self._extraction_pipeline = ContentExtractionPipeline(
            ocr_client=ocr_client,
            s3_client=s3_client,
        )
        self._validation_pipeline = ContentValidationPipeline(
            llm_client=llm_client,
            prompt_template=content_validation_prompt,
        )
        self._overlap_pipeline = PageHeadOverlapPipeline(
            overlap_char_count=page_overlap_char_count
        )

        self._doc_repo = DocumentRepository()
        self._page_repo = PageRepository()
        self._file_meta_repo = FileMetadataRepository()
        self._task_repo = TaskRepository()
        self._task_logger = TaskLogger(self._task_repo)

    async def extract_document(
        self,
        document_id: UUID,
        local_pdf_path: str,
        s3_prefix: str = "document-extraction",
        on_page_ready: Optional[Callable[[ExtractedPageResult, Task], None]] = None,
    ) -> Task:
        """Extract all pages from a PDF, validate them, and persist Page records.

        Args:
            document_id: Existing document record id.
            local_pdf_path: Path to the local PDF file.
            s3_prefix: S3 prefix for uploads.
            on_page_ready: Callback invoked after each page is saved.
                           Signature: (result: ExtractedPageResult, task: Task) -> None
        Returns:
            The Task record tracking this extraction.
        """
        document = self._doc_repo.get_by_id(document_id)
        if document is None:
            raise ValueError(f"Document {document_id} not found")

        file_path = Path(local_pdf_path)
        if not file_path.exists():
            raise FileNotFoundError(f"PDF not found: {local_pdf_path}")

        doc = fitz.open(str(file_path))
        total_pages = doc.page_count
        doc.close()

        task = await asyncio.to_thread(
            self._task_repo.create,
            name=f"extract_{document.name}",
            type="document_extraction",
            entity_id=document_id,
            entity_type="document",
            document=document,
            status=Status.PROCESSING.value,
            progress=0.0,
            total_pages=total_pages,
            processed_pages=0,
            logs=[],
        )
        self._task_logger.log_started(task.id, total_pages)

        await asyncio.to_thread(
            self._doc_repo.update,
            document_id,
            status=Status.PROCESSING.value,
            progress=0.0,
        )

        try:
            await self._process_all_pages(
                document=document,
                local_pdf_path=local_pdf_path,
                s3_prefix=s3_prefix,
                task=task,
                on_page_ready=on_page_ready,
            )
        except Exception as exc:
            logger.error("Document extraction failed for %s: %s", document_id, exc)
            await asyncio.to_thread(
                self._task_repo.update_status, task.id, Status.FAILED.value
            )
            await asyncio.to_thread(
                self._doc_repo.update, document_id, status=Status.FAILED.value
            )
            raise

        return task

    async def _process_all_pages(
        self,
        document: Document,
        local_pdf_path: str,
        s3_prefix: str,
        task: Task,
        on_page_ready: Optional[Callable],
    ) -> None:
        file_path = Path(local_pdf_path)
        file_id = str(document.file_id)
        bucket = self._s3_bucket

        doc = fitz.open(str(file_path))
        total = doc.page_count
        temp_dir = Path(tempfile.mkdtemp(prefix=f"doc_{file_id}_"))

        try:
            page_image_paths: list[tuple[Path, Optional[str]]] = []
            for page_index in range(total):
                img_path, fm_id = await self._render_page_image(
                    doc=doc,
                    page_index=page_index,
                    file_id=file_id,
                    bucket=bucket,
                    s3_prefix=s3_prefix,
                    temp_dir=temp_dir,
                )
                page_image_paths.append((img_path, fm_id))

            crop_dir = temp_dir / "crops"
            crop_dir.mkdir(parents=True, exist_ok=True)

            previous_content: Optional[str] = None
            for page_index, (img_path, fm_id) in enumerate(page_image_paths):
                is_final = page_index == total - 1
                page_orm, validated_content = await self._extract_single_page(
                    image_path=img_path,
                    page_index=page_index,
                    crop_dir=crop_dir,
                    file_id=file_id,
                    bucket=bucket,
                    s3_prefix=s3_prefix,
                    previous_content=previous_content,
                    document=document,
                    page_image_fm_id=fm_id,
                )
                previous_content = validated_content

                result = ExtractedPageResult(page=page_orm, is_final=is_final)
                if on_page_ready:
                    try:
                        on_page_ready(result, task)
                    except Exception as cb_exc:
                        logger.warning(
                            "on_page_ready callback failed for page %d: %s",
                            page_index + 1,
                            cb_exc,
                        )

                progress = round((page_index + 1) / total, 4)
                await asyncio.to_thread(
                    self._doc_repo.update, document.id, progress=progress * 100.0
                )
                logger.info(
                    "Page %d/%d extracted for document %s",
                    page_index + 1,
                    total,
                    document.id,
                )
        finally:
            doc.close()
            shutil.rmtree(temp_dir, ignore_errors=True)

    async def _extract_single_page(
        self,
        image_path: Path,
        page_index: int,
        crop_dir: Path,
        file_id: str,
        bucket: Optional[str],
        s3_prefix: str,
        previous_content: Optional[str],
        document: Document,
        page_image_fm_id: Optional[str],
    ) -> tuple[Page, str]:
        extracted = await self._extraction_pipeline.run(
            {
                "image_path": image_path,
                "page_index": page_index,
                "crop_dir": crop_dir,
                "file_id": file_id,
                "s3_prefix": s3_prefix,
                "bucket": bucket,
                "on_image_saved": self._register_image_file,
            }
        )

        validated = await self._validation_pipeline.run(
            {
                "image_path": image_path,
                "page_number": extracted["page_number"],
                "markdown_content": extracted["markdown_content"],
            }
        )

        overlap = await self._overlap_pipeline.run(
            {
                "page_number": validated["page_number"],
                "markdown_content": validated["content"],
                "previous_page_content": previous_content,
            }
        )

        # Extract overlap content for storage
        overlap_content_text = ""
        if overlap.get("overlap_content") and isinstance(overlap["overlap_content"], dict):
            overlap_content_text = overlap["overlap_content"].get("content", "")

        page_orm = await asyncio.to_thread(
            self._page_repo.create,
            document=document,
            page_number=validated["page_number"],
            content=overlap["markdown_content"],
            validated_content=validated["content"],
            overlap_content=overlap_content_text,
            page_image_id=page_image_fm_id,
        )

        return page_orm, validated["content"]

    async def _render_page_image(
        self,
        doc: fitz.Document,
        page_index: int,
        file_id: str,
        bucket: Optional[str],
        s3_prefix: str,
        temp_dir: Path,
    ) -> tuple[Path, Optional[str]]:
        page = doc[page_index]
        matrix = fitz.Matrix(2.0, 2.0)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        pil_image = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")

        image_dir = temp_dir / "pages"
        image_dir.mkdir(parents=True, exist_ok=True)
        image_name = f"page_{page_index + 1}.png"
        image_path = image_dir / image_name

        def _save():
            pil_image.save(image_path, format="PNG")

        await asyncio.to_thread(_save)

        fm_id = None
        if bucket:
            s3_key = f"{s3_prefix}/{file_id}/pages/{image_name}"
            await asyncio.to_thread(
                self._s3_client.upload_file, str(image_path), bucket, s3_key
            )
            size = image_path.stat().st_size
            fm_id = await asyncio.to_thread(
                self._register_image_file,
                object_key=s3_key,
                name=image_name,
                size=size,
                mime_type="image/png",
            )

        return image_path, fm_id

    def _register_image_file(
        self, object_key: str, name: str, size: int, mime_type: str
    ) -> str:
        fm = self._file_meta_repo.create(
            name=name,
            path=object_key,
            size=size,
            mime_type=mime_type,
            object_key=object_key,
        )
        return str(fm.id)
