from uuid import UUID
from fastapi import APIRouter, HTTPException, Query
from src.shared.helpers.dto_utils import to_dict
from src.services.page_service import PageService
from src.shared.response.response_models import (
    create_response,
    create_paginated_response,
)

router = APIRouter()
service = PageService()


def _serialize_pages(pages: list) -> list:
    """Convert list of Peewee models to list of dicts"""
    return [to_dict(p) for p in pages]


@router.get("/document/{document_id}/page/{page_number}")
async def get_page_by_document_and_number(document_id: UUID, page_number: int):
    """Get a specific page by document ID and page number"""
    page = service.get_by_document_and_page_number(document_id, page_number)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    return create_response(data=to_dict(page), message="Page retrieved successfully")


@router.get("/document/{document_id}")
async def get_pages_by_document(
    document_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
):
    """Get pages by document ID"""
    pages = service.get_by_document(document_id)
    start = (page - 1) * page_size
    end = start + page_size
    paginated_pages = _serialize_pages(pages[start:end])
    return create_paginated_response(
        data=paginated_pages,
        total=len(pages),
        page=page,
        per_page=page_size,
        message="Pages retrieved successfully",
    )


@router.get("/{page_id}")
async def get_page(page_id: UUID):
    """Get a page by ID"""
    page = service.get_by_id(page_id)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    return create_response(data=to_dict(page), message="Page retrieved successfully")


@router.get("")
async def list_pages(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
):
    """List all pages with pagination"""
    pages, total = service.get_all_paginated(page, page_size)
    return create_paginated_response(
        data=_serialize_pages(pages),
        total=total,
        page=page,
        per_page=page_size,
        message="Pages retrieved successfully",
    )
