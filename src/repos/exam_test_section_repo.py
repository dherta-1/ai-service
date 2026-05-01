from __future__ import annotations

from typing import List
from uuid import UUID

from src.entities.exam_test_section import ExamTestSection
from src.shared.base.base_repo import BaseRepo


class ExamTestSectionRepository(BaseRepo[ExamTestSection]):

    def __init__(self):
        super().__init__(ExamTestSection)

    def get_by_exam_instance(self, exam_instance_id: UUID) -> List[ExamTestSection]:
        return list(
            ExamTestSection.select()
            .where(ExamTestSection.exam_instance == exam_instance_id)
            .order_by(ExamTestSection.order_index.asc())
        )
