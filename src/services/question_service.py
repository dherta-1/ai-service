from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from src.repos.answer_repo import AnswerRepository
from src.repos.question_repo import QuestionRepository
from src.shared.base.base_service import BaseService


class QuestionService(BaseService):

    def __init__(
        self,
    ):
        super().__init__(QuestionRepository())
        self._answer_repo = AnswerRepository()

    # --- Query ---

    def get_by_id(self, question_id: UUID):
        return self.repo.get_by_id(question_id)

    def get_all(self):
        return self.repo.get_all()

    def get_all_paginated(self, page: int = 1, page_size: int = 10):
        return self.repo.get_all_paginated(page, page_size)

    def get_by_page(self, page_id: UUID):
        return self.repo.get_by_page(page_id)

    def get_sub_questions(self, parent_question_id: UUID):
        return self.repo.get_sub_questions(parent_question_id)

    def get_by_question_type(self, question_type: str):
        return self.repo.get_by_question_type(question_type)

    def get_by_subject_and_topic(
        self, subject: Optional[str] = None, topic: Optional[str] = None
    ):
        return self.repo.get_by_subject_and_topic(subject, topic)

    def get_by_document(self, document_id: UUID):
        return self.repo.get_by_document(document_id)

    def count_by_document(self, document_id: UUID) -> int:
        return self.repo.count_by_document(document_id)

    def find_filtered(
        self,
        subject: Optional[str] = None,
        topic: Optional[str] = None,
        difficulty: Optional[str] = None,
        status: Optional[int] = None,
        page: int = 1,
        page_size: int = 20,
    ):
        offset = (page - 1) * page_size
        questions = self.repo.find_filtered(
            subject=subject,
            topic=topic,
            difficulty=difficulty,
            status=status,
            offset=offset,
            limit=page_size,
        )
        total = self.repo.count_filtered(
            subject=subject, topic=topic, difficulty=difficulty, status=status
        )
        return questions, total

    def get_with_answers(self, question_id: UUID):
        question = self.repo.get_by_id(question_id)
        if question is None:
            return None, []
        answers = self._answer_repo.get_by_question(question_id)
        return question, answers

    # --- Mutation ---

    def update_status(self, question_id: UUID, status: int):
        return self.repo.update(question_id, status=status)

    def update_answers(self, question_id: UUID, answers: List[dict]):
        """Replace all answers for a question."""
        self._answer_repo.delete_by_question(question_id)
        return self._answer_repo.create_batch(question_id, answers)
