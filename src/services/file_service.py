from __future__ import annotations

from typing import Optional, Any
from uuid import UUID
import logging

from src.repos.file_metadata_repo import FileMetadataRepository
from src.shared.base.base_service import BaseService
from src.lib.s3_client import get_s3_client
from src.settings import get_settings

logger = logging.getLogger(__name__)


class FileService(BaseService):
    """File management service for document files stored in S3."""

    def __init__(self):
        super().__init__(FileMetadataRepository())
        settings = get_settings()
        self._s3_client = get_s3_client(settings)
        self._s3_bucket = getattr(settings, "aws_s3_bucket", None)
        self._s3_region = getattr(settings, "aws_region", None)

    def get_by_id(self, file_id: UUID) -> Optional[Any]:
        """Get file metadata by ID."""
        return self.repo.get_by_id(file_id)

    def get_by_object_key(self, object_key: str) -> Optional[Any]:
        """Get file metadata by S3 object key."""
        return self.repo.get_by_object_key(object_key)

    def get_by_path(self, path: str) -> Optional[Any]:
        """Get file metadata by path."""
        return self.repo.get_by_path(path)

    def get_presigned_url(
        self, file_id: UUID, expires_in: int = 3600
    ) -> Optional[str]:
        """Get presigned URL for downloading a file from S3.

        Args:
            file_id: UUID of the file metadata
            expires_in: Expiration time in seconds (default 1 hour)

        Returns:
            Presigned URL string or None if file not found
        """
        file_metadata = self.get_by_id(file_id)
        if not file_metadata:
            logger.warning("File metadata not found for ID: %s", file_id)
            return None

        if not file_metadata.object_key:
            logger.warning("No S3 object key for file: %s", file_id)
            return None

        if not self._s3_bucket:
            logger.warning("S3 bucket not configured")
            return None

        try:
            url = self._s3_client.generate_presigned_url(
                client_method="get_object",
                Params={
                    "Bucket": self._s3_bucket,
                    "Key": file_metadata.object_key,
                },
                ExpiresIn=expires_in,
            )
            logger.info("Generated presigned URL for file: %s", file_id)
            return url
        except Exception as e:
            logger.error("Failed to generate presigned URL for file %s: %s", file_id, e)
            return None

    def get_file_with_url(
        self, file_id: UUID, expires_in: int = 3600
    ) -> Optional[dict]:
        """Get file metadata with presigned download URL.

        Returns:
            Dict with file metadata and presigned_url, or None if not found
        """
        file_metadata = self.get_by_id(file_id)
        if not file_metadata:
            return None

        presigned_url = self.get_presigned_url(file_id, expires_in)

        return {
            "id": str(file_metadata.id),
            "name": file_metadata.name,
            "path": file_metadata.path,
            "size": file_metadata.size,
            "mime_type": file_metadata.mime_type,
            "object_key": file_metadata.object_key,
            "presigned_url": presigned_url,
            "presigned_url_expires_in": expires_in,
            "created_at": file_metadata.created_at,
            "updated_at": file_metadata.updated_at,
        }

    def get_batch_urls(
        self, file_ids: list[UUID], expires_in: int = 3600
    ) -> dict[str, dict]:
        """Get presigned URLs for multiple files.

        Args:
            file_ids: List of file UUIDs
            expires_in: Expiration time in seconds

        Returns:
            Dict mapping file_id (as string) to {presigned_url, expires_in}
        """
        result = {}
        for file_id in file_ids:
            presigned_url = self.get_presigned_url(file_id, expires_in)
            if presigned_url:
                result[str(file_id)] = {
                    "presigned_url": presigned_url,
                    "presigned_url_expires_in": expires_in,
                }
        return result
