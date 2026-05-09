"""Question Mutation Service

Handles create, update, delete operations for questions with:
- Vector embedding generation
- Question group assignment (find or create)
- Answer management
- Sub-question handling
"""

from __future__ import annotations

import logging
import asyncio
from typing import Optional, List
from uuid import UUID

from src.dtos.question.req import CreateQuestionRequest, UpdateQuestionRequest
from src.entities.question import Question
from src.repos.question_repo import QuestionRepository
from src.repos.answer_repo import AnswerRepository
from src.repos.question_group_repo import QuestionGroupRepository

logger = logging.getLogger(__name__)


def _build_embedding_input(question_text: str, answers: Optional[List[dict]] = None) -> str:
    """Build embedding input from question text + answer values."""
    if not question_text:
        return ""
    if not answers or not isinstance(answers, list):
        return question_text

    answer_values = []
    for a in answers:
        if isinstance(a, dict) and a.get("value"):
            answer_values.append(a["value"])

    if answer_values:
        return f"{question_text} {', '.join(answer_values)}"
    return question_text


class QuestionMutationService:
    """Create, update, delete questions with vector embedding and grouping."""

    def __init__(self, llm_client):
        self._llm = llm_client
        self._q_repo = QuestionRepository()
        self._a_repo = AnswerRepository()
        self._group_repo = QuestionGroupRepository()

    async def create_question(
        self,
        payload: CreateQuestionRequest,
        created_by_id: Optional[UUID] = None,
    ) -> Question:
        """Create a new question with embedding and group assignment."""
        # Build embedding input and embed
        embedding_text = _build_embedding_input(
            payload.question_text,
            [a.model_dump() for a in payload.answers] if payload.answers else None,
        )
        vector = None
        if self._llm and embedding_text:
            vectors = await asyncio.to_thread(self._llm.embed, [embedding_text])
            if vectors is not None and len(vectors) > 0:
                vector = vectors[0]
                # Convert numpy array to list if needed
                if hasattr(vector, 'tolist'):
                    vector = vector.tolist()

        # Find or create group (if taxonomy complete)
        group_id = None
        if payload.subject and payload.topic and payload.difficulty and vector is not None:
            group = self._find_or_create_group(
                payload.subject,
                payload.topic,
                payload.difficulty,
                vector,
                created_by_id,
            )
            group_id = group.id if group else None

        # Create top-level question
        question = Question.create(
            question_text=payload.question_text,
            question_type=payload.question_type,
            difficulty=payload.difficulty,
            subject=payload.subject,
            topic=payload.topic,
            image_list=payload.image_list,
            questions_group_id=group_id,
            vector_embedding=vector,
            page_id=payload.page_id,
        )

        # Create answers
        if payload.answers:
            self._a_repo.create_batch(
                question.id,
                [a.model_dump() for a in payload.answers],
            )

        # Create sub-questions (if composite)
        if payload.sub_questions:
            for sq_input in payload.sub_questions:
                sq = Question.create(
                    parent_question_id=question.id,
                    question_text=sq_input.question_text,
                    question_type=sq_input.question_type,
                    sub_question_order=sq_input.sub_question_order,
                    image_list=sq_input.image_list,
                )
                if sq_input.answers:
                    self._a_repo.create_batch(
                        sq.id,
                        [a.model_dump() for a in sq_input.answers],
                    )

        logger.info(f"Created question {question.id}")
        return question

    async def update_question(
        self,
        question_id: UUID,
        payload: UpdateQuestionRequest,
    ) -> Question:
        """Update a question with optional re-embedding and re-grouping."""
        try:
            question = self._q_repo.get_by_id(question_id)
            if not question:
                raise ValueError(f"Question {question_id} not found")
        except Exception as e:
            logger.exception(f"Error loading question {question_id}: {e}")
            raise

        # Check if fields that affect embedding/grouping changed
        needs_regroup = (
            payload.reassign_group
            and (
                payload.question_text is not None
                or payload.answers is not None
                or payload.subject is not None
                or payload.topic is not None
                or payload.difficulty is not None
            )
        )

        # Re-embed if needed
        vector = question.vector_embedding
        # Convert numpy array to list if needed
        if hasattr(vector, 'tolist'):
            vector = vector.tolist()

        if needs_regroup:
            question_text = payload.question_text or question.question_text
            answers = (
                [a.model_dump() for a in payload.answers]
                if payload.answers is not None
                else [a.model_dump() for a in (question.answers or [])]
            )
            embedding_text = _build_embedding_input(question_text, answers)
            if self._llm and embedding_text:
                vectors = await asyncio.to_thread(self._llm.embed, [embedding_text])
                if vectors is not None and len(vectors) > 0:
                    vector = vectors[0]
                    # Convert numpy array to list if needed
                    if hasattr(vector, 'tolist'):
                        vector = vector.tolist()

            # Find or create new group
            subject = payload.subject or question.subject
            topic = payload.topic or question.topic
            difficulty = payload.difficulty or question.difficulty
            if subject and topic and difficulty and vector is not None:
                group = self._find_or_create_group(subject, topic, difficulty, vector)
                question.questions_group_id = group.id
            else:
                question.questions_group_id = None

        # Update fields
        if payload.question_text is not None:
            question.question_text = payload.question_text
        if payload.question_type is not None:
            question.question_type = payload.question_type
        if payload.difficulty is not None:
            question.difficulty = payload.difficulty
        if payload.subject is not None:
            question.subject = payload.subject
        if payload.topic is not None:
            question.topic = payload.topic
        if payload.image_list is not None:
            question.image_list = payload.image_list

        if vector is not None:
            question.vector_embedding = vector

        question.save()

        # Replace answers
        if payload.answers is not None:
            self._a_repo.delete_by_question(question.id)
            if payload.answers:
                self._a_repo.create_batch(
                    question.id,
                    [a.model_dump() for a in payload.answers],
                )

        # Replace sub-questions (if provided)
        if payload.sub_questions is not None:
            # Delete old sub-questions and their answers
            old_subs = self._q_repo.get_sub_questions(question.id)
            for sq in old_subs:
                self._a_repo.delete_by_question(sq.id)
                sq.delete_instance()

            # Create new sub-questions
            for sq_input in payload.sub_questions:
                sq = Question.create(
                    parent_question_id=question.id,
                    question_text=sq_input.question_text,
                    question_type=sq_input.question_type,
                    sub_question_order=sq_input.sub_question_order,
                    image_list=sq_input.image_list,
                )
                if sq_input.answers:
                    self._a_repo.create_batch(
                        sq.id,
                        [a.model_dump() for a in sq_input.answers],
                    )

        logger.info(f"Updated question {question.id}")
        return question

    def delete_question(self, question_id: UUID) -> bool:
        """Delete a question, its answers, and sub-questions."""
        question = self._q_repo.get_by_id(question_id)
        if not question:
            return False

        # Delete answers for sub-questions
        sub_questions = self._q_repo.get_sub_questions(question_id)
        for sq in sub_questions:
            self._a_repo.delete_by_question(sq.id)
            sq.delete_instance()

        # Delete answers for main question
        self._a_repo.delete_by_question(question_id)

        # Delete question
        question.delete_instance()

        logger.info(f"Deleted question {question_id}")
        return True

    def _find_or_create_group(
        self,
        subject: str,
        topic: str,
        difficulty: str,
        vector: Optional[List[float]],
        uploaded_by_id: Optional[UUID] = None,
    ):
        """Find or create a question group using vector similarity."""
        candidates = self._group_repo.find_by_metadata(
            subject, topic, difficulty, from_user_id=uploaded_by_id
        )

        if candidates and vector is not None:
            matches = self._group_repo.cosine_search(candidates, vector, threshold=0.75)
            if matches:
                return matches[0]

        return self._group_repo.create_with_vector(
            subject, topic, difficulty, vector if vector is not None else [], from_user_id=uploaded_by_id
        )
