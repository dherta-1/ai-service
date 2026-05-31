"""Service for generating and accepting answers for questions via LLM."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from src.pipelines.question_answer_gen import QuestionAnswerGenPipeline
from src.repos.answer_repo import AnswerRepository
from src.repos.question_repo import QuestionRepository

logger = logging.getLogger(__name__)

_CHOICE_TYPES = {"multiple_choice", "selection", "true_false"}
_OPEN_TYPES = {"short_answer", "essay"}


class GenerateAnswerService:
    """Generate answers for questions using LLM, then optionally persist them."""

    def __init__(self, llm_client, s3_client=None):
        self._llm = llm_client
        self._s3 = s3_client
        self._question_repo = QuestionRepository()
        self._answer_repo = AnswerRepository()
        self._pipeline = QuestionAnswerGenPipeline(llm_client)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate_answer(self, question_id: UUID, language: str = "en") -> Dict[str, Any]:
        """Fetch question from DB, run LLM pipeline, return generated answer.

        Returns:
            { "question_id": str, "generated": {...} }
        """
        question = self._question_repo.get_by_id(question_id)
        if not question:
            raise ValueError(f"Question {question_id} not found")

        answers = self._answer_repo.get_by_question(question_id)
        sub_questions_entities = self._question_repo.get_sub_questions(question_id)

        sub_questions_data: List[dict] = []
        for sq in sub_questions_entities:
            sq_answers = self._answer_repo.get_by_question(sq.id)
            sub_questions_data.append({
                "id": str(sq.id),
                "sub_question_order": sq.sub_question_order or 0,
                "question_text": sq.question_text,
                "question_type": sq.question_type,
                "answers": [
                    {"value": a.value, "is_correct": a.is_correct, "explaination": a.explaination}
                    for a in sq_answers
                ],
            })

        question_dict = {
            "id": str(question.id),
            "question_text": question.question_text,
            "question_type": question.question_type,
            "difficulty": question.difficulty,
            "subject": question.subject,
            "topic": question.topic,
            "answers": [
                {"value": a.value, "is_correct": a.is_correct, "explaination": a.explaination}
                for a in answers
            ],
            "sub_questions": sub_questions_data,
            "image_list": question.image_list or [],
        }

        image_blobs = await self._fetch_image_blobs(question.image_list or [])

        result = await self._pipeline.run({
            "question": question_dict,
            "image_blobs": image_blobs if image_blobs else None,
            "language": language,
        })

        return {
            "question_id": str(question_id),
            "generated": result["generated"],
        }

    async def accept_answer(self, question_id: UUID, payload: Dict[str, Any]) -> None:
        """Persist the accepted generated answer into the Answer table.

        For choice types: delete existing answers and re-create with updated is_correct.
        For open types: delete existing and create a single answer row.
        For composite: delegate per sub-question via sub_answers list.
        """
        question = self._question_repo.get_by_id(question_id)
        if not question:
            raise ValueError(f"Question {question_id} not found")

        answer_data = payload.get("answer") or {}
        q_type = question.question_type

        if q_type == "composite":
            await self._persist_composite_answers(question_id, answer_data)
        elif q_type in _OPEN_TYPES:
            self._persist_open_answer(question_id, answer_data)
        elif q_type in _CHOICE_TYPES:
            self._persist_choice_answers(question_id, answer_data)
        else:
            # Fallback: treat as open
            self._persist_open_answer(question_id, answer_data)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _fetch_image_blobs(self, image_list: List[str]) -> List[bytes]:
        """Download image blobs from S3 for the given file IDs."""
        if not image_list or not self._s3:
            return []

        blobs: List[bytes] = []
        for file_id in image_list:
            try:
                blob = await asyncio.to_thread(self._download_blob, file_id)
                if blob:
                    blobs.append(blob)
            except Exception as exc:
                logger.warning("Failed to download image %s: %s", file_id, exc)
        return blobs

    def _download_blob(self, file_id: str) -> Optional[bytes]:
        """Synchronously download a single file from S3."""
        try:
            from src.settings import get_settings
            settings = get_settings()
            bucket = getattr(settings, "aws_s3_bucket", None)
            if not bucket:
                return None
            obj = self._s3.client.get_object(Bucket=bucket, Key=file_id)
            return obj["Body"].read()
        except Exception as exc:
            logger.warning("S3 download failed for %s: %s", file_id, exc)
            return None

    def _persist_open_answer(self, question_id: UUID, answer_data: dict) -> None:
        """Replace answers for open-type question with single text answer."""
        self._answer_repo.delete_by_question(question_id)
        answer_text = answer_data.get("answer", "")
        explaination = answer_data.get("explaination")
        if answer_text:
            self._answer_repo.create_for_question(
                question_id=question_id,
                value=answer_text,
                is_correct=True,
                explaination=explaination,
            )

    def _persist_choice_answers(self, question_id: UUID, answer_data: dict) -> None:
        """Replace answers for choice-type question."""
        answers_list = answer_data.get("answers", [])
        if not answers_list:
            return
        self._answer_repo.delete_by_question(question_id)
        for a in answers_list:
            self._answer_repo.create_for_question(
                question_id=question_id,
                value=a.get("value", ""),
                is_correct=bool(a.get("is_correct", False)),
                explaination=a.get("explaination") or None,
            )

    async def _persist_composite_answers(
        self, question_id: UUID, answer_data: dict
    ) -> None:
        """Persist answers for each sub-question in a composite question."""
        sub_answers = answer_data.get("sub_answers", [])
        if not sub_answers:
            return

        sub_questions = self._question_repo.get_sub_questions(question_id)
        sq_by_order = {sq.sub_question_order: sq for sq in sub_questions}

        for sa in sub_answers:
            order = sa.get("sub_question_order")
            sub_q = sq_by_order.get(order)
            if not sub_q:
                logger.warning("Sub-question with order %s not found", order)
                continue

            sq_type = sub_q.question_type
            if sq_type in _OPEN_TYPES:
                self._persist_open_answer(sub_q.id, sa)
            else:
                self._persist_choice_answers(sub_q.id, sa)
