from __future__ import annotations

from typing import List, Optional

from src.calculations.compute_score import cosine_similarity


def diversity_penalty(
    group_embedding,
    selected_embeddings: List,
) -> float:
    """Penalty = max cosine similarity between this group and already-selected groups.

    Returns 0.0 when nothing is selected yet or embeddings are missing.
    """
    if not selected_embeddings or group_embedding is None:
        return 0.0

    sims = []
    for sel_emb in selected_embeddings:
        if sel_emb is not None:
            sims.append(cosine_similarity(sel_emb, group_embedding))

    return max(sims) if sims else 0.0


def select_groups_greedy(
    candidates: list,
    top_k: int,
    random_level: str,
    query_embedding: Optional[List[float]] = None,
    diversity_weight: float = 0.3,
) -> list:
    """Greedy group selection maximising score while penalising redundancy.

    Args:
        candidates:       QuestionGroup objects with .vector_embedding and .existence_count
        top_k:            max groups to select
        random_level:     "low" | "medium" | "high" — controls randomisation alpha
        query_embedding:  optional semantic hint vector (from custom_text)
        diversity_weight: weight applied to the diversity penalty term

    Returns:
        list of selected groups, length <= top_k
    """
    from src.calculations.compute_score import compute_score

    selected = []
    selected_embeddings = []

    for _ in range(min(top_k, len(candidates))):
        best_group, best_score = None, float("-inf")

        for group in candidates:
            if group in selected:
                continue

            score = compute_score(
                group_embedding=group.vector_embedding,
                query_embedding=query_embedding,
                existence_count=group.existence_count,
                random_level=random_level,
            )
            penalty = diversity_penalty(group.vector_embedding, selected_embeddings)
            final = score - penalty * diversity_weight

            if final > best_score:
                best_group, best_score = group, final

        if best_group is None:
            break

        selected.append(best_group)
        selected_embeddings.append(best_group.vector_embedding)

    return selected
