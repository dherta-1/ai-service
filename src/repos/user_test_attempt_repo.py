from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from src.entities.user_test_attempt import UserTestAttempt
from src.shared.base.base_repo import BaseRepo
from src.shared.constants.exam import UserTestAttemptStatus


class UserTestAttemptRepository(BaseRepo[UserTestAttempt]):
    def __init__(self):
        super().__init__(UserTestAttempt)

    def create_attempt(
        self,
        user_id: UUID,
        exam_template_id: UUID,
        exam_instance_id: UUID,
    ) -> UserTestAttempt:
        return self.create(
            user=user_id,
            exam_template_id=str(exam_template_id),
            exam_instance=exam_instance_id,
            status=UserTestAttemptStatus.IN_PROGRESS,
            started_at=datetime.utcnow(),
        )

    def get_by_user(self, attempt_id: UUID, user_id: UUID) -> Optional[UserTestAttempt]:
        return self.filter_one(id=attempt_id, user=user_id)

    def update_status(
        self,
        attempt_id: UUID,
        status: int,
        score: Optional[float] = None,
        submitted_at: Optional[datetime] = None,
    ) -> None:
        update_data: dict = {"status": status}
        if score is not None:
            update_data["score"] = score
        if submitted_at is not None:
            update_data["submitted_at"] = submitted_at
        UserTestAttempt.update(**update_data).where(
            UserTestAttempt.id == attempt_id
        ).execute()

    def list_by_user(
        self, user_id: UUID, page: int = 1, per_page: int = 10
    ) -> tuple[list[UserTestAttempt], int]:
        query = (
            UserTestAttempt.select()
            .where(UserTestAttempt.user == user_id)
            .order_by(UserTestAttempt.started_at.desc())
        )
        total = query.count()
        attempts = list(query.offset((page - 1) * per_page).limit(per_page))
        return attempts, total
