from fastapi import APIRouter, Query, Depends, status
from typing import Optional

from src.container import get_di_container
from src.services.subject_service import SubjectService
from src.dtos.subject.req import SubjectListQuery
from src.dtos.subject.res import SubjectResponse
from src.shared.response.response_models import create_response, create_paginated_response

router = APIRouter()


def get_subject_service() -> SubjectService:
    return get_di_container().get("subject_service")


@router.get("", response_model=dict, status_code=status.HTTP_200_OK)
async def list_subjects(
    query: Optional[str] = Query(None, description="Search query"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=100, description="Items per page"),
    service: SubjectService = Depends(get_subject_service),
):
    """List subjects with optional search and pagination

    - **query**: Search by subject name, code, or Vietnamese name
    - **page**: Page number (1-indexed)
    - **page_size**: Number of items per page (1-100)
    """
    subjects, total_count = service.search(
        query=query,
        page=page,
        page_size=page_size
    )
    response = create_paginated_response(
        data=[s.model_dump() for s in subjects],
        total=total_count,
        page=page,
        per_page=page_size,
        message="Subjects retrieved successfully",
    )
    return response.model_dump(mode="json")


@router.get("/all", response_model=dict, status_code=status.HTTP_200_OK)
async def get_all_subjects(
    service: SubjectService = Depends(get_subject_service),
):
    """Get all subjects without pagination"""
    subjects = service.get_all()
    response = create_response(
        data=[s.model_dump() for s in subjects],
        message="All subjects retrieved successfully",
    )
    return response.model_dump(mode="json")
