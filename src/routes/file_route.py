from uuid import UUID
from fastapi import APIRouter, Depends, Query

from src.container import get_di_container
from src.services.file_service import FileService
from src.shared.response.exception_handler import NotFoundException
from src.shared.response.response_models import create_response

router = APIRouter()


def get_file_service() -> FileService:
    return get_di_container().resolve(FileService)


@router.post("/batch/urls")
async def get_batch_file_urls(
    file_ids: list[UUID],
    expires_in: int = Query(3600, ge=60, le=604800, description="URL expiration in seconds (1 min - 7 days)"),
    service: FileService = Depends(get_file_service),
):
    """Get presigned URLs for multiple files in one request.

    Useful for efficiently fetching URLs for multiple images or documents.
    Returns a map of file_id to {presigned_url, expires_in}.
    """
    if not file_ids:
        return create_response(
            data={},
            message="No file IDs provided",
        )

    urls_map = service.get_batch_urls(file_ids, expires_in=expires_in)

    return create_response(
        data=urls_map,
        message=f"Generated {len(urls_map)} presigned URLs",
    )

@router.get("/{file_id}")
async def get_file(
    file_id: UUID,
    expires_in: int = Query(3600, ge=60, le=604800, description="URL expiration in seconds (1 min - 7 days)"),
    service: FileService = Depends(get_file_service),
):
    """Get file metadata with presigned download URL.

    The presigned URL allows temporary direct access to the file in S3.
    Default expiration is 1 hour; can be customized via expires_in query param.
    """
    file_data = service.get_file_with_url(file_id, expires_in=expires_in)
    if not file_data:
        raise NotFoundException("File not found")

    return create_response(
        data=file_data,
        message="File retrieved successfully",
    )


@router.get("/{file_id}/url")
async def get_file_download_url(
    file_id: UUID,
    expires_in: int = Query(3600, ge=60, le=604800, description="URL expiration in seconds (1 min - 7 days)"),
    service: FileService = Depends(get_file_service),
):
    """Get only the presigned download URL for a file.

    Useful when you just need the URL without full file metadata.
    """
    file_metadata = service.get_by_id(file_id)
    if not file_metadata:
        raise NotFoundException("File not found")

    presigned_url = service.get_presigned_url(file_id, expires_in=expires_in)
    if not presigned_url:
        raise NotFoundException("Could not generate presigned URL for file")

    return create_response(
        data={
            "file_id": str(file_id),
            "presigned_url": presigned_url,
            "presigned_url_expires_in": expires_in,
        },
        message="Presigned URL generated successfully",
    )



