from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from peewee import fn
from src.entities.question import Question
from src.shared.base.base_repo import BaseRepo
from src.shared.constants.question import QuestionStatus


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
                (Page.document == document_id) & (Question.parent_question.is_null())
            )
        )

    def count_by_document(self, document_id: UUID) -> int:
        from src.entities.page import Page

        return (
            Question.select()
            .join(Page)
            .where(
                (Page.document == document_id) & (Question.parent_question.is_null())
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
        time_order: str = "desc",
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
        if time_order == "asc":
            query = query.order_by(Question.created_at.asc())
        else:
            query = query.order_by(Question.created_at.desc())
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

    def find_filtered_by_user(
        self,
        user_id: UUID,
        search_query: Optional[str] = None,
        subject: Optional[str] = None,
        topic: Optional[str] = None,
        difficulty: Optional[str] = None,
        question_type: Optional[str] = None,
        status: Optional[int] = None,
        time_order: str = "desc",
        offset: int = 0,
        limit: int = 20,
    ) -> List[Question]:
        from src.entities.question_group import QuestionGroup

        query = (
            Question.select()
            .join(QuestionGroup, on=(Question.questions_group == QuestionGroup.id))
            .where(
                (Question.parent_question.is_null())
                & (QuestionGroup.from_user == user_id)
            )
        )
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
        if time_order == "asc":
            query = query.order_by(Question.created_at.asc())
        else:
            query = query.order_by(Question.created_at.desc())
        return list(query.offset(offset).limit(limit))

    def count_by_filters(
        self,
        subject: Optional[str] = None,
        topics: Optional[List[str]] = None,
        difficulty: Optional[str] = None,
        question_types: Optional[List[str]] = None,
    ) -> int:
        query = (
            Question.select()
            .where((Question.parent_question.is_null()))
            .where(Question.status == QuestionStatus.APPROVED.value)
        )
        if subject:
            query = query.where(Question.subject == subject)
        if topics:
            query = query.where(Question.topic.in_(topics))
        if difficulty:
            query = query.where(Question.difficulty == difficulty)
        if question_types:
            query = query.where(Question.question_type.in_(question_types))
        return query.count()

    def count_filtered_by_user(
        self,
        user_id: UUID,
        search_query: Optional[str] = None,
        subject: Optional[str] = None,
        topic: Optional[str] = None,
        difficulty: Optional[str] = None,
        question_type: Optional[str] = None,
        status: Optional[int] = None,
    ) -> int:
        from src.entities.question_group import QuestionGroup

        query = (
            Question.select()
            .join(QuestionGroup, on=(Question.questions_group == QuestionGroup.id))
            .where(
                (Question.parent_question.is_null())
                & (QuestionGroup.from_user == user_id)
            )
        )
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

    def get_by_criteria(
        self,
        subject: str,
        topics: List[str],
        difficulty: str,
        question_types: Optional[List[str]] = None,
    ) -> List[Question]:
        """Get questions matching subject, topics, and difficulty.

        Excludes parent questions and only returns APPROVED questions.
        Optionally filters by question_type.
        """
        query = Question.select().where(
            (Question.subject == subject)
            & (Question.topic.in_(topics))
            & (Question.difficulty == difficulty)
            & (Question.parent_question.is_null())
            & (Question.status == QuestionStatus.APPROVED.value)
        )
        if question_types:
            query = query.where(Question.question_type.in_(question_types))
        return list(query)

    def get_by_criteria_with_fallback(
        self,
        subject: str,
        topics: List[str],
        difficulty: str,
        fallback_difficulties: Optional[List[str]] = None,
        question_types: Optional[List[str]] = None,
    ) -> List[Question]:
        """Get questions with difficulty fallback.

        First tries to match exact difficulty. If no results, tries fallback difficulties
        in order until questions are found.
        """
        questions = self.get_by_criteria(subject, topics, difficulty, question_types)

        if not questions and fallback_difficulties:
            for fallback_diff in fallback_difficulties:
                questions = self.get_by_criteria(
                    subject, topics, fallback_diff, question_types
                )
                if questions:
                    break

        return questions

    def get_variants_by_group(
        self,
        group_id: UUID,
        question_types: Optional[List[str]] = None,
    ) -> List[Question]:
        """Get all variants (non-parent questions) from a group.

        Optionally filters by question_type.
        """
        query = Question.select().where(
            (Question.questions_group == group_id)
            & (Question.parent_question.is_null())
            & (Question.status == QuestionStatus.APPROVED.value)
        )
        if question_types:
            query = query.where(Question.question_type.in_(question_types))
        return list(query)
