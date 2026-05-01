from __future__ import annotations

import json
from typing import List, Optional

import numpy as np

_RANDOM_LEVEL_ALPHA = {"low": 0.1, "medium": 0.5, "high": 1.0}


def _parse_embedding(raw) -> Optional[np.ndarray]:
    if raw is None:
        return None
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            return None
    arr = np.array(raw, dtype=float)
    return arr if arr.size > 0 else None


def cosine_similarity(vec1: List[float], vec2) -> float:
    """Cosine similarity between two vectors. Returns 0.0 on zero-norm inputs."""
    v1 = np.array(vec1, dtype=float)
    v2 = _parse_embedding(vec2)
    if v2 is None:
        return 0.0
    n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
    if n1 == 0 or n2 == 0:
        return 0.0
    return float(np.dot(v1, v2) / (n1 * n2))


def compute_score(
    group_embedding,
    query_embedding: Optional[List[float]],
    existence_count: int,
    random_level: str = "medium",
) -> float:
    """Score a question group for selection.

    score = sim * 0.7 + exist_score * 0.3
      - sim: cosine similarity to query (0 if no query embedding)
      - exist_score: 1 / (existence_count + 1) ** alpha  (prefer fresh groups)
      - alpha: 0.1 (low randomness) → 1.0 (high randomness)
    """
    alpha = _RANDOM_LEVEL_ALPHA.get(random_level, 0.5)

    sim = 0.0
    if query_embedding and group_embedding is not None:
        sim = cosine_similarity(query_embedding, group_embedding)

    exist_score = 1.0 / (existence_count + 1) ** alpha
    return sim * 0.7 + exist_score * 0.3
