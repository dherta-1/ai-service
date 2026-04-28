"""Question Grouping Pipeline — finds or creates a QuestionGroup.

Specification (Persist câu hỏi step 2-3):
  1. Query question_groups by subject + topic + difficulty
  2. Cosine-search candidates against the question vector
  3. If similarity >= threshold → reuse group with highest similarity
  4. Otherwise → create new group
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from src.entities.question_group import QuestionGroup
from src.repos.question_group_repo import QuestionGroupRepository
from src.shared.base.base_pipeline import BasePipeline

logger = logging.getLogger(__name__)


class QuestionGroupingPipeline(BasePipeline):
    """Find or create a QuestionGroup for extracted questions.

    Input payload:
        {
            "questions": [
                {
                    "subject": str,
                    "topic": str,
                    "difficulty": str,
                    "vector": List[float]
                },
                ...
            ],
            "similarity_threshold": float (default 0.75)
        }

    Output payload:
        {
            "grouped_questions": [
                {
                    "subject": str,
                    "topic": str,
                    "difficulty": str,
                    "vector": List[float],
                    "group_id": UUID
                },
                ...
            ]
        }
    """

    def __init__(self, similarity_threshold: float = 0.75):
        self._repo = QuestionGroupRepository()
        self._threshold = similarity_threshold

    def validate(self, payload: dict[str, Any]) -> None:
        if "questions" not in payload:
            raise ValueError("QuestionGroupingPipeline requires 'questions' key")

    async def process(self, payload: dict[str, Any]) -> dict[str, Any]:
        questions = payload.get("questions", [])
        threshold = payload.get("similarity_threshold", self._threshold)

        grouped = []
        for q_data in questions:
            subject = q_data.get("subject")
            topic = q_data.get("topic")
            difficulty = q_data.get("difficulty")
            vector = q_data.get("vector")

            if not (subject and topic and difficulty):
                group_id = None
            else:
                group = self._find_or_create_group(
                    subject, topic, difficulty, vector, threshold
                )
                group_id = group.id if group else None

            grouped.append(
                {
                    "subject": subject,
                    "topic": topic,
                    "difficulty": difficulty,
                    "vector": vector,
                    "group_id": group_id,
                    **{
                        k: v
                        for k, v in q_data.items()
                        if k not in ["subject", "topic", "difficulty", "vector"]
                    },
                }
            )

        return {"grouped_questions": grouped}

    def _find_or_create_group(
        self,
        subject: str,
        topic: str,
        difficulty: str,
        vector: Optional[List[float]],
        threshold: float,
    ) -> Optional[QuestionGroup]:
        """Find or create a question group using two-step matching.

        Step 1: Filter by taxonomy (subject, topic, difficulty)
        Step 2: Search filtered candidates by vector embedding similarity

        This approach allows multiple groups with the same taxonomy while using
        vector similarity as the primary matching criterion within that taxonomy.
        """
        # Step 1: Filter candidates by taxonomy
        candidates = self._repo.find_by_metadata(subject, topic, difficulty)

        # Step 2: Search candidates by vector similarity
        if candidates and vector:
            matches = self._repo.cosine_search(candidates, vector, threshold)
            if matches:
                best = matches[0]
                # Don't increment count for existence_count since it will use for exam generation only, not for counting how many questions in the group
                # self._repo.increment_existence_count(best.id)
                logger.debug(
                    "Reused QuestionGroup %s (vector match) for %s/%s/%s",
                    best.id,
                    subject,
                    topic,
                    difficulty,
                )
                return best

        group = self._repo.create_with_vector(subject, topic, difficulty, vector or [])
        logger.debug(
            "Created new QuestionGroup %s for %s/%s/%s",
            group.id,
            subject,
            topic,
            difficulty,
        )
        return group
