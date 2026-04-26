from uuid import UUID
from fastapi import APIRouter, HTTPException, Query
from src.shared.helpers.dto_utils import to_dict
from src.services.document_service import DocumentService
from src.shared.response.response_models import (
    create_response,
    create_paginated_response,
)

router = APIRouter()
service = DocumentService()


def _serialize_documents(documents: list) -> list:
    """Convert list of Peewee models to list of dicts"""
    return [to_dict(d) for d in documents]


@router.get("/pending")
async def get_pending_documents():
    """Get all pending documents"""
    documents = service.get_pending()
    return create_response(
        data=_serialize_documents(documents),
        message="Pending documents retrieved successfully",
    )


@router.get("/file/{file_id}")
async def get_document_by_file_id(file_id: str):
    """Get a document by file ID"""
    document = service.get_by_file_id(file_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return create_response(
        data=to_dict(document), message="Document retrieved successfully"
    )


@router.get("/status/{status}")
async def get_documents_by_status(
    status: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
):
    """Get documents by status"""
    documents = service.get_by_status(status)
    start = (page - 1) * page_size
    end = start + page_size
    paginated_documents = _serialize_documents(documents[start:end])
    return create_paginated_response(
        data=paginated_documents,
        total=len(documents),
        page=page,
        per_page=page_size,
        message="Documents retrieved successfully",
    )


@router.get("/{document_id}")
async def get_document(document_id: UUID):
    """Get a document by ID"""
    document = service.get_by_id(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return create_response(
        data=to_dict(document), message="Document retrieved successfully"
    )


@router.get("")
async def list_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
):
    """List all documents with pagination"""
    documents, total = service.get_all_paginated(page, page_size)
    return create_paginated_response(
        data=_serialize_documents(documents),
        total=total,
        page=page,
        per_page=page_size,
        message="Documents retrieved successfully",
    )
