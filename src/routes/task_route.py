from uuid import UUID
from fastapi import APIRouter, Depends, Query

from src.container import get_di_container
from src.services.task_service import TaskService
from src.services.document_service import DocumentService
from src.shared.response.exception_handler import NotFoundException, ForbiddenException
from src.shared.helpers.dto_utils import to_dict
from src.shared.response.response_models import create_response, create_paginated_response
from src.shared.auth_deps import get_current_user
from src.entities.user import User
from src.shared.constants.user import Role

router = APIRouter()


def get_task_service() -> TaskService:
    return get_di_container().resolve(TaskService)


def get_document_service() -> DocumentService:
    return get_di_container().resolve(DocumentService)


@router.get("/{document_id}/tasks/{task_id}")
async def get_task_by_id(
    document_id: UUID,
    task_id: UUID,
    task_service: TaskService = Depends(get_task_service),
    doc_service: DocumentService = Depends(get_document_service),
    current_user: User = Depends(get_current_user),
):
    """Get a specific extraction task for a document."""
    document = doc_service.get_by_id(document_id)
    if not document:
        raise NotFoundException("Document not found")

    if current_user.role != Role.admin.value and document.uploaded_by_id != current_user.id:
        raise ForbiddenException("You do not have permission to access this document")

    task = task_service.get_by_id(task_id)
    if not task:
        raise NotFoundException("Task not found")

    return create_response(data=to_dict(task), message="Task retrieved successfully")


@router.get("/{document_id}/tasks")
async def list_document_tasks(
    document_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    task_service: TaskService = Depends(get_task_service),
    doc_service: DocumentService = Depends(get_document_service),
    current_user: User = Depends(get_current_user),
):
    """List all extraction tasks for a document."""
    document = doc_service.get_by_id(document_id)
    if not document:
        raise NotFoundException("Document not found")

    if current_user.role != Role.admin.value and document.uploaded_by_id != current_user.id:
        raise ForbiddenException("You do not have permission to access this document")

    tasks = task_service.get_by_document(document_id)
    offset = (page - 1) * page_size
    total = len(tasks)

    return create_paginated_response(
        data=[to_dict(t) for t in tasks[offset : offset + page_size]],
        total=total,
        page=page,
        per_page=page_size,
        message="Tasks retrieved successfully",
    )


@router.get("")
async def list_tasks_by_status(
    status: str = Query(..., description="Task status to filter by"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    task_service: TaskService = Depends(get_task_service),
    current_user: User = Depends(get_current_user),
):
    """List tasks by status (admin only)."""
    if current_user.role != Role.admin.value:
        raise ForbiddenException("Only admins can list tasks by status")

    tasks = task_service.get_by_status(status)
    offset = (page - 1) * page_size
    total = len(tasks)

    return create_paginated_response(
        data=[to_dict(t) for t in tasks[offset : offset + page_size]],
        total=total,
        page=page,
        per_page=page_size,
        message="Tasks retrieved successfully",
    )
