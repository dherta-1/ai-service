"""Pipeline: generate an answer for a single question via LLM."""

from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any, Dict, List, Optional

from src.shared.base.base_pipeline import BasePipeline
from src.prompts.generate_answer_prompt import (
    build_generate_answer_prompt,
    parse_answer_response,
)

logger = logging.getLogger(__name__)


class QuestionAnswerGenPipeline(BasePipeline):
    """Generate an answer for a single question.

    Input payload keys:
        question     dict              Question dict (question_text, question_type,
                                       difficulty, subject, topic, answers, sub_questions)
        image_blobs  list[bytes]|None  Raw image bytes from S3

    Output payload keys:
        generated    dict              Parsed answer structure
    """

    def __init__(self, llm_client):
        self.llm_client = llm_client

    def validate(self, payload: Dict[str, Any]) -> None:
        if "question" not in payload:
            raise ValueError("QuestionAnswerGenPipeline requires 'question' key")
        if not payload["question"].get("question_text"):
            raise ValueError("question.question_text is required")
        if not payload["question"].get("question_type"):
            raise ValueError("question.question_type is required")

    async def process(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        question: dict = payload["question"]
        image_blobs: Optional[List[bytes]] = payload.get("image_blobs")
        language: str = payload.get("language", "en")
        question_type: str = question["question_type"]

        image_b64_list: Optional[List[str]] = None
        if image_blobs:
            image_b64_list = [
                base64.b64encode(blob).decode("utf-8") for blob in image_blobs
            ]

        prompt = build_generate_answer_prompt(
            question=question,
            has_images=bool(image_b64_list),
            language=language,
        )

        try:
            if image_b64_list and hasattr(self.llm_client, "generate_with_images"):
                raw = await asyncio.to_thread(
                    self.llm_client.generate_with_images, prompt, image_b64_list
                )
            else:
                raw = await asyncio.to_thread(self.llm_client.generate, prompt)
        except Exception as exc:
            logger.error("LLM call failed during answer generation: %s", exc)
            raise ValueError(f"LLM call failed: {exc}") from exc

        try:
            generated = parse_answer_response(raw, question_type)
        except ValueError as exc:
            logger.error("Failed to parse answer response: %s\nRaw: %s", exc, raw[:500])
            raise

        logger.info("Generated answer for question_type=%s", question_type)
        return {"generated": generated}
