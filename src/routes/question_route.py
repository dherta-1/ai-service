from uuid import UUID
from fastapi import APIRouter, HTTPException, Query
from src.services.question_service import QuestionService
from src.shared.response.response_models import (
    create_response,
    create_paginated_response,
)
from src.shared.helpers.dto_utils import to_dict

router = APIRouter()
service = QuestionService()


def _serialize_questions(questions: list) -> list:
    """Convert list of Peewee models to list of dicts"""
    return [to_dict(q) for q in questions]


@router.get("/taxonomy/search")
async def get_questions_by_taxonomy(
    subject: str = Query(None),
    topic: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
):
    """Get questions by subject and/or topic"""
    if not subject and not topic:
        raise HTTPException(
            status_code=400,
            detail="At least one of 'subject' or 'topic' must be provided",
        )
    questions = service.get_by_subject_and_topic(subject, topic)
    start = (page - 1) * page_size
    end = start + page_size
    paginated_questions = _serialize_questions(questions[start:end])
    return create_paginated_response(
        data=paginated_questions,
        total=len(questions),
        page=page,
        per_page=page_size,
        message="Questions retrieved successfully",
    )


@router.get("/page/{page_id}")
async def get_questions_by_page(
    page_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
):
    """Get questions by page ID"""
    questions = service.get_by_page(page_id)
    start = (page - 1) * page_size
    end = start + page_size
    paginated_questions = _serialize_questions(questions[start:end])
    return create_paginated_response(
        data=paginated_questions,
        total=len(questions),
        page=page,
        per_page=page_size,
        message="Questions retrieved successfully",
    )


@router.get("/type/{question_type}")
async def get_questions_by_type(
    question_type: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
):
    """Get questions by type"""
    questions = service.get_by_question_type(question_type)
    start = (page - 1) * page_size
    end = start + page_size
    paginated_questions = _serialize_questions(questions[start:end])
    return create_paginated_response(
        data=paginated_questions,
        total=len(questions),
        page=page,
        per_page=page_size,
        message="Questions retrieved successfully",
    )


@router.get("/{question_id}")
async def get_question(question_id: UUID):
    """Get a question by ID"""
    question = service.get_by_id(question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    return create_response(
        data=to_dict(question), message="Question retrieved successfully"
    )


@router.get("")
async def list_questions(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
):
    """List all questions with pagination"""
    questions, total = service.get_all_paginated(page, page_size)
    return create_paginated_response(
        data=_serialize_questions(questions),
        total=total,
        page=page,
        per_page=page_size,
        message="Questions retrieved successfully",
    )
