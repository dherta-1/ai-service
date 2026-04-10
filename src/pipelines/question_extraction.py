from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any, TypedDict

from src.llm.base import GenerationConfig
from src.shared.base.base_pipeline import BasePipeline
from src.shared.constants.question import DifficultyLevel, QuestionType, Subject

logger = logging.getLogger(__name__)


class ExtractedQuestion(TypedDict):
    question_text: str
    question_type: str
    difficulty: str | None
    subject: str | None
    topic: str | None
    answers: str | None
    correct_answer: str | None
    image_list: list[str]


class QuestionExtractionInput(TypedDict):
    image_path: Path
    page_number: int
    markdown_content: str


class QuestionExtractionOutput(TypedDict):
    page_number: int
    questions: list[ExtractedQuestion]


class QuestionExtractionPipeline(
    BasePipeline[QuestionExtractionInput, QuestionExtractionOutput]
):
    """Extract and classify page questions using multimodal LLM input."""

    def __init__(self, llm_client, prompt_template: str):
        self.llm_client = llm_client
        self.prompt_template = prompt_template

    def validate(self, payload: QuestionExtractionInput) -> None:
        image_path = payload.get("image_path")
        if not isinstance(image_path, Path) or not image_path.exists():
            raise FileNotFoundError(f"Image path not found: {image_path}")

    async def process(
        self, payload: QuestionExtractionInput
    ) -> QuestionExtractionOutput:
        page_number = payload["page_number"]
        markdown_content = (payload.get("markdown_content") or "").strip()
        image_path = payload["image_path"]

        if not markdown_content:
            return {"page_number": page_number, "questions": []}

        if self.llm_client is None:
            return {"page_number": page_number, "questions": []}

        prompt = self.prompt_template.format(markdown_content=markdown_content)

        try:
            raw_response = await asyncio.to_thread(
                self.llm_client.generate_file,
                str(image_path),
                prompt,
                GenerationConfig(temperature=0.1),
            )

            logger.debug(
                "LLM raw response for page %s: %s", page_number, raw_response[:200]
            )

            parsed = self._extract_json_payload(raw_response)
            questions_raw = parsed.get("questions", [])
            questions = self._normalize_questions(questions_raw)

            logger.info(
                "Extracted %d questions from page %s",
                len(questions),
                page_number,
            )

            return {
                "page_number": page_number,
                "questions": questions,
            }
        except Exception as exc:
            logger.error(
                "Question extraction failed for page %s: %s",
                page_number,
                exc,
                exc_info=True,
            )
            return {"page_number": page_number, "questions": []}

    @staticmethod
    def _extract_json_payload(raw_text: str) -> dict[str, Any]:
        text = (raw_text or "").strip()
        if not text:
            logger.warning("Empty response from LLM")
            return {"questions": []}

        # Prefer fenced JSON if model wraps response.
        fenced = re.findall(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
        candidates = fenced + [text]

        for candidate in candidates:
            candidate = candidate.strip()
            if not candidate:
                continue
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    logger.debug("Successfully parsed JSON from LLM response")
                    return parsed
            except json.JSONDecodeError as e:
                logger.debug("JSON parse attempt failed: %s", str(e)[:100])
                pass

        # Best-effort: extract outermost JSON object from noisy content.
        start_idx = text.find("{")
        end_idx = text.rfind("}")
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            snippet = text[start_idx : end_idx + 1]
            try:
                parsed = json.loads(snippet)
                if isinstance(parsed, dict):
                    logger.debug("Successfully parsed JSON from extracted snippet")
                    return parsed
            except json.JSONDecodeError as e:
                logger.debug("Snippet JSON parse failed: %s", str(e)[:100])
                pass

        logger.error("Could not extract valid JSON from LLM response: %s", text[:300])
        return {"questions": []}

    @classmethod
    def _normalize_questions(cls, questions_raw: Any) -> list[ExtractedQuestion]:
        if not isinstance(questions_raw, list):
            return []

        normalized: list[ExtractedQuestion] = []
        for item in questions_raw:
            if not isinstance(item, dict):
                continue

            question_text = str(item.get("question_text") or "").strip()
            if not question_text:
                continue

            question_type = cls._normalize_question_type(item.get("question_type"))
            difficulty = cls._normalize_difficulty(item.get("difficulty"))
            subject = cls._normalize_subject(item.get("subject"))
            topic = cls._optional_str(item.get("topic"))
            answers = cls._normalize_answers(item.get("answers"), question_type)
            correct_answer = cls._optional_str(item.get("correct_answer"))
            image_list = cls._normalize_image_list(item.get("image_list"))

            normalized.append(
                {
                    "question_text": question_text,
                    "question_type": question_type,
                    "difficulty": difficulty,
                    "subject": subject,
                    "topic": topic,
                    "answers": answers,
                    "correct_answer": correct_answer,
                    "image_list": image_list,
                }
            )

        return normalized

    @staticmethod
    def _optional_str(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _normalize_question_type(value: Any) -> str:
        raw = str(value or "").strip().lower()
        aliases = {
            "mcq": QuestionType.MULTIPLE_CHOICE.value,
            "multiple choice": QuestionType.MULTIPLE_CHOICE.value,
            "multiple-choice": QuestionType.MULTIPLE_CHOICE.value,
            "true/false": QuestionType.TRUE_FALSE.value,
            "true false": QuestionType.TRUE_FALSE.value,
            "short answer": QuestionType.SHORT_ANSWER.value,
        }
        normalized = aliases.get(raw, raw)
        allowed = {item.value for item in QuestionType}
        if normalized in allowed:
            return normalized
        return QuestionType.SHORT_ANSWER.value

    @staticmethod
    def _normalize_difficulty(value: Any) -> str | None:
        raw = str(value or "").strip().lower()
        allowed = {item.value for item in DifficultyLevel}
        if raw in allowed:
            return raw
        return None

    @staticmethod
    def _normalize_subject(value: Any) -> str | None:
        raw = str(value or "").strip().lower()
        aliases = {
            "mathematics": Subject.MATH.value,
            "physics": Subject.SCIENCE.value,
            "chemistry": Subject.SCIENCE.value,
            "biology": Subject.SCIENCE.value,
            "english": Subject.LITERATURE.value,
        }
        normalized = aliases.get(raw, raw)
        allowed = {item.value for item in Subject}
        if normalized in allowed:
            return normalized
        return None

    @staticmethod
    def _normalize_answers(value: Any, question_type: str) -> str | None:
        if question_type in {QuestionType.SHORT_ANSWER.value, QuestionType.ESSAY.value}:
            return None

        if value is None:
            if question_type == QuestionType.TRUE_FALSE.value:
                return json.dumps(["True", "False"])
            return None

        # Keep storage shape aligned to entity: JSON string.
        if isinstance(value, list):
            cleaned = [str(item).strip() for item in value if str(item).strip()]
            return json.dumps(cleaned) if cleaned else None

        text = str(value).strip()
        if not text:
            return None

        # If model already returned JSON array in text form, keep as normalized JSON.
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                cleaned = [str(item).strip() for item in parsed if str(item).strip()]
                return json.dumps(cleaned) if cleaned else None
        except json.JSONDecodeError:
            pass

        return text

    @staticmethod
    def _normalize_image_list(value: Any) -> list[str]:
        if value is None:
            return []

        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]

        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed if str(item).strip()]
            except json.JSONDecodeError:
                return [text]

        return []
