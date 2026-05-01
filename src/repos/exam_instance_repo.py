from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from src.entities.exam_instance import ExamInstance
from src.shared.base.base_repo import BaseRepo
from src.shared.constants.exam import ExamInstanceStatus


class ExamInstanceRepository(BaseRepo[ExamInstance]):

    def __init__(self):
        super().__init__(ExamInstance)

    def get_by_template(self, template_id: UUID) -> List[ExamInstance]:
        return list(ExamInstance.select().where(ExamInstance.exam_template == template_id))

    def get_base_instances(self, template_id: UUID) -> List[ExamInstance]:
        return list(
            ExamInstance.select().where(
                (ExamInstance.exam_template == template_id)
                & (ExamInstance.is_base == True)  # noqa: E712
            ).order_by(ExamInstance.created_at.desc())
        )

    def get_versions_of(self, base_exam_id: UUID) -> List[ExamInstance]:
        return list(
            ExamInstance.select().where(
                (ExamInstance.parent_exam_instance == base_exam_id)
                & (ExamInstance.is_base == False)  # noqa: E712
            ).order_by(ExamInstance.created_at.asc())
        )

    def get_by_code(self, code: str) -> Optional[ExamInstance]:
        return self.filter_one(exam_test_code=code)

    def get_accepted_base(self, template_id: UUID) -> Optional[ExamInstance]:
        try:
            return (
                ExamInstance.select()
                .where(
                    (ExamInstance.exam_template == template_id)
                    & (ExamInstance.is_base == True)  # noqa: E712
                    & (ExamInstance.status == ExamInstanceStatus.ACCEPTED)
                )
                .get()
            )
        except ExamInstance.DoesNotExist:
            return None

    def get_by_user(self, user_id: UUID) -> List[ExamInstance]:
        return list(ExamInstance.select().where(ExamInstance.created_by == user_id))

    def get_by_user_and_template(self, user_id: UUID, template_id: UUID) -> List[ExamInstance]:
        return list(
            ExamInstance.select().where(
                (ExamInstance.created_by == user_id) & (ExamInstance.exam_template == template_id)
            )
        )

    def update_status(self, exam_id: UUID, status: int) -> None:
        ExamInstance.update(status=status).where(ExamInstance.id == exam_id).execute()
