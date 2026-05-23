"""Exam Mutation Service — manual exam instance create/update.

Handles building exam instances from explicitly chosen question IDs,
following the same repo/helper patterns as BaseExamGenerationService.
"""

from __future__ import annotations

import json
import logging
from typing import Optional
from uuid import UUID

from src.dtos.exam.req import CreateManualExamRequest, UpdateManualExamRequest
from src.entities.exam_instance import ExamInstance
from src.repos.answer_repo import AnswerRepository
from src.repos.exam_instance_repo import ExamInstanceRepository
from src.repos.exam_test_section_repo import ExamTestSectionRepository
from src.repos.question_exam_test_repo import QuestionExamTestRepository
from src.repos.question_repo import QuestionRepository
from src.shared.constants.exam import ExamInstanceStatus
from src.shared.helpers.exam_generation_helpers import shuffle_answer_indices

logger = logging.getLogger(__name__)


class ExamMutationService:
    """Create and update manual exam instances from explicit question lists."""

    def __init__(self):
        self._instance_repo = ExamInstanceRepository()
        self._section_repo = ExamTestSectionRepository()
        self._qet_repo = QuestionExamTestRepository()
        self._question_repo = QuestionRepository()
        self._answer_repo = AnswerRepository()

    def create_manual_exam(
        self,
        payload: CreateManualExamRequest,
        created_by_id: Optional[UUID] = None,
    ) -> ExamInstance:
        """Create a new manual exam instance with the given sections and questions."""
        exam = self._instance_repo.create(
            exam_template=None,
            parent_exam_instance=None,
            exam_test_code=payload.exam_test_code,
            is_base=True,
            status=ExamInstanceStatus.PENDING,
            created_by_id=created_by_id,
        )

        self._build_sections(exam.id, payload.sections)

        logger.info("Created manual exam %s (%s)", exam.id, exam.exam_test_code)
        return exam

    def update_manual_exam(
        self,
        exam_id: UUID,
        payload: UpdateManualExamRequest,
    ) -> ExamInstance:
        """Replace the sections/questions of an existing exam instance."""
        exam = self._instance_repo.get_by_id(exam_id)
        if not exam:
            raise ValueError(f"Exam instance {exam_id} not found")

        if payload.exam_test_code is not None:
            exam.exam_test_code = payload.exam_test_code
            exam.save()

        # Delete existing sections (QETs are cascade-deleted via FK)
        for section in self._section_repo.get_by_exam_instance(exam_id):
            for qet in self._qet_repo.get_by_section(section.id):
                qet.delete_instance()
            section.delete_instance()

        self._build_sections(exam_id, payload.sections)

        logger.info("Updated manual exam %s", exam_id)
        return exam

    def _build_sections(self, exam_id: UUID, sections) -> None:
        for section_input in sections:
            sec = self._section_repo.create(
                exam_instance=exam_id,
                name=section_input.name,
                order_index=section_input.order_index,
            )

            for entry in section_input.questions:
                question = self._question_repo.get_by_id(entry.question_id)
                if not question:
                    raise ValueError(f"Question {entry.question_id} not found")

                answer_order = shuffle_answer_indices(question, self._answer_repo)

                self._qet_repo.create(
                    question_group=question.questions_group,
                    question_id=str(entry.question_id),
                    exam_test_section=sec.id,
                    order_count=entry.order_count,
                    answer_order=json.dumps(answer_order),
                )
