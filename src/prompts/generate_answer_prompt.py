"""Prompt template for generating answers to exam questions via LLM."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List


_CHOICE_TYPES = {"multiple_choice", "selection", "true_false"}
_OPEN_TYPES = {"short_answer", "essay"}


_LANGUAGE_NAMES: Dict[str, str] = {
    "vi": "Vietnamese",
    "en": "English",
}


def build_generate_answer_prompt(
    question: Dict[str, Any],
    has_images: bool = False,
    language: str = "en",
) -> str:
    """Build a prompt instructing the LLM to produce an answer for the given question.

    Args:
        question: Question dict with keys: question_text, question_type, difficulty,
                  subject, topic, answers (existing options), sub_questions.
        has_images: Whether image blobs will be attached to the LLM call.
        language: BCP-47 language code for explanation language (e.g. "en", "vi").

    Returns:
        Formatted prompt string.
    """
    q_text = question.get("question_text", "")
    q_type = question.get("question_type", "")
    difficulty = question.get("difficulty", "")
    subject = question.get("subject", "")
    topic = question.get("topic", "")
    existing_answers = question.get("answers") or []
    sub_questions = question.get("sub_questions") or []

    lang_name = _LANGUAGE_NAMES.get(language, "English")

    image_note = (
        "\nNote: Images are attached — use their content to inform your answer.\n"
        if has_images
        else ""
    )

    if q_type in _OPEN_TYPES:
        schema_instruction = _open_schema_instruction()
    elif q_type in _CHOICE_TYPES:
        schema_instruction = _choice_schema_instruction(q_type, existing_answers)
    elif q_type == "composite":
        schema_instruction = _composite_schema_instruction(sub_questions)
    else:
        schema_instruction = _open_schema_instruction()

    prompt = f"""You are an expert educator. Your task is to generate a correct, well-explained answer for the following exam question.
{image_note}
## Question
Text: {q_text}
Type: {q_type}
Difficulty: {difficulty}
Subject: {subject}
Topic: {topic}

{schema_instruction}

IMPORTANT:
- Return ONLY valid JSON matching the schema above — no extra text or markdown fences.
- Write ALL explanations in {lang_name}.
- Explanations should be concise and educational.
- For choice questions, mark exactly the correct option(s) with "is_correct": true.
"""
    return prompt


def _open_schema_instruction() -> str:
    return """\
## Output Schema (JSON)
Return a single JSON object:
{
  "answer": "<the correct answer text>",
  "explaination": "<brief explanation of why this is correct>"
}"""


def _choice_schema_instruction(q_type: str, existing_answers: List[dict]) -> str:
    if existing_answers:
        options_repr = json.dumps(
            [{"value": a.get("value", "")} for a in existing_answers],
            ensure_ascii=False,
        )
        options_note = (
            f"The existing answer options are:\n{options_repr}\n"
            "Identify which option(s) are correct and add explanations."
        )
    else:
        options_note = "Generate appropriate answer options for the question type."

    if q_type == "true_false":
        example = json.dumps(
            {
                "answers": [
                    {"value": "True", "is_correct": True, "explaination": "Because ..."},
                    {"value": "False", "is_correct": False, "explaination": ""},
                ]
            },
            ensure_ascii=False,
            indent=2,
        )
    elif q_type == "selection":
        example = json.dumps(
            {
                "answers": [
                    {"value": "Option A", "is_correct": True, "explaination": "Because ..."},
                    {"value": "Option B", "is_correct": True, "explaination": "Because ..."},
                    {"value": "Option C", "is_correct": False, "explaination": ""},
                ]
            },
            ensure_ascii=False,
            indent=2,
        )
    else:
        example = json.dumps(
            {
                "answers": [
                    {"value": "Option A", "is_correct": False, "explaination": ""},
                    {"value": "Option B", "is_correct": True, "explaination": "Because ..."},
                    {"value": "Option C", "is_correct": False, "explaination": ""},
                ]
            },
            ensure_ascii=False,
            indent=2,
        )

    return f"""\
{options_note}

## Output Schema (JSON)
Return a single JSON object matching this structure:
{example}"""


def _composite_schema_instruction(sub_questions: List[dict]) -> str:
    sub_items = []
    for sq in sub_questions:
        order = sq.get("sub_question_order", 0)
        sq_type = sq.get("question_type", "short_answer")
        sq_answers = sq.get("answers") or []

        if sq_type in _OPEN_TYPES:
            sub_schema: dict = {
                "sub_question_order": order,
                "answer": "<answer>",
                "explaination": "<explanation>",
            }
        else:
            if sq_answers:
                sub_schema = {
                    "sub_question_order": order,
                    "answers": [
                        {"value": a.get("value", ""), "is_correct": False, "explaination": ""}
                        for a in sq_answers
                    ],
                }
            else:
                sub_schema = {
                    "sub_question_order": order,
                    "answers": [
                        {"value": "Option A", "is_correct": True, "explaination": "<why>"},
                        {"value": "Option B", "is_correct": False, "explaination": ""},
                    ],
                }
        sub_items.append(sub_schema)

    sub_questions_text = "\n".join(
        f"  {i + 1}. [{sq.get('question_type', '')}] {sq.get('question_text', '')}"
        for i, sq in enumerate(sub_questions)
    )

    schema_example = json.dumps({"sub_answers": sub_items}, ensure_ascii=False, indent=2)

    return f"""\
This is a composite question with the following sub-questions:
{sub_questions_text}

## Output Schema (JSON)
Return a single JSON object with answers for each sub-question:
{schema_example}

For open-type sub-questions use {{ "answer": "...", "explaination": "..." }}.
For choice-type sub-questions use {{ "answers": [...] }} with is_correct flags."""


def parse_answer_response(response_text: str, question_type: str) -> Dict[str, Any]:
    """Parse the LLM JSON response into a structured answer dict.

    Args:
        response_text: Raw LLM response.
        question_type: The question type to guide validation.

    Returns:
        Parsed dict matching one of the three schema shapes.

    Raises:
        ValueError: If JSON cannot be parsed or required keys are missing.
    """
    text = response_text.strip()

    # Strip markdown fences if present
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()

    obj_match = re.search(r"\{[\s\S]*\}", text)
    if not obj_match:
        raise ValueError("No JSON object found in LLM response")

    json_str = obj_match.group(0)
    # Escape bare backslashes not part of valid JSON escape sequences
    json_str = re.sub(r'(?<!\\)\\(?!["\\/bfnrtu])', r'\\\\', json_str)

    try:
        parsed = json.loads(json_str)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Failed to parse LLM JSON response: {exc}") from exc

    if not isinstance(parsed, dict):
        raise ValueError("Expected JSON object in LLM response")

    if question_type == "composite":
        if "sub_answers" not in parsed:
            raise ValueError("Expected 'sub_answers' key for composite question")
    elif question_type in _OPEN_TYPES:
        if "answer" not in parsed:
            raise ValueError("Expected 'answer' key for open-type question")
    elif question_type in _CHOICE_TYPES:
        if "answers" not in parsed:
            raise ValueError("Expected 'answers' key for choice-type question")

    return parsed
