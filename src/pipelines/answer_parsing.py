"""Answer Normalization Pipeline — pass-through pipeline for answer validation.

Since QuestionExtractionPipeline now normalizes answers to the proper format
({value, is_correct} dicts), this pipeline is a pass-through for compatibility
with the pipeline chain.

Input payload:
    {
        "questions": [
            {
                "question_text": str,
                "question_type": str,
                "answers": Optional[List[Dict{"value": str, "is_correct": bool}]],
                "sub_questions": Optional[list]
            },
            ...
        ]
    }

Output payload: Same as input (pass-through)
"""

from __future__ import annotations

import logging
from typing import Any

from src.shared.base.base_pipeline import BasePipeline

logger = logging.getLogger(__name__)


class AnswerParsingPipeline(BasePipeline):
    """Pass-through pipeline for answer structure validation.

    This pipeline is kept for backward compatibility with the existing
    pipeline chain. Answer normalization is now handled by
    QuestionExtractionPipeline._normalize_answers().
    """

    def validate(self, payload: dict[str, Any]) -> None:
        if "questions" not in payload:
            raise ValueError("AnswerParsingPipeline requires 'questions' key")

    async def process(self, payload: dict[str, Any]) -> dict[str, Any]:
        return payload
