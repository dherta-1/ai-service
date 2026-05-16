from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from src.repos.answer_repo import AnswerRepository
from src.repos.question_repo import QuestionRepository
from src.repos.question_group_repo import QuestionGroupRepository
from src.shared.base.base_service import BaseService


class QuestionService(BaseService):

    def __init__(
        self,
    ):
        super().__init__(QuestionRepository())
        self._answer_repo = AnswerRepository()
        self._group_repo = QuestionGroupRepository()

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
        search_query: Optional[str] = None,
        subject: Optional[str] = None,
        topic: Optional[str] = None,
        difficulty: Optional[str] = None,
        question_type: Optional[str] = None,
        status: Optional[int] = None,
        page: int = 1,
        page_size: int = 20,
    ):
        offset = (page - 1) * page_size
        questions = self.repo.find_filtered(
            search_query=search_query,
            subject=subject,
            topic=topic,
            difficulty=difficulty,
            question_type=question_type,
            status=status,
            offset=offset,
            limit=page_size,
        )
        total = self.repo.count_filtered(
            search_query=search_query,
            subject=subject,
            topic=topic,
            difficulty=difficulty,
            question_type=question_type,
            status=status,
        )
        return questions, total

    def find_filtered_by_user(
        self,
        user_id: UUID,
        search_query: Optional[str] = None,
        subject: Optional[str] = None,
        topic: Optional[str] = None,
        difficulty: Optional[str] = None,
        question_type: Optional[str] = None,
        status: Optional[int] = None,
        page: int = 1,
        page_size: int = 20,
    ):
        offset = (page - 1) * page_size
        questions = self.repo.find_filtered_by_user(
            user_id=user_id,
            search_query=search_query,
            subject=subject,
            topic=topic,
            difficulty=difficulty,
            question_type=question_type,
            status=status,
            offset=offset,
            limit=page_size,
        )
        total = self.repo.count_filtered_by_user(
            user_id=user_id,
            search_query=search_query,
            subject=subject,
            topic=topic,
            difficulty=difficulty,
            question_type=question_type,
            status=status,
        )
        return questions, total

    def get_stats(
        self,
        subject: Optional[str] = None,
        topics: Optional[List[str]] = None,
        difficulty: Optional[str] = None,
        question_types: Optional[List[str]] = None,
    ) -> dict:
        question_count = self.repo.count_by_filters(
            subject=subject,
            topics=topics,
            difficulty=difficulty,
            question_types=question_types,
        )
        group_count = self._group_repo.count_by_filters(
            subject=subject,
            topics=topics,
            difficulty=difficulty,
        )
        return {"question_count": question_count, "group_count": group_count}

    def get_with_answers(self, question_id: UUID):
        question = self.repo.get_by_id(question_id)
        if question is None:
            return None, []
        answers = self._answer_repo.get_by_question(question_id)
        return question, answers

    # --- Mutation ---

    def update_status(self, question_id: UUID, status: int):
        return self.repo.update(question_id, status=status)

    def batch_update_status(self, question_ids: List[UUID], status: int) -> tuple[int, list[str]]:
        """Update status for multiple questions.

        Args:
            question_ids: List of question UUIDs
            status: Status value (0=pending, 1=approved, 2=rejected)

        Returns:
            Tuple of (updated_count, failed_ids)
        """
        updated_count = 0
        failed_ids = []

        for question_id in question_ids:
            try:
                self.repo.update(question_id, status=status)
                updated_count += 1
            except Exception:
                failed_ids.append(str(question_id))

        return updated_count, failed_ids

    def update_answers(self, question_id: UUID, answers: List[dict]):
        """Replace all answers for a question."""
        self._answer_repo.delete_by_question(question_id)
        return self._answer_repo.create_batch(question_id, answers)
