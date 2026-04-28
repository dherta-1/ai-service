from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from src.entities.question_group import QuestionGroup
from src.shared.base.base_repo import BaseRepo


class QuestionGroupRepository(BaseRepo[QuestionGroup]):

    def __init__(self):
        super().__init__(QuestionGroup)

    def find_by_metadata(
        self, subject: str, topic: str, difficulty: str
    ) -> List[QuestionGroup]:
        return list(
            QuestionGroup.select().where(
                (QuestionGroup.subject == subject)
                & (QuestionGroup.topic == topic)
                & (QuestionGroup.difficulty == difficulty)
            )
        )

    def cosine_search(
        self,
        candidates: List[QuestionGroup],
        vector: List[float],
        threshold: float = 0.75,
    ) -> List[QuestionGroup]:
        """Search candidate question groups by vector embedding similarity.

        Returns groups whose embedding has cosine similarity >= threshold.
        Uses Python-based computation to avoid pgvector operator issues.

        Args:
            candidates: List of QuestionGroup objects to search within
            vector: Query vector for similarity computation
            threshold: Cosine similarity threshold (0.0-1.0)

        Returns:
            Sorted list of matching groups (best similarity first)
        """
        if not candidates or not vector:
            return []

        import numpy as np
        import json

        results = []
        q_vec = np.array(vector, dtype=float)
        norm_q = np.linalg.norm(q_vec)

        if norm_q == 0:
            return []

        for group in candidates:
            if group.vector_embedding is None:
                continue

            # Parse vector if it's a string
            embedding = group.vector_embedding
            if isinstance(embedding, str):
                embedding = json.loads(embedding)

            # Compute cosine similarity in Python
            g_vec = np.array(embedding, dtype=float)
            norm_g = np.linalg.norm(g_vec)

            if norm_g == 0:
                continue

            cosine_sim = float(np.dot(g_vec, q_vec) / (norm_g * norm_q))
            if cosine_sim >= threshold:
                results.append((cosine_sim, group))

        # Sort by similarity descending
        results.sort(key=lambda x: x[0], reverse=True)
        return [g for _, g in results]

    def create_with_vector(
        self,
        subject: str,
        topic: str,
        difficulty: str,
        vector: List[float],
    ) -> QuestionGroup:
        return QuestionGroup.create(
            subject=subject,
            topic=topic,
            difficulty=difficulty,
            existence_count=0,
            vector_embedding=vector,
        )

    def increment_existence_count(self, group_id: UUID) -> None:
        QuestionGroup.update(
            existence_count=QuestionGroup.existence_count + 1
        ).where(QuestionGroup.id == group_id).execute()
