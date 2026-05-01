from uuid import UUID
from typing import Optional
from fastapi import APIRouter, Query, Body, Depends

from src.container import get_di_container
from src.shared.response.exception_handler import NotFoundException
from src.services.question_service import QuestionService
from src.dtos.question.res import QuestionListResponse, QuestionDetailResponse
from src.shared.helpers.dto_utils import to_dict
from src.shared.response.response_models import (
    create_response,
    create_paginated_response,
)

router = APIRouter()


def get_question_service() -> QuestionService:
    return get_di_container().resolve(QuestionService)


@router.get("/page/{page_id}")
async def get_questions_by_page(
    page_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    service: QuestionService = Depends(get_question_service),
):
    """Get top-level questions for a page."""
    questions = service.get_by_page(page_id)
    offset = (page - 1) * page_size
    return create_paginated_response(
        data=[QuestionListResponse.model_validate(q).model_dump() for q in questions[offset : offset + page_size]],
        total=len(questions),
        page=page,
        per_page=page_size,
        message="Questions retrieved successfully",
    )


@router.get("/{question_id}")
async def get_question(
    question_id: UUID,
    service: QuestionService = Depends(get_question_service),
):
    """Get a question with its answers and sub-questions."""
    question, answers = service.get_with_answers(question_id)
    if not question:
        raise NotFoundException("Question not found")

    sub_questions = service.get_sub_questions(question_id)
    data = QuestionDetailResponse.model_validate(question).model_dump()
    data["answers"] = [to_dict(a) for a in answers]
    data["sub_questions"] = [QuestionListResponse.model_validate(sq).model_dump() for sq in sub_questions]
    return create_response(data=data, message="Question retrieved successfully")


@router.get("")
async def list_questions(
    search: Optional[str] = Query(None),
    subject: Optional[str] = Query(None),
    topic: Optional[str] = Query(None),
    difficulty: Optional[str] = Query(None),
    question_type: Optional[str] = Query(None),
    status: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    service: QuestionService = Depends(get_question_service),
):
    """List questions with optional filters and search.

    Query parameters:
    - search: Full-text search in question content
    - subject: Filter by subject code
    - topic: Filter by topic code
    - difficulty: Filter by difficulty level
    - question_type: Filter by question type (multiple_choice, true_false, etc.)
    - status: Filter by status (0=pending, 1=approved, 2=rejected)
    """
    questions, total = service.find_filtered(
        search_query=search,
        subject=subject,
        topic=topic,
        difficulty=difficulty,
        question_type=question_type,
        status=status,
        page=page,
        page_size=page_size,
    )
    return create_paginated_response(
        data=[QuestionListResponse.model_validate(q).model_dump() for q in questions],
        total=total,
        page=page,
        per_page=page_size,
        message="Questions retrieved successfully",
    )


@router.patch("/{question_id}/status")
async def update_question_status(
    question_id: UUID,
    status: int = Query(..., ge=0, le=2),
    service: QuestionService = Depends(get_question_service),
):
    """Update question approval status. 0=pending, 1=approved, 2=rejected."""
    question = service.get_by_id(question_id)
    if not question:
        raise NotFoundException("Question not found")
    service.update_status(question_id, status)
    return create_response(
        data={"id": str(question_id), "status": status},
        message="Question status updated",
    )


@router.post("/{question_id}/review")
async def submit_question_review(
    question_id: UUID,
    body: dict = Body(...),
    service: QuestionService = Depends(get_question_service),
):
    """Submit manual corrections for a question's answers."""
    question = service.get_by_id(question_id)
    if not question:
        raise NotFoundException("Question not found")

    answers = body.get("answers")
    if answers is not None:
        service.update_answers(question_id, answers)

    return create_response(
        data={"id": str(question_id), "updated": True},
        message="Question review submitted",
    )
