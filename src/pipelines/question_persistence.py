"""Question Persistence Pipeline — persists extracted questions with answers.

Specification (Persist câu hỏi step 1-5):
  1. Create Question records (composite → sub-questions with parent_question_id)
  2. Create Answer records with is_correct boolean
  3. Update task progress
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional
from uuid import UUID

from src.entities.question import Question
from src.repos.answer_repo import AnswerRepository
from src.repos.question_repo import QuestionRepository
from src.repos.task_repo import TaskRepository
from src.repos.subject_repo import SubjectRepository
from src.repos.topic_repo import TopicRepository
from src.shared.base.base_pipeline import BasePipeline
from src.shared.constants.general import Status
from src.shared.constants.question import QuestionType
from src.shared.helpers.task_logger import TaskLogger

logger = logging.getLogger(__name__)


class QuestionPersistencePipeline(BasePipeline):
    """Persist extracted questions to database and create subject/topic records.

    Input payload:
        {
            "page_id": UUID,
            "page_number": int,
            "task_id": UUID,
            "is_final_page": bool,
            "questions": [
                {
                    "question_text": str,
                    "question_type": str,
                    "difficulty": Optional[str],
                    "subject": Optional[str] (code, e.g., "math"),
                    "subject_vi": Optional[str] (Vietnamese name),
                    "topic": Optional[str] (code, e.g., "algebra"),
                    "topic_vi": Optional[str] (Vietnamese name),
                    "image_list": Optional[list],
                    "answers": Optional[List[Dict{"value": str, "is_correct": bool}]],
                    "group_id": Optional[UUID],
                    "sub_questions": Optional[list] of {
                        "order": Optional[int] (1-indexed, sub-question sequence),
                        "sub_question_text": str,
                        "question_type": str,
                        "answers": Optional[List[Dict{"value": str, "is_correct": bool}]],
                        "image_list": Optional[list]
                    }
                },
                ...
            ]
        }

    Output payload:
        {
            "persisted_count": int,
            "failed_count": int,
            "errors": List[str]
        }
    """

    def __init__(self):
        self._question_repo = QuestionRepository()
        self._answer_repo = AnswerRepository()
        self._task_repo = TaskRepository()
        self._subject_repo = SubjectRepository()
        self._topic_repo = TopicRepository()
        self._task_logger = TaskLogger(self._task_repo)

    def validate(self, payload: dict[str, Any]) -> None:
        required = ["page_id", "page_number", "task_id", "is_final_page", "questions"]
        for key in required:
            if key not in payload:
                raise ValueError(f"QuestionPersistencePipeline requires '{key}' key")

    async def process(self, payload: dict[str, Any]) -> dict[str, Any]:
        page_id = UUID(payload["page_id"])
        page_number = payload["page_number"]
        task_id = UUID(payload["task_id"])
        is_final_page = payload["is_final_page"]
        questions = payload.get("questions", [])

        start_ms = int(time.time() * 1000)
        result = {"persisted_count": 0, "failed_count": 0, "errors": []}

        for q_data in questions:
            try:
                self._persist_one(page_id, q_data)
                result["persisted_count"] += 1
            except Exception as exc:
                result["failed_count"] += 1
                result["errors"].append(str(exc))
                logger.error("Failed to persist question: %s", exc, exc_info=True)

        elapsed_ms = int(time.time() * 1000) - start_ms
        self._update_task_progress(
            task_id=task_id,
            page_number=page_number,
            questions_count=result["persisted_count"],
            elapsed_ms=elapsed_ms,
            is_final_page=is_final_page,
        )

        return result

    def _persist_one(self, page_id: UUID, q_data: Dict[str, Any]) -> None:
        question_text = (q_data.get("question_text") or "").strip()
        if not question_text:
            return

        question_type = q_data.get("question_type", QuestionType.SHORT_ANSWER.value)
        difficulty = q_data.get("difficulty")
        subject_code = q_data.get("subject")
        topic_code = q_data.get("topic")
        subject_vi = q_data.get("subject_vi")
        topic_vi = q_data.get("topic_vi")
        image_list = q_data.get("image_list") or []
        group_id = q_data.get("group_id")

        # Create or get subject record if subject_code is provided
        # This ensures subject exists in Subject table for reference
        if subject_code:
            self._subject_repo.get_or_create(
                code=subject_code,
                name=subject_code.replace("_", " ").title(),
                name_vi=subject_vi,
            )

        # Create or get topic record if topic_code is provided
        # This ensures topic exists in Topic table for reference
        if topic_code:
            self._topic_repo.get_or_create(
                code=topic_code,
                name=topic_code.replace("_", " ").title(),
                name_vi=topic_vi,
            )

        main_q = Question.create(
            page=page_id,
            parent_question=None,
            questions_group=group_id,
            question_text=question_text,
            question_type=question_type,
            difficulty=difficulty,
            subject=subject_code,  # Store the code as string reference
            topic=topic_code,      # Store the code as string reference
            image_list=image_list or [],
            vector_embedding=q_data.get("vector"),
            variant_existence_count=1,
            status=0,
        )

        answers = q_data.get("answers") or []
        if answers and isinstance(answers, list):
            self._answer_repo.create_batch(main_q.id, answers)

        if question_type == QuestionType.COMPOSITE.value:
            sub_questions = q_data.get("sub_questions") or []
            for sub in sub_questions:
                self._persist_sub_question(page_id, group_id, main_q.id, sub)

    def _persist_sub_question(
        self,
        page_id: UUID,
        group_id: Optional[UUID],
        parent_id: UUID,
        sub_data: Dict[str, Any],
    ) -> None:
        sub_text = (
            sub_data.get("sub_question_text") or sub_data.get("question_text") or ""
        ).strip()
        if not sub_text:
            return

        sub_order = sub_data.get("order")

        sub_q = Question.create(
            page=page_id,
            parent_question=parent_id,
            questions_group=group_id,
            question_text=sub_text,
            question_type=sub_data.get("question_type", QuestionType.SHORT_ANSWER.value),
            difficulty=None,
            subject=None,
            topic=None,
            image_list=None,
            sub_question_order=sub_order,  # Store order from LLM
            vector_embedding=None,
            variant_existence_count=1,
            status=0,
        )

        answers = sub_data.get("answers") or []
        if answers and isinstance(answers, list):
            self._answer_repo.create_batch(sub_q.id, answers)

    def _update_task_progress(
        self,
        task_id: UUID,
        page_number: int,
        questions_count: int,
        elapsed_ms: int,
        is_final_page: bool,
    ) -> None:
        task = self._task_repo.get_by_id(task_id)
        if task is None:
            return

        task.processed_pages = (task.processed_pages or 0) + 1
        total = task.total_pages or 1
        task.progress = min(task.processed_pages / total, 1.0)

        if is_final_page:
            task.status = Status.COMPLETED.value
            task.progress = 1.0

        task.save()

        if is_final_page:
            self._task_logger.log_completed(task_id, questions_count)
        else:
            self._task_logger.log_page_processed(
                task_id, page_number, questions_count, elapsed_ms
            )
