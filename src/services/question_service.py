from typing import List, Optional
from uuid import UUID
from src.shared.base.base_service import BaseService
from src.repos.question_repo import QuestionRepository


class QuestionService(BaseService):
    """Service for question operations"""

    def __init__(self):
        super().__init__(QuestionRepository())

    def get_by_id(self, question_id: UUID) -> Optional:
        """Get question by ID"""
        return self.repo.get_by_id(question_id)

    def get_all(self) -> List:
        """Get all questions"""
        return self.repo.get_all()

    def get_all_paginated(self, page: int = 1, page_size: int = 10):
        """Get questions with pagination"""
        return self.repo.get_all_paginated(page, page_size)

    def get_by_page(self, page_id: UUID) -> List:
        """Get questions by page ID"""
        return self.repo.get_by_page(page_id)

    def get_by_question_type(self, question_type: str) -> List:
        """Get questions by type"""
        return self.repo.get_by_question_type(question_type)

    def get_by_subject_and_topic(
        self, subject: Optional[str] = None, topic: Optional[str] = None
    ) -> List:
        """Get questions by subject and/or topic"""
        return self.repo.get_by_subject_and_topic(subject, topic)
