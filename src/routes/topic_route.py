from fastapi import APIRouter, Query, Depends, status
from typing import Optional

from src.container import get_di_container
from src.services.topic_service import TopicService
from src.shared.response.response_models import create_response, create_paginated_response

router = APIRouter()


def get_topic_service() -> TopicService:
    return get_di_container().get("topic_service")


@router.get("", response_model=dict, status_code=status.HTTP_200_OK)
async def list_topics(
    query: Optional[str] = Query(None, description="Search query"),
    subject_code: Optional[str] = Query(None, description="Filter by subject code"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=100, description="Items per page"),
    service: TopicService = Depends(get_topic_service),
):
    """List topics with optional search, subject filter, and pagination

    - **query**: Search by topic name, code, or Vietnamese name
    - **subject_code**: Filter topics by parent subject code
    - **page**: Page number (1-indexed)
    - **page_size**: Number of items per page (1-100)
    """
    topics, total_count = service.search(
        query=query,
        subject_code=subject_code,
        page=page,
        page_size=page_size
    )
    response = create_paginated_response(
        data=[t.model_dump() for t in topics],
        total=total_count,
        page=page,
        per_page=page_size,
        message="Topics retrieved successfully",
    )
    return response.model_dump(mode="json")


@router.get("/subject/{subject_code}", response_model=dict, status_code=status.HTTP_200_OK)
async def get_topics_by_subject(
    subject_code: str,
    service: TopicService = Depends(get_topic_service),
):
    """Get all topics for a specific subject"""
    topics = service.get_by_subject(subject_code)
    response = create_response(
        data=[t.model_dump() for t in topics],
        message=f"Topics for subject '{subject_code}' retrieved successfully",
    )
    return response.model_dump(mode="json")


@router.get("/all", response_model=dict, status_code=status.HTTP_200_OK)
async def get_all_topics(
    service: TopicService = Depends(get_topic_service),
):
    """Get all topics without pagination"""
    topics = service.get_all()
    response = create_response(
        data=[t.model_dump() for t in topics],
        message="All topics retrieved successfully",
    )
    return response.model_dump(mode="json")


@router.post("/batch/codes", response_model=dict, status_code=status.HTTP_200_OK)
async def get_topics_by_codes(
    codes: list[str],
    service: TopicService = Depends(get_topic_service),
):
    """Get multiple topics by their codes"""
    topics = [service.get_by_code(code) for code in codes]
    topics = [t for t in topics if t is not None]
    response = create_response(
        data=[t.model_dump() for t in topics],
        message="Topics retrieved successfully",
    )
    return response.model_dump(mode="json")


@router.get("/{code}", response_model=dict, status_code=status.HTTP_200_OK)
async def get_topic_by_code(
    code: str,
    service: TopicService = Depends(get_topic_service),
):
    """Get a topic by its code"""
    topic = service.get_by_code(code)
    if not topic:
        return create_response(data=None, message="Topic not found").model_dump(mode="json")
    response = create_response(
        data=topic.model_dump(),
        message="Topic retrieved successfully",
    )
    return response.model_dump(mode="json")
