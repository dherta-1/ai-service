from uuid import UUID
from fastapi import APIRouter, HTTPException, Query, Depends

from src.container import get_di_container
from src.services.page_service import PageService
from src.services.question_service import QuestionService
from src.shared.helpers.dto_utils import to_dict
from src.shared.response.response_models import (
    create_response,
    create_paginated_response,
)

router = APIRouter()


def get_page_service() -> PageService:
    return get_di_container().resolve(PageService)


def get_question_service() -> QuestionService:
    return get_di_container().resolve(QuestionService)


@router.get("/document/{document_id}/page/{page_number}")
async def get_page_by_document_and_number(
    document_id: UUID,
    page_number: int,
    service: PageService = Depends(get_page_service),
):
    page = service.get_by_document_and_page_number(document_id, page_number)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    return create_response(data=to_dict(page), message="Page retrieved successfully")


@router.get("/document/{document_id}")
async def get_pages_by_document(
    document_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    service: PageService = Depends(get_page_service),
):
    pages = service.get_by_document(document_id)
    offset = (page - 1) * page_size
    return create_paginated_response(
        data=[to_dict(p) for p in pages[offset : offset + page_size]],
        total=len(pages),
        page=page,
        per_page=page_size,
        message="Pages retrieved successfully",
    )


@router.get("/{page_id}/questions")
async def get_page_questions(
    page_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    page_service: PageService = Depends(get_page_service),
    question_service: QuestionService = Depends(get_question_service),
):
    """Get top-level questions for a specific page."""
    if not page_service.get_by_id(page_id):
        raise HTTPException(status_code=404, detail="Page not found")
    questions = question_service.get_by_page(page_id)
    offset = (page - 1) * page_size
    return create_paginated_response(
        data=[to_dict(q) for q in questions[offset : offset + page_size]],
        total=len(questions),
        page=page,
        per_page=page_size,
        message="Questions retrieved successfully",
    )


@router.get("/{page_id}")
async def get_page(
    page_id: UUID,
    service: PageService = Depends(get_page_service),
):
    page = service.get_by_id(page_id)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    return create_response(data=to_dict(page), message="Page retrieved successfully")


@router.get("")
async def list_pages(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    service: PageService = Depends(get_page_service),
):
    pages, total = service.get_all_paginated(page, page_size)
    return create_paginated_response(
        data=[to_dict(p) for p in pages],
        total=total,
        page=page,
        per_page=page_size,
        message="Pages retrieved successfully",
    )
