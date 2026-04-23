"""Embed Question records into vector_embedding using the LLM embedding client."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from src.entities.question import Question
from src.shared.base.base_pipeline import BasePipeline

logger = logging.getLogger(__name__)

_BATCH_SIZE = 20


def _build_embedding_input(question: Question) -> str:
    """Return the question text for embedding.

    Only embed the semantic text content; taxonomy (subject, topic, type, difficulty)
    will be used for SQL WHERE filters before cosine similarity search.
    """
    return question.question_text or ""


def _build_sub_question_embedding_input(parent_text: str, sub_question_text: str) -> str:
    """Return sub-question text prefixed with parent stem for context."""
    return f"{parent_text}\n{sub_question_text}"


class QuestionEmbeddingPipeline(BasePipeline):
    """Compute and persist vector embeddings for a list of Question ORM objects.

    Input payload keys:
        questions (list[Question]): ORM instances already saved to DB.

    Returns the same list with vector_embedding populated.
    """

    def __init__(self, llm_client):
        self.llm_client = llm_client

    def validate(self, payload: dict[str, Any]) -> None:
        if "questions" not in payload:
            raise ValueError("QuestionEmbeddingPipeline requires 'questions' key")

    async def process(self, payload: dict[str, Any]) -> dict[str, Any]:
        questions: list[Question] = payload["questions"]
        if not questions:
            return {"questions": []}

        # Build texts and track which question each text belongs to.
        # For composite questions we also embed each sub-question and store the
        # vector inline in the sub_questions JSONB field.
        texts: list[str] = []
        meta: list[dict] = []  # {"type": "main"|"sub", "question": q, "sub_idx": int}

        for q in questions:
            main_text = _build_embedding_input(q)
            if main_text:
                texts.append(main_text)
                meta.append({"type": "main", "question": q})

            sub_questions: list[dict] = q.sub_questions or []
            for idx, sub in enumerate(sub_questions):
                sub_text = sub.get("sub_question_text", "")
                if sub_text:
                    texts.append(
                        _build_sub_question_embedding_input(q.question_text or "", sub_text)
                    )
                    meta.append({"type": "sub", "question": q, "sub_idx": idx})

        # Batch embed to avoid oversized requests
        if not texts:
            return {"questions": questions}

        all_vectors: list[list[float]] = []
        for i in range(0, len(texts), _BATCH_SIZE):
            batch = texts[i : i + _BATCH_SIZE]
            try:
                vectors = await asyncio.to_thread(self.llm_client.embed, batch)
                all_vectors.extend(vectors)
            except Exception as exc:
                logger.error(
                    "Embedding batch %d-%d failed: %s", i, i + len(batch), exc
                )
                all_vectors.extend([None] * len(batch))

        # Write vectors back
        for entry, vector in zip(meta, all_vectors):
            q = entry["question"]
            if entry["type"] == "main":
                if vector is not None:
                    q.vector_embedding = vector
            else:
                idx = entry["sub_idx"]
                subs: list[dict] = q.sub_questions or []
                if idx < len(subs) and vector is not None:
                    subs[idx]["vector"] = vector
                    q.sub_questions = subs

        # Persist in a thread (Peewee is synchronous)
        def _save_all():
            for q in questions:
                q.save()

        await asyncio.to_thread(_save_all)
        logger.info("Embedded and saved %d questions", len(questions))
        return {"questions": questions}
