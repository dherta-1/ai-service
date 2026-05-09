"""Exam Instance Export Service

Orchestrates the full export flow:
  1. Fetch exam instance + all its questions/answers
  2. Collect presigned URLs for all image_list file IDs
  3. Build PDF via exam_pdf_build pipeline
  4. Upload PDF to S3 and save FileMetadata record
  5. Mark ExamInstance.is_exported = True, store exported_file_id
  6. Return (pdf_bytes, file_id) so callers can stream or redirect
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional
from uuid import UUID

from src.pipelines.exam_pdf_build_v2 import ExamPdfBuildInput, ExamPdfBuildPipelineV2
from src.entities.exam_instance import ExamInstance
from src.entities.file_metadata import FileMetadata
from src.lib.s3_client import S3Client
from src.lib.playwright import PlaywrightManager
from src.repos.exam_instance_repo import ExamInstanceRepository
from src.repos.file_metadata_repo import FileMetadataRepository
from src.services.exam_service import ExamService
from src.services.file_service import FileService

logger = logging.getLogger(__name__)


class ExamInstanceExportService:
    """Builds and exports an exam instance as a PDF."""

    def __init__(
        self,
        s3_client: S3Client,
        s3_bucket: str,
        exam_service: ExamService,
        file_service: FileService,
        playwright_manager: PlaywrightManager,
    ):
        self._s3 = s3_client
        self._bucket = s3_bucket
        self._exam_service = exam_service
        self._file_service = file_service
        self._playwright = playwright_manager
        self._instance_repo = ExamInstanceRepository()
        self._file_meta_repo = FileMetadataRepository()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def export(
        self,
        exam_id: UUID,
        school_name: str = "TRƯỜNG ĐẠI HỌC",
        subject_label: str = "",
        duration_minutes: int = 90,
        include_answer_key: bool = True,
        force_regenerate: bool = False,
        pdf_version: str = "v2",
    ) -> tuple[bytes, str]:
        """Export exam to PDF with full regeneration and override.

        Always performs a fresh PDF build. If the exam already has an exported file,
        deletes the old PDF and metadata record before creating a new one.

        Args:
            exam_id: UUID of exam instance to export
            school_name: School/institution name for header
            subject_label: Subject display name
            duration_minutes: Exam duration in minutes
            include_answer_key: Append answer key page
            force_regenerate: Deprecated (always regenerates now)
            pdf_version: "v1" (reportlab) or "v2" (xhtml2pdf + Jinja2). Default "v2".

        Returns:
            (pdf_bytes, file_id_str)
        """
        exam = self._instance_repo.get_by_id(exam_id)
        if not exam:
            raise ValueError(f"Exam instance {exam_id} not found")

        # Delete old export if exists
        if exam.is_exported and exam.exported_file_id:
            self._delete_old_export(exam.exported_file_id)

        # Build fresh
        exam_data = self._exam_service.build_exam_response_data(exam)
        exam_data.pop("_total_questions", None)

        presigned_urls = self._collect_presigned_urls(exam_data)

        pipeline = ExamPdfBuildPipelineV2(playwright_manager=self._playwright)

        pdf_bytes = await pipeline.run(
            ExamPdfBuildInput(
                exam_data=exam_data,
                presigned_urls=presigned_urls,
                school_name=school_name,
                subject_label=subject_label,
                duration_minutes=duration_minutes,
                include_answer_key=include_answer_key,
            )
        )

        file_id = self._upload_pdf(
            pdf_bytes, exam_data.get("exam_test_code", str(exam_id))
        )
        self._mark_exported(exam, file_id)

        return pdf_bytes, file_id

    def get_download_url(self, exam_id: UUID, expires_in: int = 3600) -> Optional[str]:
        """Return a presigned download URL for an already-exported exam."""
        exam = self._instance_repo.get_by_id(exam_id)
        if not exam or not exam.exported_file_id:
            return None
        return self._file_service.get_presigned_url(
            UUID(exam.exported_file_id), expires_in=expires_in
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _collect_presigned_urls(self, exam_data: Dict[str, Any]) -> Dict[str, str]:
        """Walk exam_data and gather presigned URLs for every image file_id."""
        file_ids: List[str] = []

        for section in exam_data.get("sections", []):
            for q in section.get("questions", []):
                file_ids.extend(q.get("image_list") or [])
                for sq in q.get("sub_questions") or []:
                    file_ids.extend(sq.get("image_list") or [])

        urls: Dict[str, str] = {}
        for fid in set(file_ids):
            try:
                url = self._file_service.get_presigned_url(UUID(fid), expires_in=600)
                if url:
                    urls[fid] = url
            except Exception as exc:
                logger.warning("Could not get presigned URL for file %s: %s", fid, exc)

        return urls

    def _upload_pdf(self, pdf_bytes: bytes, exam_code: str) -> str:
        """Upload PDF bytes to S3 and create FileMetadata record."""
        uid = str(uuid.uuid4())
        object_key = f"exports/exams/{exam_code}_{uid}.pdf"

        self._s3.upload_file_bytes(
            file_content=pdf_bytes,
            bucket=self._bucket,
            key=object_key,
            content_type="application/pdf",
        )

        meta = FileMetadata.create(
            name=f"{exam_code}.pdf",
            path=object_key,
            size=len(pdf_bytes),
            mime_type="application/pdf",
            object_key=object_key,
        )
        file_id = str(meta.id)

        logger.info(
            "Uploaded exam PDF to s3://%s/%s (file_id=%s)",
            self._bucket,
            object_key,
            file_id,
        )
        return str(meta.id)

    def _mark_exported(self, exam: ExamInstance, file_id: str) -> None:
        ExamInstance.update(
            is_exported=True,
            exported_file_id=file_id,
        ).where(ExamInstance.id == exam.id).execute()
        exam.is_exported = True
        exam.exported_file_id = file_id

    def _download_existing(self, file_id: str) -> Optional[bytes]:
        """Re-download PDF bytes from S3 for an existing export."""
        try:
            file_meta = self._file_meta_repo.get_by_id(UUID(file_id))
            if not file_meta or not file_meta.object_key:
                return None
            data = self._s3.download_file_bytes(
                bucket=self._bucket, key=file_meta.object_key
            )
            return data
        except Exception as exc:
            logger.warning("Could not re-download existing export %s: %s", file_id, exc)
            return None

    def _delete_old_export(self, file_id: str) -> None:
        """Delete old exported PDF file and its metadata record."""
        try:
            file_meta = self._file_meta_repo.get_by_id(UUID(file_id))
            if file_meta and file_meta.object_key:
                # Delete from S3
                try:
                    self._s3.delete_file(bucket=self._bucket, key=file_meta.object_key)
                    logger.info(
                        "Deleted old exam PDF from s3://%s/%s",
                        self._bucket,
                        file_meta.object_key,
                    )
                except Exception as exc:
                    logger.warning(
                        "Could not delete old S3 file %s: %s", file_meta.object_key, exc
                    )

                # Delete metadata record
                if self._file_meta_repo.delete_by_id(UUID(file_id)):
                    logger.info("Deleted file metadata record %s", file_id)
                else:
                    logger.warning("Could not delete file metadata record %s", file_id)
            else:
                logger.warning("File metadata %s not found for deletion", file_id)
        except Exception as exc:
            logger.warning("Error deleting old export %s: %s", file_id, exc)
