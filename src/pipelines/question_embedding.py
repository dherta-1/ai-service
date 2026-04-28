"""Embed Question records into vector_embedding using the LLM embedding client."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from src.shared.base.base_pipeline import BasePipeline

logger = logging.getLogger(__name__)

_BATCH_SIZE = 20


def _build_embedding_input(text: str, answers: Optional[list] = None) -> str:
    """Build embedding input from question text + answer values.

    Strategy: "<question_text> <answer1>, <answer2>, ..."
    """
    if not text:
        return ""
    if not answers or not isinstance(answers, list):
        return text

    answer_values = []
    for a in answers:
        if isinstance(a, dict) and a.get("value"):
            answer_values.append(a["value"])

    if answer_values:
        return f"{text} {', '.join(answer_values)}"
    return text


class QuestionEmbeddingPipeline(BasePipeline):
    """Embed extracted questions via LLM.

    Input payload keys:
        questions (list[Dict]): List of extracted question dicts with 'question_text' and optional 'answers'

    Returns:
        questions (list[Dict]): Same dicts enriched with 'vector' key containing the embedding
    """

    def __init__(self, llm_client):
        self.llm_client = llm_client

    def validate(self, payload: dict[str, Any]) -> None:
        if "questions" not in payload:
            raise ValueError("QuestionEmbeddingPipeline requires 'questions' key")

    async def process(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.llm_client is None:
            logger.warning("LLM client is None, skipping embeddings")
            questions = payload["questions"]
            for q in questions:
                q["vector"] = None
            return {"questions": questions}

        questions: list[Dict] = payload["questions"]
        if not questions:
            return {"questions": []}

        texts: list[str] = []
        for q in questions:
            text = _build_embedding_input(
                q.get("question_text", ""),
                q.get("answers")
            )
            texts.append(text)

        if not texts:
            for q in questions:
                q["vector"] = None
            return {"questions": questions}

        all_vectors: list[Optional[List[float]]] = []
        for i in range(0, len(texts), _BATCH_SIZE):
            batch = texts[i : i + _BATCH_SIZE]
            try:
                vectors = await asyncio.to_thread(self.llm_client.embed, batch)
                all_vectors.extend(vectors)
            except Exception as exc:
                logger.error("Embedding batch %d-%d failed: %s", i, i + len(batch), exc)
                all_vectors.extend([None] * len(batch))

        for q, vector in zip(questions, all_vectors):
            q["vector"] = vector

        logger.info("Embedded %d questions", len(questions))
        return {"questions": questions}
