from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from peewee import fn
from src.entities.question import Question
from src.shared.base.base_repo import BaseRepo


class QuestionRepository(BaseRepo[Question]):

    def __init__(self):
        super().__init__(Question)

    def get_by_page(self, page_id: UUID) -> List[Question]:
        return list(
            Question.select().where(
                (Question.page == page_id) & (Question.parent_question.is_null())
            )
        )

    def get_sub_questions(self, parent_question_id: UUID) -> List[Question]:
        return list(
            Question.select().where(Question.parent_question == parent_question_id)
        )

    def get_by_question_type(self, question_type: str) -> List[Question]:
        return list(Question.select().where(Question.question_type == question_type))

    def get_by_subject_and_topic(
        self, subject: Optional[str] = None, topic: Optional[str] = None
    ) -> List[Question]:
        query = Question.select().where(Question.parent_question.is_null())
        if subject is not None:
            query = query.where(Question.subject == subject)
        if topic is not None:
            query = query.where(Question.topic == topic)
        return list(query)

    def get_by_document(self, document_id: UUID) -> List[Question]:
        from src.entities.page import Page
        return list(
            Question.select()
            .join(Page)
            .where(
                (Page.document == document_id)
                & (Question.parent_question.is_null())
            )
        )

    def count_by_document(self, document_id: UUID) -> int:
        from src.entities.page import Page
        return (
            Question.select()
            .join(Page)
            .where(
                (Page.document == document_id)
                & (Question.parent_question.is_null())
            )
            .count()
        )

    def get_by_group(self, group_id: UUID) -> List[Question]:
        return list(Question.select().where(Question.questions_group == group_id))

    def find_filtered(
        self,
        search_query: Optional[str] = None,
        subject: Optional[str] = None,
        topic: Optional[str] = None,
        difficulty: Optional[str] = None,
        question_type: Optional[str] = None,
        status: Optional[int] = None,
        offset: int = 0,
        limit: int = 20,
    ) -> List[Question]:
        query = Question.select().where(Question.parent_question.is_null())
        if search_query:
            query = query.where(Question.question_text.contains(search_query))
        if subject:
            query = query.where(Question.subject == subject)
        if topic:
            query = query.where(Question.topic == topic)
        if difficulty:
            query = query.where(Question.difficulty == difficulty)
        if question_type:
            query = query.where(Question.question_type == question_type)
        if status is not None:
            query = query.where(Question.status == status)
        return list(query.offset(offset).limit(limit))

    def count_filtered(
        self,
        search_query: Optional[str] = None,
        subject: Optional[str] = None,
        topic: Optional[str] = None,
        difficulty: Optional[str] = None,
        question_type: Optional[str] = None,
        status: Optional[int] = None,
    ) -> int:
        query = Question.select().where(Question.parent_question.is_null())
        if search_query:
            query = query.where(Question.question_text.contains(search_query))
        if subject:
            query = query.where(Question.subject == subject)
        if topic:
            query = query.where(Question.topic == topic)
        if difficulty:
            query = query.where(Question.difficulty == difficulty)
        if question_type:
            query = query.where(Question.question_type == question_type)
        if status is not None:
            query = query.where(Question.status == status)
        return query.count()
