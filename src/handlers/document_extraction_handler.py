"""document_extraction_handler – download file from S3, extract pages, publish per-page events."""

from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict
from uuid import UUID

from src.shared.base.base_handler import BaseEventHandler

logger = logging.getLogger(__name__)


class DocumentExtractionHandler(BaseEventHandler):
    """Handles document_extraction_requested events.

    Event payload:
    {
        "event_type": "document_extraction_requested",
        "document_id": str(UUID)
    }

    Fetches document file from S3, extracts pages, publishes question_extraction_requested.
    """

    @property
    def event_type(self) -> str:
        return "document_extraction_requested"

    @property
    def topic(self) -> str:
        return "document_extraction_requested"

    def __init__(self):
        from src.services.core.document_extraction_service import DocumentExtractionService
        from src.lib.event_bus.kafka.producer import KafkaProducerImpl
        from src.container import get_di_container
        from src.settings import get_settings

        container = get_di_container()
        settings = get_settings()
        s3_bucket = getattr(settings, "aws_s3_bucket", None)

        self._kafka_producer = container.get("kafka_producer") or KafkaProducerImpl()
        self._service = DocumentExtractionService(
            ocr_client=container.get("ocr_client"),
            llm_client=container.get("llm_client"),
            s3_client=container.get("s3_client"),
            s3_bucket=s3_bucket,
        )
        self._s3_client = container.get("s3_client")
        self._s3_bucket = s3_bucket

    def handle(self, key: str, value: Dict[str, Any]) -> None:
        asyncio.run(self._handle_async(value))

    async def _handle_async(self, value: Dict[str, Any]) -> None:
        from src.repos.document_repo import DocumentRepository
        from src.repos.file_metadata_repo import FileMetadataRepository
        from src.shared.constants.general import Status

        document_id = UUID(value["document_id"])
        doc_repo = DocumentRepository()
        file_meta_repo = FileMetadataRepository()

        temp_dir = None
        local_pdf_path = None

        try:
            # Fetch document metadata
            document = doc_repo.get_by_id(document_id)
            if not document:
                raise ValueError(f"Document {document_id} not found")

            if not document.file_id:
                raise ValueError(f"Document {document_id} has no file_id")

            # Download PDF from S3 to temp path
            temp_dir = Path(tempfile.mkdtemp(prefix=f"doc_{document_id}_"))
            local_pdf_path = temp_dir / "document.pdf"

            if self._s3_bucket:
                file_metadata = file_meta_repo.get_by_id(document.file_id)
                if not file_metadata or not file_metadata.object_key:
                    raise ValueError(f"File metadata not found for document {document_id}")

                await asyncio.to_thread(
                    self._s3_client.download_file,
                    self._s3_bucket,
                    file_metadata.object_key,
                    str(local_pdf_path),
                )
            else:
                raise ValueError("S3 bucket not configured")

            # Mark document as PROCESSING
            await asyncio.to_thread(
                doc_repo.update,
                document_id,
                status=Status.PROCESSING.value,
                progress=0.0,
            )

            def on_page_ready(result, task) -> None:
                """Publish question_extraction_requested for each extracted page."""
                self._kafka_producer.send(
                    key=None,
                    value={
                        "event_type": "question_extraction_requested",
                        "page_id": str(result.page.id),
                        "task_id": str(task.id),
                        "is_final_page": result.is_final,
                    },
                    topic="question_extraction_requested",
                )
                logger.info(
                    "Published question_extraction_requested for page %s (final=%s)",
                    result.page.id,
                    result.is_final,
                )

            # Extract document pages
            task = await self._service.extract_document(
                document_id=document_id,
                local_pdf_path=str(local_pdf_path),
                s3_prefix="document-extraction",
                on_page_ready=on_page_ready,
            )
            logger.info(
                "Document extraction complete for document %s, task %s",
                document_id,
                task.id,
            )

        except Exception as exc:
            logger.error(
                "Document extraction failed for document %s: %s",
                document_id,
                exc,
                exc_info=True,
            )
            raise

        finally:
            if temp_dir and temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
