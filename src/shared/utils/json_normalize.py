"""Utilities for extracting and normalizing JSON returned by LLMs."""

from __future__ import annotations

import json
import re
from typing import Any


def extract_json_object(raw_text: str) -> dict[str, Any]:
    """Extract the first valid JSON object from LLM output text, including fenced code blocks."""
    text = (raw_text or "").strip()
    if not text:
        raise ValueError("Empty LLM response")

    candidates: list[str] = []

    # Prefer JSON fenced blocks such as ```json {...}``` or ```{...}```
    fence_matches = re.findall(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    for raw_block in fence_matches:
        trimmed = raw_block.strip()
        if trimmed:
            # If wrapped in braces, keep as is. Otherwise try to extract object/array snippet.
            start = trimmed.find("{")
            end = trimmed.rfind("}")
            if start != -1 and end != -1 and end > start:
                candidates.append(trimmed[start : end + 1])
            else:
                candidates.append(trimmed)

    # Fallback: loose JSON anywhere in text
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidates.append(text[start : end + 1])

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue

    raise ValueError("Could not parse valid JSON object from LLM response")


def normalize_exam_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Ensure output has stable keys and structure for exam extraction."""
    if "exam_data" not in payload or not isinstance(payload["exam_data"], list):
        payload["exam_data"] = []

    normalized_rows = []
    for row in payload["exam_data"]:
        if not isinstance(row, dict):
            continue

        options = row.get("options") if isinstance(row.get("options"), dict) else {}
        classification = (
            row.get("classification")
            if isinstance(row.get("classification"), dict)
            else {}
        )
        ill = (
            row.get("illustration_box")
            if isinstance(row.get("illustration_box"), dict)
            else None
        )

        normalized_rows.append(
            {
                "question_number": str(row.get("question_number", "")).strip(),
                "content": str(row.get("content", "")).strip(),
                "options": {
                    "A": str(options.get("A", "")).strip(),
                    "B": str(options.get("B", "")).strip(),
                    "C": str(options.get("C", "")).strip(),
                    "D": str(options.get("D", "")).strip(),
                },
                "classification": {
                    "subject": str(classification.get("subject", "")).strip(),
                    "topic": str(classification.get("topic", "")).strip(),
                    "level": str(classification.get("level", "")).strip(),
                },
                "illustration_box": ill,
            }
        )

    return {"exam_data": normalized_rows}
