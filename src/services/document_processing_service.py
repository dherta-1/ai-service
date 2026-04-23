"""Document extraction flow service."""

from __future__ import annotations

import json
import asyncio
import io
import logging
import re
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Optional

import fitz
from PIL import Image

logger = logging.getLogger(__name__)

from src.entities.document import Document
from src.entities.file_metadata import FileMetadata
from src.entities.page import Page
from src.entities.question import Question
from src.pipelines.content_extraction import ContentExtractionPipeline
from src.pipelines.content_validation import ContentValidationPipeline
from src.pipelines.page_head_overlap import PageHeadOverlapPipeline
from src.pipelines.question_embedding import QuestionEmbeddingPipeline
from src.pipelines.question_extraction import QuestionExtractionPipeline
from src.prompts.content_validation_prompt import content_validation_prompt
from src.prompts.question_extraction_prompt import question_extraction_prompt
from src.repos.document_repo import DocumentRepository
from src.repos.file_metadata_repo import FileMetadataRepository
from src.repos.page_repo import PageRepository
from src.repos.question_repo import QuestionRepository
from src.repos.subject_repo import SubjectRepository
from src.repos.topic_repo import TopicRepository
from src.shared.constants.general import Status

logger = logging.getLogger(__name__)

# Regex to find presigned-URL <img> tags left by older pipeline runs
_IMG_PRESIGNED_RE = re.compile(r'<img\s+src="[^"]*"\s+alt="[^"]*"\s*/>', re.IGNORECASE)


class DocumentProcessingService:
    """Process uploaded documents into normalized markdown per page."""

    def __init__(
        self,
        ocr_client,
        s3_client,
        llm_client=None,
        s3_bucket: Optional[str] = None,
        page_overlap_char_count: int = 500,
    ):
        self.ocr_client = ocr_client
        self.s3_client = s3_client
        self.llm_client = llm_client
        self.s3_bucket = s3_bucket

        self.extraction_pipeline = ContentExtractionPipeline(
            ocr_client=self.ocr_client,
            s3_client=self.s3_client,
        )
        self.validation_pipeline = ContentValidationPipeline(
            llm_client=self.llm_client,
            prompt_template=content_validation_prompt,
        )
        self.overlap_pipeline = PageHeadOverlapPipeline(
            overlap_char_count=page_overlap_char_count
        )
        self.question_pipeline = QuestionExtractionPipeline(
            llm_client=self.llm_client,
            prompt_template=question_extraction_prompt,
        )
        self.embedding_pipeline = QuestionEmbeddingPipeline(
            llm_client=self.llm_client,
        )

        # Repos
        self._doc_repo = DocumentRepository()
        self._page_repo = PageRepository()
        self._question_repo = QuestionRepository()
        self._file_meta_repo = FileMetadataRepository()
        self._subject_repo = SubjectRepository()
        self._topic_repo = TopicRepository()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def process_document(
        self,
        local_file_path: str,
        original_filename: str,
        s3_bucket: Optional[str] = None,
        s3_prefix: str = "document-extraction",
    ) -> dict[str, object]:
        """Main flow: render pages → OCR → validate → extract questions → persist."""
        file_id = str(uuid.uuid4())
        file_path = Path(local_file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"Uploaded file not found: {local_file_path}")

        bucket = s3_bucket or self.s3_bucket

        # Upload original PDF file to S3 and save metadata
        pdf_s3_key = f"{s3_prefix}/{file_id}/input/{original_filename}"
        if bucket:
            self.s3_client.upload_file(str(file_path), bucket, pdf_s3_key)

        # Register original PDF in file_metadata
        pdf_file_size = file_path.stat().st_size
        pdf_fm_id = await asyncio.to_thread(
            self._register_image_file,
            object_key=pdf_s3_key,
            name=original_filename,
            size=pdf_file_size,
            mime_type="application/pdf",
        )

        # Create Document record (status=processing) with PDF file reference
        document = await asyncio.to_thread(
            self._doc_repo.create,
            name=original_filename,
            file_id=pdf_fm_id,
            status=Status.PROCESSING.value,
            progress=0.0,
        )

        try:
            doc = fitz.open(str(file_path))
            try:
                pages_output = await self._process_pages(
                    doc=doc,
                    file_id=file_id,
                    bucket=bucket,
                    s3_prefix=s3_prefix,
                    document=document,
                )
            finally:
                doc.close()

            # Mark document completed
            await asyncio.to_thread(
                self._doc_repo.update,
                document.id,
                status=Status.COMPLETED.value,
                progress=100.0,
            )

            return {
                "file_id": file_id,
                "filename": original_filename,
                "pages": pages_output,
            }

        except Exception:
            await asyncio.to_thread(
                self._doc_repo.update,
                document.id,
                status=Status.FAILED.value,
            )
            raise

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _process_pages(
        self,
        doc: fitz.Document,
        file_id: str,
        bucket: Optional[str],
        s3_prefix: str,
        document: Document,
    ) -> list[dict]:
        # Create temporary directory for this document's processing
        temp_dir = Path(tempfile.mkdtemp(prefix=f"doc_{file_id}_"))
        try:
            page_image_paths: list[Path] = []
            page_image_ids: list[Optional[str]] = []
            for page_index in range(doc.page_count):
                page = doc[page_index]
                image_path, fm_id = await self._render_and_save_page_image(
                    file_id, page_index, page, bucket, s3_prefix, temp_dir
                )
                page_image_paths.append(image_path)
                page_image_ids.append(fm_id)

            crop_dir = temp_dir / "crops"
            crop_dir.mkdir(parents=True, exist_ok=True)

            pages_output: list[dict] = []
            previous_page_content: Optional[str] = None
            total = len(page_image_paths)

            for page_index, (image_path, page_fm_id) in enumerate(
                zip(page_image_paths, page_image_ids)
            ):
                page_data = await self._process_single_page(
                    image_path=image_path,
                    page_index=page_index,
                    crop_dir=crop_dir,
                    file_id=file_id,
                    bucket=bucket,
                    s3_prefix=s3_prefix,
                    previous_page_content=previous_page_content,
                    document=document,
                    page_fm_id=page_fm_id,
                )
                pages_output.append(
                    {
                        "page_number": page_data["page_number"],
                        "content": page_data["content"],
                        "questions": [
                            self._question_to_dict(q) for q in page_data["questions"]
                        ],
                    }
                )
                previous_page_content = page_data["content"]

                progress = round((page_index + 1) / total * 100.0, 1)
                await asyncio.to_thread(
                    self._doc_repo.update, document.id, progress=progress
                )

            return pages_output
        finally:
            # Clean up temporary directory
            shutil.rmtree(temp_dir, ignore_errors=True)

    async def _process_single_page(
        self,
        image_path: Path,
        page_index: int,
        crop_dir: Path,
        file_id: str,
        bucket: Optional[str],
        s3_prefix: str,
        previous_page_content: Optional[str],
        document: Document,
        page_fm_id: Optional[str] = None,
    ) -> dict:
        # --- Content extraction (OCR + crop upload) ---
        extracted = await self.extraction_pipeline.run(
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
        self._assert_keys(extracted, ["page_number", "markdown_content"], "extraction")

        # --- Content validation ---
        validated = await self.validation_pipeline.run(
            {
                "image_path": image_path,
                "page_number": extracted["page_number"],
                "markdown_content": extracted["markdown_content"],
            }
        )
        self._assert_keys(validated, ["page_number", "content"], "validation")

        # --- Page head overlap ---
        overlap_result = await self.overlap_pipeline.run(
            {
                "page_number": validated["page_number"],
                "markdown_content": validated["content"],
                "previous_page_content": previous_page_content,
            }
        )
        self._assert_keys(
            overlap_result, ["page_number", "markdown_content"], "overlap"
        )

        # --- Question extraction ---
        questions_result = await self.question_pipeline.run(
            {
                "page_number": overlap_result["page_number"],
                "markdown_content": overlap_result["markdown_content"],
                "overlap_content": overlap_result.get("overlap_content"),
            }
        )
        self._assert_keys(
            questions_result, ["page_number", "questions"], "question_extraction"
        )

        page_content = validated["content"]
        raw_questions: list[dict] = questions_result["questions"]

        # --- Persist Page ---
        page_orm = await asyncio.to_thread(
            self._page_repo.create,
            document=document,
            page_number=validated["page_number"],
            content=page_content,
            page_image_id=page_fm_id,
        )

        # --- Ensure subject/topic taxonomy exists, then persist Questions ---
        question_orms = await self._save_questions(raw_questions, page_orm)

        # --- Compute embeddings ---
        if question_orms and self.llm_client:
            try:
                await self.embedding_pipeline.run({"questions": question_orms})
            except Exception as exc:
                logger.warning("Embedding failed for page %d: %s", page_index + 1, exc)

        logger.info("Page %d: saved %d questions", page_index + 1, len(question_orms))
        return {
            "page_number": validated["page_number"],
            "content": page_content,
            "questions": question_orms,
        }

    # ------------------------------------------------------------------
    # Image file metadata registration
    # ------------------------------------------------------------------

    def _register_image_file(
        self, object_key: str, name: str, size: int, mime_type: str
    ) -> str:
        """Save a crop image to file_metadata and return its UUID string."""
        fm = self._file_meta_repo.create(
            name=name,
            path=object_key,
            size=size,
            mime_type=mime_type,
            object_key=object_key,
        )
        return str(fm.id)

    # ------------------------------------------------------------------
    # Taxonomy helpers
    # ------------------------------------------------------------------

    def _ensure_subject(self, subject_code: Optional[str]) -> None:
        if not subject_code:
            return
        self._subject_repo.get_or_create(
            code=subject_code.lower(),
            name=subject_code.capitalize(),
        )

    def _ensure_topic(self, topic_code: Optional[str]) -> None:
        if not topic_code:
            return
        self._topic_repo.get_or_create(
            code=topic_code.lower(),
            name=topic_code.replace("_", " ").title(),
        )

    # ------------------------------------------------------------------
    # Question persistence
    # ------------------------------------------------------------------

    async def _save_questions(
        self, raw_questions: list[dict], page_orm: Page
    ) -> list[Question]:
        if not raw_questions:
            return []

        # Collect distinct subjects/topics and upsert them first
        subjects = {q.get("subject") for q in raw_questions if q.get("subject")}
        topics = {q.get("topic") for q in raw_questions if q.get("topic")}

        def _upsert_taxonomy():
            for s in subjects:
                self._ensure_subject(s)
            for t in topics:
                self._ensure_topic(t)

        await asyncio.to_thread(_upsert_taxonomy)

        def _create_all():
            saved = []
            for q in raw_questions:
                image_list = self._resolve_image_list(q.get("image_list") or [])

                # Normalize answers: could be string (JSON), list, or None
                answers_raw = q.get("answers")
                if isinstance(answers_raw, str):
                    try:
                        answers = json.loads(answers_raw)
                    except (json.JSONDecodeError, ValueError):
                        answers = None
                elif isinstance(answers_raw, list):
                    answers = answers_raw
                else:
                    answers = None

                orm = self._question_repo.create(
                    page=page_orm,
                    question_text=q.get("question_text", ""),
                    question_type=q.get("question_type", "short_answer"),
                    difficulty=q.get("difficulty"),
                    subject=q.get("subject"),
                    topic=q.get("topic"),
                    answers=answers,
                    correct_answer=q.get("correct_answer"),
                    sub_questions=q.get("sub_questions") or None,
                    image_list=image_list if image_list else None,
                    status=0,
                )
                saved.append(orm)
            return saved

        return await asyncio.to_thread(_create_all)

    def _resolve_image_list(self, image_list: list) -> list[str]:
        """Convert any presigned-URL entries to file_metadata IDs.

        The extraction pipeline now emits file IDs directly, but if any
        legacy presigned URLs slip through (e.g. from LLM output), look them
        up in file_metadata by object_key fragment.
        """
        resolved = []
        for entry in image_list:
            if not entry:
                continue
            # Already a plain UUID string — keep as-is
            if _is_uuid(entry):
                resolved.append(entry)
                continue
            # Presigned URL: extract object key and look up file_metadata
            key = _extract_s3_key(entry)
            if key:
                fm = self._file_meta_repo.get_by_object_key(key)
                if fm:
                    resolved.append(str(fm.id))
                    continue
            # Fallback: skip unknown references
            logger.warning(
                "Could not resolve image reference to file_metadata: %s", entry
            )
        return resolved

    # ------------------------------------------------------------------
    # Serialization helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _question_to_dict(q: Question) -> dict:
        return {
            "question_text": q.question_text,
            "question_type": q.question_type,
            "difficulty": q.difficulty,
            "subject": q.subject,
            "topic": q.topic,
            "answers": q.answers,
            "correct_answer": q.correct_answer,
            "sub_questions": q.sub_questions,
            "image_list": q.image_list,
        }

    # ------------------------------------------------------------------
    # Page rendering
    # ------------------------------------------------------------------

    async def _render_and_save_page_image(
        self,
        file_id: str,
        page_index: int,
        page: fitz.Page,
        bucket: Optional[str],
        s3_prefix: str,
        temp_dir: Path,
    ) -> tuple[Path, Optional[str]]:
        """Render page to image, save temp for OCR processing, upload to S3, register in file_metadata.

        Keeps temp file for processing (OCR/extraction), uploads to S3, and returns file_metadata_id.
        Returns (local_temp_path, file_metadata_id)
        """
        matrix = fitz.Matrix(2.0, 2.0)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        pil_image = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")

        image_dir = temp_dir / "pages"
        image_dir.mkdir(parents=True, exist_ok=True)
        image_name = f"page_{page_index + 1}.png"
        image_path = image_dir / image_name

        def _save_temp():
            pil_image.save(image_path, format="PNG")
            return image_path

        local_path = await asyncio.to_thread(_save_temp)

        # Upload to S3 if configured and register in file_metadata
        fm_id = None
        if bucket:
            s3_key = f"{s3_prefix}/{file_id}/pages/{image_name}"
            await asyncio.to_thread(
                self.s3_client.upload_file,
                str(local_path),
                bucket,
                s3_key,
            )
            # Register in file_metadata
            size = local_path.stat().st_size
            fm_id = await asyncio.to_thread(
                self._register_image_file,
                object_key=s3_key,
                name=image_name,
                size=size,
                mime_type="image/png",
            )

        return local_path, fm_id

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def _assert_keys(result: object, keys: list[str], stage: str) -> None:
        if not isinstance(result, dict):
            raise ValueError(
                f"{stage} pipeline returned invalid type: {type(result).__name__}"
            )
        missing = [k for k in keys if k not in result]
        if missing:
            raise KeyError(
                f"{stage} pipeline missing required keys {missing}. Got: {list(result.keys())}"
            )


# ------------------------------------------------------------------
# Module-level utilities
# ------------------------------------------------------------------

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _is_uuid(value: str) -> bool:
    return bool(_UUID_RE.match(value.strip()))


def _extract_s3_key(url: str) -> Optional[str]:
    """Extract the object key path from a presigned S3 URL or plain key string."""
    # Presigned URLs contain '?' for query params; the key is the URL path portion
    try:
        from urllib.parse import urlparse, unquote

        parsed = urlparse(url)
        if parsed.scheme in ("http", "https"):
            # Strip leading '/' and decode percent-encoding
            return unquote(parsed.path.lstrip("/"))
    except Exception:
        pass
    return None
