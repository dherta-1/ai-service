from __future__ import annotations

from typing import List, Optional, Tuple
from uuid import UUID
import asyncio
from fastapi import UploadFile

from src.repos.document_repo import DocumentRepository
from src.repos.file_metadata_repo import FileMetadataRepository
from src.shared.base.base_service import BaseService
from src.shared.constants.general import Status
from src.lib.s3_client import get_s3_client
from src.settings import get_settings


class DocumentService(BaseService):

    def __init__(self):
        super().__init__(DocumentRepository())
        self._file_meta_repo = FileMetadataRepository()

    def get_by_id(self, document_id: UUID):
        return self.repo.get_by_id(document_id)

    def get_all(self):
        return self.repo.get_all()

    def get_all_paginated(self, page: int = 1, page_size: int = 10):
        return self.repo.get_all_paginated(page, page_size)

    def get_all_paginated_by_user(self, uploaded_by_id: UUID, page: int = 1, page_size: int = 10):
        return self.repo.get_all_paginated_by_user(uploaded_by_id, page, page_size)

    def get_by_file_id(self, file_id: str):
        return self.repo.get_by_file_id(file_id)

    def get_by_name(self, name: str):
        return self.repo.get_by_name(name)

    def get_by_status(self, status: str):
        return self.repo.get_by_status(status)

    def get_pending(self):
        return self.repo.get_pending()

    async def upload_and_create_metadata(
        self, file: UploadFile, s3_prefix: str = "documents", uploaded_by_id: UUID = None
    ):
        """Stage 1: Upload file to S3 and create document metadata."""
        if not file.filename:
            raise ValueError("Missing filename")

        settings = get_settings()
        s3_client = get_s3_client(settings)
        s3_bucket = getattr(settings, "aws_s3_bucket", None)

        # Read file content
        content = await file.read()

        # Upload to S3
        s3_key = f"{s3_prefix}/{file.filename}"
        if s3_bucket:
            await asyncio.to_thread(
                s3_client.upload_file_bytes,
                content,
                s3_bucket,
                s3_key,
                file.content_type or "application/octet-stream",
            )

        # Create file_metadata record
        fm = await asyncio.to_thread(
            self._file_meta_repo.create,
            name=file.filename,
            path=s3_key,
            size=len(content),
            mime_type=file.content_type or "application/octet-stream",
            object_key=s3_key,
        )

        # Create document record (PENDING status)
        document = await asyncio.to_thread(
            self.repo.create,
            name=file.filename,
            file_id=str(fm.id),
            status=Status.PENDING.value,
            progress=0.0,
            uploaded_by_id=uploaded_by_id,
        )

        return document

    async def batch_upload_and_create_metadata(
        self, files: List[UploadFile], s3_prefix: str = "documents", uploaded_by_id: UUID = None
    ) -> Tuple[List[dict], List[dict]]:
        """Batch upload multiple files to S3 and create document metadata.

        Returns tuple of (successful_uploads, failed_uploads).
        Each item has: document_id, file_id, name, status, and error (if failed).
        """
        if not files:
            raise ValueError("No files provided")

        successful_uploads = []
        failed_uploads = []

        # Process uploads concurrently
        tasks = [
            self.upload_and_create_metadata(file, s3_prefix, uploaded_by_id)
            for file in files
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for idx, result in enumerate(results):
            filename = files[idx].filename or f"file_{idx}"

            if isinstance(result, Exception):
                failed_uploads.append({
                    "filename": filename,
                    "error": str(result),
                })
            else:
                successful_uploads.append({
                    "document_id": str(result.id),
                    "file_id": str(result.file_id),
                    "name": result.name,
                    "status": result.status,
                })

        return successful_uploads, failed_uploads
