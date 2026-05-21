from uuid import UUID
from fastapi import APIRouter, Query, UploadFile, File, Form, Depends, status, Request

from src.container import get_di_container
from src.shared.response.exception_handler import NotFoundException, BadRequestException, ForbiddenException
from src.services.document_service import DocumentService
from src.services.question_service import QuestionService
from src.shared.helpers.dto_utils import to_dict
from src.shared.response.response_models import (
    create_response,
    create_paginated_response,
)
from src.shared.auth_deps import get_current_user, require_admin
from src.entities.user import User
from src.shared.constants.user import Role
from src.shared.logger.audit_logger import log_audit
from src.shared.constants.audit_log import ActionType, ActorType, EntityType

router = APIRouter()


def get_document_service() -> DocumentService:
    return get_di_container().resolve(DocumentService)


def get_question_service() -> QuestionService:
    return get_di_container().resolve(QuestionService)


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    s3_prefix: str = Form(default="documents"),
    service: DocumentService = Depends(get_document_service),
    current_user: User = Depends(get_current_user),
    request: Request = None,
):
    """Stage 1: Upload document file to S3 and create metadata (no processing).

    Returns document_id which can later be queued for extraction via /ai/queue.
    Requires authentication - sets uploaded_by_id to current user.
    """
    if not file.filename:
        raise BadRequestException("Missing filename")

    try:
        document = await service.upload_and_create_metadata(
            file=file,
            s3_prefix=s3_prefix,
            uploaded_by_id=current_user.id,
        )

        log_audit(
            actor_type=ActorType.user,
            entity_type=EntityType.document,
            action_type=ActionType.CREATE,
            actor_id=current_user.id,
            entity_id=document.id,
            before_data=None,
            after_data={"name": document.name, "status": document.status},
            request_ip=request.client.host if request else None,
        )

        return create_response(
            data={
                "document_id": str(document.id),
                "file_id": str(document.file_id),
                "name": document.name,
                "status": document.status,
            },
            message="Document uploaded successfully",
        )
    except Exception as e:
        raise BadRequestException(f"Upload failed: {e}") from e


@router.post("/batch-upload", status_code=status.HTTP_201_CREATED)
async def batch_upload_documents(
    files: list[UploadFile] = File(...),
    s3_prefix: str = Form(default="documents"),
    service: DocumentService = Depends(get_document_service),
    current_user: User = Depends(get_current_user),
    request: Request = None,
):
    """Batch upload multiple document files to S3 with metadata creation.

    Processes all files concurrently. Returns successful uploads and any failures.
    Requires authentication - sets uploaded_by_id to current user for all uploads.

    Response includes:
    - successful: Array of uploaded documents with document_id, file_id, name, status
    - failed: Array of failed uploads with filename and error reason
    - total_succeeded: Number of successful uploads
    - total_failed: Number of failed uploads
    """
    if not files or len(files) == 0:
        raise BadRequestException("No files provided")

    if len(files) > 50:
        raise BadRequestException("Maximum 50 files per batch upload")

    try:
        successful, failed = await service.batch_upload_and_create_metadata(
            files=files,
            s3_prefix=s3_prefix,
            uploaded_by_id=current_user.id,
        )

        if len(successful) > 0:
            log_audit(
                actor_type=ActorType.user,
                entity_type=EntityType.document,
                action_type=ActionType.CREATE,
                actor_id=current_user.id,
                entity_id=None,
                before_data=None,
                after_data={"count": len(successful), "s3_prefix": s3_prefix},
                request_ip=request.client.host if request else None,
            )

        return create_response(
            data={
                "successful": successful,
                "failed": failed,
                "total_succeeded": len(successful),
                "total_failed": len(failed),
            },
            message=f"Batch upload completed: {len(successful)} succeeded, {len(failed)} failed",
        )
    except ValueError as e:
        raise BadRequestException(str(e)) from e
    except Exception as e:
        raise BadRequestException(f"Batch upload failed: {e}") from e


# @router.get("/file/{file_id}")
# async def get_document_by_file_id(
#     file_id: str,
#     service: DocumentService = Depends(get_document_service),
# ):
#     """Get a document by file ID."""
#     document = service.get_by_file_id(file_id)
#     if not document:
#         raise NotFoundException("Document not found")
#     return create_response(data=to_dict(document), message="Document retrieved successfully")




# @router.get("/{document_id}/questions")
# async def get_document_questions(
#     document_id: UUID,
#     page: int = Query(1, ge=1),
#     page_size: int = Query(10, ge=1, le=100),
#     doc_service: DocumentService = Depends(get_document_service),
#     question_service: QuestionService = Depends(get_question_service),
#     current_user: User = Depends(get_current_user),
# ):
#     """Get extracted questions for a document."""
#     document = doc_service.get_by_id(document_id)
#     if not document:
#         raise NotFoundException("Document not found")

#     # Check authorization: admin or document owner
#     if current_user.role != Role.admin.value and document.uploaded_by_id != current_user.id:
#         raise ForbiddenException("You do not have permission to access this document")

#     questions = question_service.get_by_document(document_id)
#     offset = (page - 1) * page_size
#     total = question_service.count_by_document(document_id)
#     return create_paginated_response(
#         data=[to_dict(q) for q in questions[offset : offset + page_size]],
#         total=total,
#         page=page,
#         per_page=page_size,
#         message="Questions retrieved successfully",
#     )


@router.get("/{document_id}")
async def get_document(
    document_id: UUID,
    service: DocumentService = Depends(get_document_service),
    current_user: User = Depends(get_current_user),
):
    """Get a single document by ID."""
    document = service.get_by_id(document_id)
    if not document:
        raise NotFoundException("Document not found")

    if current_user.role != Role.admin.value and document.uploaded_by_id != current_user.id:
        raise ForbiddenException("You do not have permission to access this document")

    return create_response(data=to_dict(document), message="Document retrieved successfully")


@router.get("")
async def list_all_documents(
    status: str = Query(None, description="Filter by document status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    service: DocumentService = Depends(get_document_service),
    current_user: User = Depends(get_current_user),
):
    """List all documents (admin only) with optional status filter."""
    if current_user.role != Role.admin.value:
        raise ForbiddenException("Only admins can list all documents")

    if status:
        documents = service.get_by_status(status)
    else:
        documents = service.get_all()

    offset = (page - 1) * page_size
    total = len(documents)

    return create_paginated_response(
        data=[to_dict(d) for d in documents[offset : offset + page_size]],
        total=total,
        page=page,
        per_page=page_size,
        message="Documents retrieved successfully",
    )


@router.get("/user/documents")
async def list_user_documents(
    status: str = Query(None, description="Filter by document status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    service: DocumentService = Depends(get_document_service),
    current_user: User = Depends(get_current_user),
):
    """List current user's documents with optional status filter."""
    if status:
        # Get all documents for user, then filter by status
        all_documents = service.get_all_paginated_by_user(current_user.id, 1, 10000)[0]
        documents = [d for d in all_documents if d.status == status]
    else:
        documents, _ = service.get_all_paginated_by_user(current_user.id, 1, 10000)

    offset = (page - 1) * page_size
    total = len(documents)

    return create_paginated_response(
        data=[to_dict(d) for d in documents[offset : offset + page_size]],
        total=total,
        page=page,
        per_page=page_size,
        message="Documents retrieved successfully",
    )
