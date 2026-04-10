from typing import List, Optional
from uuid import UUID
from src.entities.question import Question
from src.shared.base.base_repo import BaseRepo


class QuestionRepository(BaseRepo[Question]):

    def __init__(self):
        super().__init__(Question)

    def get_by_page(self, page_id: UUID) -> List[Question]:
        return self.filter(page=page_id)

    def get_by_question_type(self, question_type: str) -> List[Question]:
        return self.filter(question_type=question_type)

    def get_by_subject_and_topic(
        self, subject: Optional[str] = None, topic: Optional[str] = None
    ) -> List[Question]:
        query = self.model.select()
        if subject is not None:
            query = query.where(self.model.subject == subject)
        if topic is not None:
            query = query.where(self.model.topic == topic)
        return list(query)
