from __future__ import annotations

from typing import Iterable, List, Optional
from uuid import UUID

from src.entities.user_test_attempt_answer import UserTestAttemptAnswer
from src.shared.base.base_repo import BaseRepo


class UserTestAttemptAnswerRepository(BaseRepo[UserTestAttemptAnswer]):
    def __init__(self):
        super().__init__(UserTestAttemptAnswer)

    def get_by_attempt(self, attempt_id: UUID) -> List[UserTestAttemptAnswer]:
        return list(
            UserTestAttemptAnswer.select().where(
                UserTestAttemptAnswer.attempt == attempt_id
            )
        )

    def get_by_attempt_and_question(
        self, attempt_id: UUID, question_id: str
    ) -> Optional[UserTestAttemptAnswer]:
        return self.filter_one(attempt=attempt_id, question_id=question_id)

    def upsert_answer(
        self,
        attempt_id: UUID,
        question_id: str,
        selected_answer_id: Optional[str],
        is_correct: bool,
        time_spent: int = 0,
    ) -> UserTestAttemptAnswer:
        existing = self.get_by_attempt_and_question(attempt_id, question_id)
        if existing:
            existing.selected_answer_id = selected_answer_id
            existing.is_correct = is_correct
            existing.time_spent = time_spent
            existing.save()
            return existing

        return self.create(
            attempt=attempt_id,
            question_id=question_id,
            selected_answer_id=selected_answer_id,
            is_correct=is_correct,
            time_spent=time_spent,
        )

    def bulk_upsert(self, answers: Iterable[dict]) -> None:
        for payload in answers:
            self.upsert_answer(**payload)
