"""Exam Service - Orchestrates exam lifecycle and management.

Handles lifecycle operations:
  - ExamTemplate CRUD
  - ExamInstance status management and review
  - Exam data retrieval and assembly

Delegates pure generation logic to core services:
  - BaseExamGenerationService (core generation algorithms)
  - VariantExamGenerationService (core variant generation)
"""

from __future__ import annotations

import json
import logging
from typing import List, Optional
from uuid import UUID

from src.dtos.exam.req import SectionConfig
from src.entities.exam_instance import ExamInstance
from src.entities.exam_template import ExamTemplate
from src.entities.question_exam_test import QuestionExamTest
from src.repos.answer_repo import AnswerRepository
from src.repos.exam_instance_repo import ExamInstanceRepository
from src.repos.exam_template_repo import ExamTemplateRepository
from src.repos.exam_test_section_repo import ExamTestSectionRepository
from src.repos.question_exam_test_repo import QuestionExamTestRepository
from src.repos.question_repo import QuestionRepository
from src.services.core.base_exam_generation_service import BaseExamGenerationService
from src.services.core.variant_exam_generation_service import (
    VariantExamGenerationService,
)
from src.shared.constants.exam import ExamInstanceStatus

logger = logging.getLogger(__name__)


class ExamService:
    """Exam lifecycle and management service.

    Handles all lifecycle operations via repositories directly.
    Delegates pure generation logic to core services.
    """

    def __init__(self, llm_client=None):
        self._template_repo = ExamTemplateRepository()
        self._instance_repo = ExamInstanceRepository()
        self._section_repo = ExamTestSectionRepository()
        self._qet_repo = QuestionExamTestRepository()
        self._question_repo = QuestionRepository()
        self._answer_repo = AnswerRepository()

    # ------------------------------------------------------------------
    # Template management (Lifecycle - Direct repo access)
    # ------------------------------------------------------------------

    def save_template(
        self,
        name: str,
        subject: str,
        generation_config: Optional[List[SectionConfig]] = None,
        template_id: Optional[UUID] = None,
        created_by_id: Optional[UUID] = None,
    ) -> ExamTemplate:
        """Create or update an ExamTemplate."""
        config_json = (
            json.dumps([s.model_dump() for s in generation_config])
            if generation_config
            else None
        )

        if template_id:
            template = self._template_repo.get_by_id(template_id)
            if not template:
                raise ValueError(f"Template {template_id} not found")
            template.name = name
            template.subject = subject
            template.generation_config = config_json
            template.save()
            return template

        return self._template_repo.create(
            name=name,
            subject=subject,
            generation_config=config_json,
            created_by_id=created_by_id,
        )

    def get_template(self, template_id: UUID) -> Optional[ExamTemplate]:
        """Retrieve a template by ID."""
        return self._template_repo.get_by_id(template_id)

    def list_templates(
        self, subject: Optional[str] = None, user_id: Optional[UUID] = None
    ) -> List[ExamTemplate]:
        """List templates, optionally filtered by subject and/or user.

        If user_id provided (non-admin): return only user's templates.
        If user_id is None (admin): return all templates.
        """
        if user_id:
            if subject:
                return self._template_repo.get_by_subject_and_user(subject, user_id)
            return self._template_repo.get_by_user(user_id)

        if subject:
            return self._template_repo.get_by_subject(subject)
        return self._template_repo.get_all()

    # ------------------------------------------------------------------
    # Exam status lifecycle (Direct repo access)
    # ------------------------------------------------------------------

    def update_exam_status(self, exam_id: UUID, status: int) -> ExamInstance:
        """Set exam status. 0=pending, 1=accepted, 2=rejected."""
        if status not in (
            ExamInstanceStatus.PENDING,
            ExamInstanceStatus.ACCEPTED,
            ExamInstanceStatus.REJECTED,
        ):
            raise ValueError(f"Invalid status value: {status}")

        exam = self._instance_repo.get_by_id(exam_id)
        if not exam:
            raise ValueError(f"Exam instance {exam_id} not found")

        self._instance_repo.update_status(exam_id, status)
        exam.status = status
        return exam

    # ------------------------------------------------------------------
    # Question replacement (Review - Direct repo access)
    # ------------------------------------------------------------------

    def replace_question(
        self,
        exam_instance_id: UUID,
        qet_id: UUID,
        new_question_id: UUID,
    ) -> QuestionExamTest:
        """Replace a question variant within the same QuestionGroup."""
        qet = self._qet_repo.get_by_id(qet_id)
        if not qet:
            raise ValueError(f"QuestionExamTest {qet_id} not found")

        section = self._section_repo.get_by_id(qet.exam_test_section_id)
        if str(section.exam_instance_id) != str(exam_instance_id):
            raise ValueError(
                f"QuestionExamTest {qet_id} does not belong to exam {exam_instance_id}"
            )

        new_question = self._question_repo.get_by_id(new_question_id)
        if not new_question:
            raise ValueError(f"Question {new_question_id} not found")

        if str(new_question.questions_group_id) != str(qet.question_group_id):
            raise ValueError(
                f"Question {new_question_id} is not in group {qet.question_group_id}"
            )

        from src.shared.helpers.exam_generation_helpers import shuffle_answer_indices

        qet.question_id = str(new_question_id)
        qet.answer_order = json.dumps(
            shuffle_answer_indices(new_question, self._answer_repo)
        )
        qet.save()
        return qet

    # ------------------------------------------------------------------
    # Read operations (Direct repo access)
    # ------------------------------------------------------------------

    def get_exam_instance(self, exam_id: UUID) -> Optional[ExamInstance]:
        """Retrieve an exam instance by ID."""
        return self._instance_repo.get_by_id(exam_id)

    def get_exam_versions(self, base_exam_id: UUID) -> List[ExamInstance]:
        """Get all variant versions of a base exam."""
        return self._instance_repo.get_versions_of(base_exam_id)

    def get_base_instances(
        self, template_id: UUID, user_id: Optional[UUID] = None
    ) -> List[ExamInstance]:
        """Get base exam instances from a template.

        If user_id provided (non-admin): return only user's instances.
        If user_id is None (admin): return all instances.
        """
        all_instances = self._instance_repo.get_base_instances(template_id)
        if user_id:
            return [inst for inst in all_instances if inst.created_by_id == user_id]
        return all_instances

    def build_exam_response_data(self, exam: ExamInstance) -> dict:
        """Assemble full exam data dict (sections + enriched questions)."""
        sections_data = []
        total_questions = 0

        sections = self._section_repo.get_by_exam_instance(exam.id)
        for sec in sections:
            qets = self._qet_repo.get_by_section(sec.id)
            questions_data = []

            for qet in qets:
                question = self._question_repo.get_by_id(UUID(qet.question_id))
                if not question:
                    continue

                answers = self._answer_repo.get_by_question(question.id)
                sub_questions = self._question_repo.get_sub_questions(question.id)

                answer_order = None
                if qet.answer_order:
                    try:
                        answer_order = json.loads(qet.answer_order)
                    except (ValueError, TypeError):
                        answer_order = None

                questions_data.append(
                    {
                        "question_exam_test_id": str(qet.id),
                        "question_id": str(question.id),
                        "question_group_id": str(qet.question_group_id),
                        "order_count": qet.order_count,
                        "answer_order": answer_order,
                        "question_text": question.question_text,
                        "question_type": question.question_type,
                        "difficulty": question.difficulty,
                        "image_list": question.image_list,
                        "answers": [
                            {
                                "id": str(a.id),
                                "value": a.value,
                                "is_correct": a.is_correct,
                            }
                            for a in answers
                        ],
                        "sub_questions": [
                            {
                                "question_exam_test_id": str(qet.id),
                                "question_id": str(sq.id),
                                "question_group_id": str(qet.question_group_id),
                                "order_count": sq.sub_question_order or 0,
                                "answer_order": None,
                                "question_text": sq.question_text,
                                "question_type": sq.question_type,
                                "difficulty": None,
                                "image_list": sq.image_list,
                                "answers": [
                                    {
                                        "id": str(a.id),
                                        "value": a.value,
                                        "is_correct": a.is_correct,
                                    }
                                    for a in self._answer_repo.get_by_question(sq.id)
                                ],
                                "sub_questions": None,
                            }
                            for sq in sub_questions
                        ]
                        or None,
                    }
                )
                total_questions += 1

            sections_data.append(
                {
                    "id": str(sec.id),
                    "name": sec.name,
                    "order_index": sec.order_index,
                    "questions": questions_data,
                }
            )

        return {
            "id": str(exam.id),
            "exam_test_code": exam.exam_test_code,
            "is_base": exam.is_base,
            "is_exported": exam.is_exported,
            "status": exam.status,
            "template_id": (
                str(exam.exam_template_id) if exam.exam_template_id else None
            ),
            "parent_exam_instance_id": (
                str(exam.parent_exam_instance_id)
                if exam.parent_exam_instance_id
                else None
            ),
            "sections": sections_data,
            "created_at": exam.created_at.isoformat(),
            "updated_at": exam.updated_at.isoformat(),
            "_total_questions": total_questions,
        }
