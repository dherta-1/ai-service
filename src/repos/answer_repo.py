from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from src.entities.answer import Answer
from src.shared.base.base_repo import BaseRepo


class AnswerRepository(BaseRepo[Answer]):

    def __init__(self):
        super().__init__(Answer)

    def get_by_question(self, question_id: UUID) -> List[Answer]:
        return list(Answer.select().where(Answer.question == question_id))

    def create_for_question(
        self,
        question_id: UUID,
        value: str,
        is_correct: bool,
        explaination: Optional[str] = None,
    ) -> Answer:
        return Answer.create(
            question=question_id,
            value=value,
            is_correct=is_correct,
            explaination=explaination,
        )

    def create_batch(
        self, question_id: UUID, answers: List[dict]
    ) -> List[Answer]:
        created = []
        for a in answers:
            created.append(
                self.create_for_question(
                    question_id=question_id,
                    value=a["value"],
                    is_correct=a["is_correct"],
                    explaination=a.get("explaination"),
                )
            )
        return created

    def delete_by_question(self, question_id: UUID) -> int:
        return Answer.delete().where(Answer.question == question_id).execute()
