from __future__ import annotations

from typing import List, Optional

from src.entities.exam_template import ExamTemplate
from src.shared.base.base_repo import BaseRepo


class ExamTemplateRepository(BaseRepo[ExamTemplate]):

    def __init__(self):
        super().__init__(ExamTemplate)

    def get_by_name(self, name: str) -> Optional[ExamTemplate]:
        return self.filter_one(name=name)

    def get_by_subject(self, subject: str) -> List[ExamTemplate]:
        return list(ExamTemplate.select().where(ExamTemplate.subject == subject))
