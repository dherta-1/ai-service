from __future__ import annotations

from typing import List
from uuid import UUID

from src.entities.exam_test_section import ExamTestSection
from src.entities.question_exam_test import QuestionExamTest
from src.shared.base.base_repo import BaseRepo


class QuestionExamTestRepository(BaseRepo[QuestionExamTest]):

    def __init__(self):
        super().__init__(QuestionExamTest)

    def get_by_section(self, section_id: UUID) -> List[QuestionExamTest]:
        return list(
            QuestionExamTest.select()
            .where(QuestionExamTest.exam_test_section == section_id)
            .order_by(QuestionExamTest.order_count.asc())
        )

    def get_by_exam_instance(self, exam_instance_id: UUID) -> List[QuestionExamTest]:
        return list(
            QuestionExamTest.select()
            .join(ExamTestSection)
            .where(ExamTestSection.exam_instance == exam_instance_id)
            .order_by(ExamTestSection.order_index.asc(), QuestionExamTest.order_count.asc())
        )

    def get_group_ids_for_exam(self, exam_instance_id: UUID) -> List[UUID]:
        rows = (
            QuestionExamTest.select(QuestionExamTest.question_group)
            .join(ExamTestSection)
            .where(ExamTestSection.exam_instance == exam_instance_id)
            .distinct()
        )
        return [r.question_group_id for r in rows]
