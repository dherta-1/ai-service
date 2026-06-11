from uuid import UUID
from typing import Optional
from fastapi import APIRouter, Query, Body, Depends, Request

from src.container import get_di_container
from src.shared.response.exception_handler import NotFoundException, BadRequestException
from src.services.question_service import QuestionService
from src.services.core.question_mutation_service import QuestionMutationService
from src.services.core.generate_answer_service import GenerateAnswerService
from src.dtos.question.req import CreateQuestionRequest, UpdateQuestionRequest, AcceptAnswerRequest
from src.dtos.question.res import (
    QuestionListResponse,
    QuestionDetailResponse,
    QuestionGroupResponse,
)
from src.shared.helpers.dto_utils import to_dict
from src.shared.response.response_models import (
    create_response,
    create_paginated_response,
)
from src.shared.auth_deps import get_current_user
from src.entities.user import User
from src.entities.question_group import QuestionGroup
from src.shared.logger.audit_logger import log_audit
from src.shared.constants.audit_log import ActionType, ActorType, EntityType
from src.shared.helpers.request_helper import get_client_ip
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


def get_question_service() -> QuestionService:
    return get_di_container().resolve(QuestionService)


def get_mutation_service() -> QuestionMutationService:
    return get_di_container().resolve(QuestionMutationService)


def get_generate_answer_service() -> GenerateAnswerService:
    return get_di_container().resolve(GenerateAnswerService)


@router.get("")
async def list_questions(
    search: Optional[str] = Query(None),
    subject: Optional[str] = Query(None),
    topic: Optional[str] = Query(None),
    difficulty: Optional[str] = Query(None),
    question_type: Optional[str] = Query(None),
    status: Optional[int] = Query(None),
    time_order: Optional[str] = Query("desc", pattern="^(asc|desc)$"),
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
    - time_order: Sort by created_at (asc|desc, default desc)
    """
    questions, total = service.find_filtered(
        search_query=search,
        subject=subject,
        topic=topic,
        difficulty=difficulty,
        question_type=question_type,
        status=status,
        time_order=time_order or "desc",
        page=page,
        page_size=page_size,
    )
    data = []
    for q in questions:
        q_data = QuestionListResponse.model_validate(q).model_dump()
        _, answers = service.get_with_answers(q.id)
        sub_questions = service.get_sub_questions(q.id)
        q_data["answers"] = [to_dict(a) for a in answers]
        q_data["sub_questions"] = [
            QuestionListResponse.model_validate(sq).model_dump() for sq in sub_questions
        ]
        data.append(q_data)
    return create_paginated_response(
        data=data,
        total=total,
        page=page,
        per_page=page_size,
        message="Questions retrieved successfully",
    )


@router.get("/my")
async def list_my_questions(
    search: Optional[str] = Query(None),
    subject: Optional[str] = Query(None),
    topic: Optional[str] = Query(None),
    difficulty: Optional[str] = Query(None),
    question_type: Optional[str] = Query(None),
    status: Optional[int] = Query(None),
    time_order: Optional[str] = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    service: QuestionService = Depends(get_question_service),
):
    """List questions belonging to the current user (via their question groups)."""
    questions, total = service.find_filtered_by_user(
        user_id=current_user.id,
        search_query=search,
        subject=subject,
        topic=topic,
        difficulty=difficulty,
        question_type=question_type,
        status=status,
        time_order=time_order or "desc",
        page=page,
        page_size=page_size,
    )
    data = []
    for q in questions:
        q_data = QuestionListResponse.model_validate(q).model_dump()
        _, answers = service.get_with_answers(q.id)
        sub_questions = service.get_sub_questions(q.id)
        q_data["answers"] = [to_dict(a) for a in answers]
        q_data["sub_questions"] = [
            QuestionListResponse.model_validate(sq).model_dump() for sq in sub_questions
        ]
        data.append(q_data)
    return create_paginated_response(
        data=data,
        total=total,
        page=page,
        per_page=page_size,
        message="My questions retrieved successfully",
    )


@router.get("/group/my")
async def list_my_question_groups(
    subject: Optional[str] = Query(None),
    topic: Optional[str] = Query(None),
    difficulty: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    current_user: User = Depends(get_current_user),
):
    """List question groups belonging to the current user."""
    query = QuestionGroup.select().where(QuestionGroup.from_user == current_user.id)
    if subject:
        query = query.where(QuestionGroup.subject == subject)
    if topic:
        query = query.where(QuestionGroup.topic == topic)
    if difficulty:
        query = query.where(QuestionGroup.difficulty == difficulty)
    total = query.count()
    offset = (page - 1) * page_size
    groups = list(query.offset(offset).limit(page_size))
    return create_paginated_response(
        data=[QuestionGroupResponse.model_validate(g).model_dump() for g in groups],
        total=total,
        page=page,
        per_page=page_size,
        message="My question groups retrieved successfully",
    )


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
    paginated_questions = questions[offset : offset + page_size]
    data = []
    for q in paginated_questions:
        q_data = QuestionListResponse.model_validate(q).model_dump()
        _, answers = service.get_with_answers(q.id)
        sub_questions = service.get_sub_questions(q.id)
        q_data["answers"] = [to_dict(a) for a in answers]
        q_data["sub_questions"] = [
            QuestionListResponse.model_validate(sq).model_dump() for sq in sub_questions
        ]
        data.append(q_data)
    return create_paginated_response(
        data=data,
        total=len(questions),
        page=page,
        per_page=page_size,
        message="Questions retrieved successfully",
    )


@router.patch("/batch/status")
async def batch_update_question_status(
    body: dict = Body(...),
    service: QuestionService = Depends(get_question_service),
    request: Request = None,
):
    """Batch update question approval status for multiple questions.

    Request body:
    {
        "question_ids": ["uuid1", "uuid2", ...],
        "status": 0|1|2
    }

    Returns updated count and any failed IDs.
    """
    question_ids = body.get("question_ids", [])
    status = body.get("status")

    if not isinstance(question_ids, list) or not question_ids:
        raise ValueError("question_ids must be a non-empty list")
    if status is None or not isinstance(status, int) or status < 0 or status > 2:
        raise ValueError("status must be 0, 1, or 2")

    try:
        uuids = [UUID(qid) for qid in question_ids]
    except (ValueError, TypeError):
        raise ValueError("Invalid UUID format in question_ids")

    updated_count, failed_ids = service.batch_update_status(uuids, status)

    if updated_count > 0:
        log_audit(
            actor_type=ActorType.admin,
            entity_type=EntityType.question,
            action_type=ActionType.BATCH_UPDATE,
            actor_id=None,
            entity_id=None,
            before_data={"count": len(uuids)},
            after_data={"count": updated_count, "status": status},
            request_ip=get_client_ip(request),
        )

    return create_response(
        data={
            "updated_count": updated_count,
            "failed_ids": failed_ids,
            "status": status,
        },
        message=f"Batch updated {updated_count} questions",
    )


@router.get("/stats")
async def get_question_stats(
    subject: Optional[str] = Query(None),
    topics: Optional[str] = Query(None),
    difficulty: Optional[str] = Query(None),
    question_types: Optional[str] = Query(None),
    service: QuestionService = Depends(get_question_service),
):
    """Get question and group counts for given filters (for stat display).

    Query params:
    - subject: Subject code
    - topics: Comma-separated topic codes (e.g., "topic1,topic2")
    - difficulty: Difficulty level
    - question_types: Comma-separated question types (e.g., "multiple_choice,true_false")
    """
    topics_list = [t.strip() for t in topics.split(",")] if topics else []
    question_types_list = (
        [qt.strip() for qt in question_types.split(",")] if question_types else []
    )

    stats = service.get_stats(
        subject=subject,
        topics=topics_list,
        difficulty=difficulty,
        question_types=question_types_list,
    )
    return create_response(data=stats, message="Question stats retrieved")


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
    data["sub_questions"] = [
        QuestionListResponse.model_validate(sq).model_dump() for sq in sub_questions
    ]
    return create_response(data=data, message="Question retrieved successfully")


@router.patch("/{question_id}/status")
async def update_question_status(
    question_id: UUID,
    status: int = Query(..., ge=0, le=2),
    service: QuestionService = Depends(get_question_service),
    request: Request = None,
):
    """Update question approval status. 0=pending, 1=approved, 2=rejected."""
    question = service.get_by_id(question_id)
    if not question:
        raise NotFoundException("Question not found")

    old_status = question.status
    service.update_status(question_id, status)

    log_audit(
        actor_type=ActorType.admin,
        entity_type=EntityType.question,
        action_type=ActionType.UPDATE,
        actor_id=None,
        entity_id=question_id,
        before_data={"status": old_status},
        after_data={"status": status},
        request_ip=get_client_ip(request),
    )

    return create_response(
        data={"id": str(question_id), "status": status},
        message="Question status updated",
    )


@router.post("/{question_id}/review")
async def submit_question_review(
    question_id: UUID,
    body: dict = Body(...),
    service: QuestionService = Depends(get_question_service),
    request: Request = None,
):
    """Submit manual corrections for a question's answers."""
    question = service.get_by_id(question_id)
    if not question:
        raise NotFoundException("Question not found")

    answers = body.get("answers")
    if answers is not None:
        _, old_answers = service.get_with_answers(question_id)
        service.update_answers(question_id, answers)

        log_audit(
            actor_type=ActorType.admin,
            entity_type=EntityType.question,
            action_type=ActionType.UPDATE,
            actor_id=None,
            entity_id=question_id,
            before_data={
                "answers": [to_dict(a) for a in old_answers] if old_answers else None
            },
            after_data={"answers": answers},
            request_ip=get_client_ip(request),
        )

    return create_response(
        data={"id": str(question_id), "updated": True},
        message="Question review submitted",
    )


# ------------------------------------------------------------------
# Question Mutation
# ------------------------------------------------------------------


@router.post("/batch/create")
async def batch_create_questions(
    body: dict = Body(...),
    mutation_service: QuestionMutationService = Depends(get_mutation_service),
    request: Request = None,
):
    """Batch create multiple questions with embedding and group assignment.

    Request body:
    {
        "questions": [
            {
                "question_text": "...",
                "question_type": "...",
                "difficulty": "...",
                "subject": "...",
                "topic": "...",
                "answers": [...],
                "sub_questions": [...],
                "image_list": [...]
            },
            ...
        ]
    }

    Returns list of created questions with their IDs.
    """
    questions_data = body.get("questions", [])
    if not isinstance(questions_data, list) or not questions_data:
        raise BadRequestException("questions must be a non-empty list")

    created_questions = []
    failed_questions = []

    for idx, q_data in enumerate(questions_data):
        try:
            req = CreateQuestionRequest(**q_data)
            question = await mutation_service.create_question(req)
            data = QuestionDetailResponse.model_validate(question).model_dump()
            created_questions.append(data)
        except Exception as e:
            failed_questions.append({"index": idx, "error": str(e)})

    if len(created_questions) > 0:
        log_audit(
            actor_type=ActorType.user,
            entity_type=EntityType.question,
            action_type=ActionType.CREATE,
            actor_id=None,
            entity_id=None,
            before_data=None,
            after_data={"count": len(created_questions)},
            request_ip=get_client_ip(request),
        )

    return create_response(
        data={
            "created": created_questions,
            "failed": failed_questions,
            "total_created": len(created_questions),
            "total_failed": len(failed_questions),
        },
        message=f"Batch created {len(created_questions)} questions",
    )


@router.post("")
async def create_question(
    body: CreateQuestionRequest,
    mutation_service: QuestionMutationService = Depends(get_mutation_service),
    request: Request = None,
):
    """Create a new question with embedding and group assignment."""
    try:
        question = await mutation_service.create_question(body)
        data = QuestionDetailResponse.model_validate(question).model_dump()

        log_audit(
            actor_type=ActorType.user,
            entity_type=EntityType.question,
            action_type=ActionType.CREATE,
            actor_id=None,
            entity_id=question.id,
            before_data=None,
            after_data={
                "question_text": question.question_text,
                "question_type": question.question_type,
            },
            request_ip=get_client_ip(request),
        )

        return create_response(
            data=data,
            message="Question created successfully",
        )
    except ValueError as exc:
        raise BadRequestException(str(exc))


@router.put("/{question_id}")
async def update_question(
    question_id: UUID,
    body: UpdateQuestionRequest,
    mutation_service: QuestionMutationService = Depends(get_mutation_service),
    service: QuestionService = Depends(get_question_service),
    request: Request = None,
):
    """Update a question with optional re-embedding and re-grouping."""
    try:
        old_question = service.get_by_id(question_id)
        question = await mutation_service.update_question(question_id, body)
        data = QuestionDetailResponse.model_validate(question).model_dump()

        log_audit(
            actor_type=ActorType.user,
            entity_type=EntityType.question,
            action_type=ActionType.UPDATE,
            actor_id=None,
            entity_id=question_id,
            before_data={
                "question_text": old_question.question_text if old_question else None
            },
            after_data={"question_text": question.question_text},
            request_ip=get_client_ip(request),
        )

        return create_response(
            data=data,
            message="Question updated successfully",
        )
    except ValueError as exc:
        raise BadRequestException(str(exc))
    except Exception as exc:
        logger.exception(f"Error updating question {question_id}: {exc}")
        raise BadRequestException(f"Error updating question: {str(exc)}")


@router.post("/{question_id}/generate-answer")
async def generate_answer(
    question_id: UUID,
    language: Optional[str] = Query("en"),
    service: GenerateAnswerService = Depends(get_generate_answer_service),
    current_user: User = Depends(get_current_user),
    request: Request = None,
):
    """Generate an AI answer for a question (not persisted)."""
    try:
        result = await service.generate_answer(question_id, language=language or "en")

        log_audit(
            actor_type=ActorType.user,
            entity_type=EntityType.question,
            action_type=ActionType.GENERATE,
            actor_id=current_user.id,
            entity_id=question_id,
            before_data=None,
            after_data={"question_id": str(question_id)},
            request_ip=get_client_ip(request),
        )

        return create_response(data=result, message="Answer generated successfully")
    except ValueError as exc:
        raise NotFoundException(str(exc))
    except Exception as exc:
        logger.exception("Error generating answer for question %s", question_id)
        raise BadRequestException(f"Failed to generate answer: {str(exc)}")


@router.post("/{question_id}/accept-answer")
async def accept_answer(
    question_id: UUID,
    body: AcceptAnswerRequest,
    service: GenerateAnswerService = Depends(get_generate_answer_service),
    current_user: User = Depends(get_current_user),
    request: Request = None,
):
    """Persist a generated answer accepted by the user."""
    try:
        await service.accept_answer(question_id, body.model_dump())

        log_audit(
            actor_type=ActorType.user,
            entity_type=EntityType.question,
            action_type=ActionType.UPDATE,
            actor_id=current_user.id,
            entity_id=question_id,
            before_data=None,
            after_data={"accepted_answer": True},
            request_ip=get_client_ip(request),
        )

        return create_response(
            data={"id": str(question_id), "accepted": True},
            message="Answer accepted and saved",
        )
    except ValueError as exc:
        raise NotFoundException(str(exc))
    except Exception as exc:
        logger.exception("Error accepting answer for question %s", question_id)
        raise BadRequestException(f"Failed to accept answer: {str(exc)}")


@router.delete("/{question_id}")
async def delete_question(
    question_id: UUID,
    mutation_service: QuestionMutationService = Depends(get_mutation_service),
    service: QuestionService = Depends(get_question_service),
    request: Request = None,
):
    """Delete a question and its sub-questions."""
    question_to_delete = service.get_by_id(question_id)
    deleted = mutation_service.delete_question(question_id)
    if not deleted:
        raise NotFoundException("Question not found")

    if question_to_delete:
        log_audit(
            actor_type=ActorType.user,
            entity_type=EntityType.question,
            action_type=ActionType.DELETE,
            actor_id=None,
            entity_id=question_id,
            before_data={"question_text": question_to_delete.question_text},
            after_data=None,
            request_ip=get_client_ip(request),
        )

    return create_response(
        data={"id": str(question_id), "deleted": True},
        message="Question deleted successfully",
    )
