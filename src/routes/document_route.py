from uuid import UUID
from fastapi import APIRouter, Query, UploadFile, File, Form, Depends, status

from src.container import get_di_container
from src.shared.response.exception_handler import NotFoundException, BadRequestException
from src.services.document_service import DocumentService
from src.services.question_service import QuestionService
from src.shared.helpers.dto_utils import to_dict
from src.shared.response.response_models import (
    create_response,
    create_paginated_response,
)

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
):
    """Stage 1: Upload document file to S3 and create metadata (no processing).

    Returns document_id which can later be queued for extraction via /ai/queue.
    """
    if not file.filename:
        raise BadRequestException("Missing filename")

    try:
        document = await service.upload_and_create_metadata(
            file=file,
            s3_prefix=s3_prefix,
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


@router.get("/pending")
async def get_pending_documents(service: DocumentService = Depends(get_document_service)):
    documents = service.get_pending()
    return create_response(
        data=[to_dict(d) for d in documents],
        message="Pending documents retrieved successfully",
    )


@router.get("/file/{file_id}")
async def get_document_by_file_id(
    file_id: str,
    service: DocumentService = Depends(get_document_service),
):
    document = service.get_by_file_id(file_id)
    if not document:
        raise NotFoundException("Document not found")
    return create_response(data=to_dict(document), message="Document retrieved successfully")


@router.get("/status/{status}")
async def get_documents_by_status(
    status: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    service: DocumentService = Depends(get_document_service),
):
    documents = service.get_by_status(status)
    offset = (page - 1) * page_size
    return create_paginated_response(
        data=[to_dict(d) for d in documents[offset : offset + page_size]],
        total=len(documents),
        page=page,
        per_page=page_size,
        message="Documents retrieved successfully",
    )


@router.get("/{document_id}/tasks/{task_id}")
async def get_task_progress(
    document_id: UUID,
    task_id: UUID,
    service: DocumentService = Depends(get_document_service),
):
    """Get extraction task progress for a document."""
    if not service.get_by_id(document_id):
        raise NotFoundException("Document not found")
    task = service.get_task(task_id)
    if not task:
        raise NotFoundException("Task not found")
    return create_response(data=to_dict(task), message="Task retrieved successfully")


@router.get("/{document_id}/tasks")
async def get_latest_task(
    document_id: UUID,
    service: DocumentService = Depends(get_document_service),
):
    """Get the latest extraction task for a document."""
    task = service.get_latest_task(document_id)
    if not task:
        raise NotFoundException("No task found for this document")
    return create_response(data=to_dict(task), message="Task retrieved successfully")


@router.get("/{document_id}/questions")
async def get_document_questions(
    document_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    doc_service: DocumentService = Depends(get_document_service),
    question_service: QuestionService = Depends(get_question_service),
):
    """Get extracted questions for a document."""
    document = doc_service.get_by_id(document_id)
    if not document:
        raise NotFoundException("Document not found")

    questions = question_service.get_by_document(document_id)
    offset = (page - 1) * page_size
    total = question_service.count_by_document(document_id)
    return create_paginated_response(
        data=[to_dict(q) for q in questions[offset : offset + page_size]],
        total=total,
        page=page,
        per_page=page_size,
        message="Questions retrieved successfully",
    )


@router.get("/{document_id}")
async def get_document(
    document_id: UUID,
    service: DocumentService = Depends(get_document_service),
):
    document = service.get_by_id(document_id)
    if not document:
        raise NotFoundException("Document not found")

    data = to_dict(document)
    task = service.get_latest_task(document_id)
    data["latest_task"] = to_dict(task) if task else None
    return create_response(data=data, message="Document retrieved successfully")


@router.get("")
async def list_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    service: DocumentService = Depends(get_document_service),
):
    documents, total = service.get_all_paginated(page, page_size)
    return create_paginated_response(
        data=[to_dict(d) for d in documents],
        total=total,
        page=page,
        per_page=page_size,
        message="Documents retrieved successfully",
    )
