from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, TypedDict

from src.llm.base import GenerationConfig
from src.shared.base.base_pipeline import BasePipeline
from src.shared.constants.question import DifficultyLevel, QuestionType, Subject
from src.settings import get_settings
from src.prompts.question_extraction_prompt import question_extraction_prompt_template
from src.shared.helpers.debug_export import export_pipeline_debug

logger = logging.getLogger(__name__)


class ExtractedQuestion(TypedDict):
    question_text: str
    question_type: str
    difficulty: str | None
    subject: str | None
    subject_vi: str | None
    topic: str | None
    topic_vi: str | None
    answers: list | None
    image_list: list[str]
    sub_questions: list | None


class OverlapContent(TypedDict):
    previous_page: int
    content: str


class QuestionExtractionInput(TypedDict):
    page_number: int
    markdown_content: str
    overlap_content: Optional[OverlapContent]


class QuestionExtractionOutput(TypedDict):
    page_number: int
    questions: list[ExtractedQuestion]


class QuestionExtractionPipeline(
    BasePipeline[QuestionExtractionInput, QuestionExtractionOutput]
):
    """Extract and classify page questions using multimodal LLM input."""

    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.prompt_template_base = question_extraction_prompt_template

    def validate(self, payload: QuestionExtractionInput) -> None:
        """Validate input payload."""
        if "page_number" not in payload or "markdown_content" not in payload:
            raise ValueError(
                "Missing required input fields: page_number, markdown_content"
            )

    def postprocess(self, result: QuestionExtractionOutput) -> QuestionExtractionOutput:
        """Validate output structure before returning."""
        if not isinstance(result, dict):
            logger.error(
                f"QuestionExtractionPipeline postprocess: Invalid result type {type(result)}"
            )
            return {"page_number": 0, "questions": []}

        if "page_number" not in result or "questions" not in result:
            logger.error(
                f"QuestionExtractionPipeline postprocess: Missing required keys. Got: {list(result.keys())}"
            )
            return {"page_number": result.get("page_number", 0), "questions": []}

        # Ensure questions is a list
        if not isinstance(result["questions"], list):
            logger.error(
                f"QuestionExtractionPipeline postprocess: 'questions' is not a list, got {type(result['questions'])}"
            )
            result["questions"] = []

        return result

    async def process(
        self, payload: QuestionExtractionInput
    ) -> QuestionExtractionOutput:
        page_number = payload["page_number"]
        markdown_content = (payload.get("markdown_content") or "").strip()
        overlap_content = payload.get("overlap_content")

        export_pipeline_debug(
            "question_extraction",
            "input",
            {
                "page_number": page_number,
                "content_length": len(markdown_content),
                "has_overlap": overlap_content is not None,
            },
            page_number,
        )

        if not markdown_content:
            return {"page_number": page_number, "questions": []}

        if self.llm_client is None:
            return {"page_number": page_number, "questions": []}

        # Build overlap section for the prompt
        overlap_section = ""
        if overlap_content and isinstance(overlap_content, dict):
            previous_page = overlap_content.get("previous_page", page_number - 1)
            overlap_text = (overlap_content.get("content") or "").strip()
            if overlap_text:
                overlap_section = f"\nOverlap content from page {previous_page} (to resolve questions spanning pages):\n{overlap_text}"

        # Build injected variables
        question_types = ", ".join([f'"{qt.value}"' for qt in QuestionType])
        difficulty_levels = ", ".join([f'"{dl.value}"' for dl in DifficultyLevel])
        subjects = ", ".join([f'"{s.value}"' for s in Subject])

        prompt = self.prompt_template_base.format(
            markdown_content=markdown_content,
            overlap_section=overlap_section,
            question_types=question_types,
            difficulty_levels=difficulty_levels,
            subjects=subjects,
        )

        try:
            raw_response = await asyncio.to_thread(
                self.llm_client.generate,
                prompt,
                GenerationConfig(
                    temperature=0.1, response_mime_type="application/json"
                ),
            )

            logger.debug(
                "LLM raw response for page %s: %s", page_number, raw_response[:200]
            )

            parsed = self._extract_json_payload(raw_response)
            logger.debug(f"Parsed JSON structure keys: {list(parsed.keys())}")

            questions_raw = parsed.get("questions", [])
            questions = self._normalize_questions(questions_raw)

            logger.info(
                "Extracted %d questions from page %s",
                len(questions),
                page_number,
            )

            result: QuestionExtractionOutput = {
                "page_number": page_number,
                "questions": questions,
            }
            logger.debug(f"Question extraction result structure: {list(result.keys())}")

            export_pipeline_debug(
                "question_extraction",
                "output",
                {
                    "page_number": page_number,
                    "question_count": len(questions),
                    "questions_summary": [
                        {
                            "text": q.get("question_text", "")[:100],
                            "type": q.get("question_type"),
                            "difficulty": q.get("difficulty"),
                            "subject": q.get("subject"),
                            "subject_vi": q.get("subject_vi"),
                            "topic": q.get("topic"),
                            "topic_vi": q.get("topic_vi"),
                        }
                        for q in questions
                    ],
                },
                page_number,
            )

            return result
        except Exception as exc:
            logger.error(
                "Question extraction failed for page %s: %s",
                page_number,
                exc,
                exc_info=True,
            )
            export_pipeline_debug(
                "question_extraction",
                "error",
                {
                    "page_number": page_number,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
                page_number,
            )
            return {"page_number": page_number, "questions": []}

    @staticmethod
    def _extract_json_payload(raw_text: str) -> dict[str, Any]:
        text = (raw_text or "").strip()
        if not text:
            logger.warning("Empty response from LLM")
            return {"questions": []}

        candidates: list[str] = []

        # Strategy 1: Extract fenced JSON blocks
        fenced_greedy = re.findall(
            r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE
        )
        if fenced_greedy:
            candidates.extend(fenced_greedy)
            logger.debug(f"Found {len(fenced_greedy)} fenced JSON block(s)")

        # Strategy 2: Try the raw text directly
        candidates.append(text)

        # Try to parse each candidate
        for idx, candidate in enumerate(candidates):
            candidate = candidate.strip()
            if not candidate:
                continue

            # Pre-process to fix common LLM JSON errors
            cleaned = candidate

            # Normalize backslashes (escaping unescaped ones)
            cleaned = QuestionExtractionPipeline._normalize_backslashes(cleaned)

            # Fix trailing commas before closing brackets/braces
            cleaned = re.sub(r",(\s*[\]}])", r"\1", cleaned)

            # Fix string "null" to actual null
            cleaned = re.sub(r':\s*"null"', r": null", cleaned)
            cleaned = re.sub(r':\s*"null"\s*,', r": null,", cleaned)

            # Try direct parsing first
            try:
                parsed = json.loads(cleaned)
                if isinstance(parsed, dict):
                    logger.debug(f"Successfully parsed JSON from candidate {idx}")
                    return parsed
            except json.JSONDecodeError as e:
                logger.debug(
                    f"JSON parse attempt {idx} failed at pos {e.pos}: {str(e.msg)}"
                )

            # Try fixing trailing comma on the original
            if candidate.endswith(","):
                try:
                    fixed = json.loads(candidate[:-1])
                    if isinstance(fixed, dict):
                        logger.debug(
                            f"Successfully parsed JSON after removing trailing comma (candidate {idx})"
                        )
                        return fixed
                except json.JSONDecodeError:
                    pass

        # Strategy 3: Best-effort extraction of outermost JSON object
        start_idx = text.find("{")
        end_idx = text.rfind("}")
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            snippet = text[start_idx : end_idx + 1]
            logger.debug(
                f"Attempting to parse extracted JSON snippet (length: {len(snippet)})"
            )

            # Pre-process
            cleaned_snippet = snippet
            cleaned_snippet = QuestionExtractionPipeline._normalize_backslashes(
                cleaned_snippet
            )
            cleaned_snippet = re.sub(r",(\s*[\]}])", r"\1", cleaned_snippet)
            cleaned_snippet = re.sub(r':\s*"null"', r": null", cleaned_snippet)
            cleaned_snippet = re.sub(r':\s*"null"\s*,', r": null,", cleaned_snippet)

            # Try direct parsing
            try:
                parsed = json.loads(cleaned_snippet)
                if isinstance(parsed, dict):
                    logger.debug("Successfully parsed JSON from extracted snippet")
                    return parsed
            except json.JSONDecodeError as e:
                logger.debug(f"Snippet JSON parse failed at pos {e.pos}: {str(e.msg)}")

                # Strategy 4: Truncate from error position and recover
                if e.pos and e.pos > 0:
                    for trim_pos in range(e.pos, max(e.pos - 500, 0), -1):
                        try:
                            trimmed = snippet[:trim_pos]
                            # Pre-process
                            trimmed = QuestionExtractionPipeline._normalize_backslashes(
                                trimmed
                            )
                            trimmed = re.sub(r",(\s*[\]}])", r"\1", trimmed)
                            trimmed = re.sub(r':\s*"null"', r": null", trimmed)

                            # Skip incomplete strings
                            unclosed_quotes = trimmed.count('"') % 2
                            if unclosed_quotes:
                                last_quote = trimmed.rfind('"')
                                if last_quote > 0 and last_quote < len(trimmed) - 1:
                                    trimmed = trimmed[:last_quote]

                            # Close any open structures
                            open_braces = trimmed.count("{") - trimmed.count("}")
                            open_brackets = trimmed.count("[") - trimmed.count("]")

                            if open_braces > 0 or open_brackets > 0:
                                if trimmed.rstrip().endswith(","):
                                    trimmed = trimmed.rstrip()[:-1]
                                if trimmed.rstrip().endswith("["):
                                    trimmed = trimmed.rstrip()[:-1]
                                    trimmed = trimmed.rstrip()

                            if open_braces > 0:
                                trimmed += "}" * open_braces
                            if open_brackets > 0:
                                trimmed += "]" * open_brackets

                            parsed = json.loads(trimmed)
                            if isinstance(parsed, dict):
                                logger.warning(
                                    f"Successfully recovered JSON from error position {e.pos} (trimmed to {len(trimmed)} chars)"
                                )
                                return parsed
                        except (json.JSONDecodeError, ValueError):
                            continue

                # Strategy 5: Try backwards from end, finding last complete structure
                for trim_pos in range(len(snippet) - 1, max(len(snippet) - 500, 0), -1):
                    trimmed = snippet[:trim_pos]

                    # Pre-process
                    trimmed = QuestionExtractionPipeline._normalize_backslashes(trimmed)
                    trimmed = re.sub(r",(\s*[\]}])", r"\1", trimmed)
                    trimmed = re.sub(r':\s*"null"', r": null", trimmed)

        logger.error(
            f"Could not extract valid JSON from LLM response. Text length: {len(text)}, Preview: {text[:300]}..."
        )

        # Write failed JSON to debug file if debug mode is enabled
        settings = get_settings()
        if settings.debug:
            try:
                tmp_dir = Path("tmp")
                tmp_dir.mkdir(exist_ok=True)

                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
                debug_file = tmp_dir / f"failed_json_{timestamp}.txt"

                with open(debug_file, "w", encoding="utf-8") as f:
                    f.write("FAILED JSON PARSING DEBUG LOG\n")
                    f.write("=" * 80 + "\n")
                    f.write(f"Timestamp: {datetime.now().isoformat()}\n")
                    f.write(f"Text Length: {len(text)}\n")
                    f.write("=" * 80 + "\n\n")
                    f.write("RAW RESPONSE:\n")
                    f.write("-" * 80 + "\n")
                    f.write(text)
                    f.write("\n" + "-" * 80 + "\n")

                logger.debug(f"Dumped failed JSON to {debug_file}")
            except Exception as dump_error:
                logger.warning(f"Failed to write debug JSON file: {dump_error}")

        return {"questions": []}

    @staticmethod
    def _normalize_backslashes(text: str) -> str:
        """Normalize unescaped backslashes in JSON strings.
        
        Escapes backslashes that are not part of valid JSON escape sequences.
        Valid JSON escapes: \", \\, \\/, \b, \f, \n, \r, \t, \\uXXXX
        
        Args:
            text: Raw JSON text potentially containing unescaped backslashes
            
        Returns:
            Text with unescaped backslashes properly escaped as \\
        """
        # Replace backslashes that are:
        # 1. NOT preceded by another backslash (negative lookbehind: (?<!\\))
        # 2. NOT followed by valid JSON escape characters (negative lookahead: (?![\"\\\/bfnrtu]))
        # This prevents double-escaping already-escaped backslashes like \\frac
        normalized = re.sub(r"(?<!\\)\\(?![\"\\\/bfnrtu])", r"\\\\", text)
        return normalized

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
            subject_vi = cls._optional_str(item.get("subject_vi"))
            topic = cls._optional_str(item.get("topic"))
            topic_vi = cls._optional_str(item.get("topic_vi"))
            answers = cls._normalize_answers(item.get("answers"), question_type)
            sub_questions = cls._normalize_sub_questions(item.get("sub_questions", []))
            image_list = cls._normalize_image_list(item.get("image_list"))

            normalized.append(
                {
                    "question_text": question_text,
                    "question_type": question_type,
                    "difficulty": difficulty,
                    "subject": subject,
                    "subject_vi": subject_vi,
                    "topic": topic,
                    "topic_vi": topic_vi,
                    "answers": answers,
                    "image_list": image_list,
                    "sub_questions": sub_questions,
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
            "selection": QuestionType.SELECTION.value,
            "composite": QuestionType.COMPOSITE.value,
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
    def _normalize_answers(value: Any, question_type: str) -> list | None:
        """Normalize answers to list of {value, is_correct} dicts or null."""
        if value is None:
            return None

        # Ensure value is a list
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    value = parsed
                else:
                    value = [value]
            except json.JSONDecodeError:
                value = [value]
        elif not isinstance(value, list):
            value = [value]

        # Filter and normalize answer items
        answers = []
        for item in value:
            if isinstance(item, dict):
                # Already a dict with {value, is_correct} structure
                answer_val = str(item.get("value", "")).strip()
                if answer_val:
                    answers.append(item)
            else:
                # Plain string value
                answer_val = str(item).strip()
                if answer_val:
                    answers.append({"value": answer_val, "is_correct": False})

        return answers if answers else None

    @staticmethod
    def _normalize_sub_questions(value: Any) -> list[ExtractedQuestion]:
        if not isinstance(value, list):
            return []

        normalized_subs: list[ExtractedQuestion] = []
        for item in value:
            if not isinstance(item, dict):
                continue

            sub_question_text = str(
                item.get("sub_question_text") or item.get("question_text") or ""
            ).strip()
            if not sub_question_text:
                continue

            question_type = QuestionExtractionPipeline._normalize_question_type(
                item.get("question_type")
            )
            answers = QuestionExtractionPipeline._normalize_answers(
                item.get("answers"), question_type
            )

            # Extract order field (1-indexed)
            order = item.get("order")
            if order is not None:
                try:
                    order = int(order)
                except (ValueError, TypeError):
                    order = None

            normalized_subs.append(
                {
                    "sub_question_text": sub_question_text,
                    "question_type": question_type,
                    "answers": answers,
                    "order": order,
                }
            )

        return normalized_subs

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
