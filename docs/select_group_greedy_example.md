# `select_groups_greedy` — Worked Example

## Setup

| Parameter | Value |
|-----------|-------|
| `top_k` | 2 |
| `random_level` | `"medium"` → α = 0.5 |
| `diversity_weight` | 0.3 (default) |
| `query_embedding` | provided (some topic query vector) |

### Candidate Groups

| Group | `existence_count` | Assumed cosine sim to **query** | Notes |
|-------|------------------|---------------------------------|-------|
| G1 | 4 | 0.90 | Very relevant, but heavily reused |
| G2 | 1 | 0.80 | Relevant, lightly used |
| G3 | 1 | 0.78 | Slightly less relevant, similar topic to G2 |

### Assumed pairwise cosine similarities (between groups)

| | G1 | G2 | G3 |
|---|---|---|---|
| G1 | — | 0.30 | 0.25 |
| G2 | 0.30 | — | 0.85 |
| G3 | 0.25 | 0.85 | — |

G2 and G3 are semantically close to each other (0.85); both are distant from G1.

---

## Score Formula

```
compute_score = sim * 0.7  +  exist_score * 0.3
  where:
    sim         = cosine_similarity(query_embedding, group_embedding)
    exist_score = 1 / (existence_count + 1) ** alpha
    alpha       = 0.5  (medium)

final_score = compute_score  -  diversity_penalty * diversity_weight
  where:
    diversity_penalty = max cosine_similarity(group, already_selected_groups)
    diversity_weight  = 0.3
```

---

## Iteration 1 — `selected = []`

`selected_embeddings` is empty → `diversity_penalty = 0.0` for every candidate.

### G1
```
exist_score = 1 / (4 + 1)^0.5 = 1 / √5 = 1 / 2.236 ≈ 0.447
score       = 0.90 * 0.7 + 0.447 * 0.3
            = 0.630 + 0.134 = 0.764
penalty     = 0.0  (nothing selected yet)
final       = 0.764 - 0.0 * 0.3 = 0.764
```

### G2
```
exist_score = 1 / (1 + 1)^0.5 = 1 / √2 ≈ 0.707
score       = 0.80 * 0.7 + 0.707 * 0.3
            = 0.560 + 0.212 = 0.772
penalty     = 0.0
final       = 0.772
```

### G3
```
exist_score = 1 / (1 + 1)^0.5 ≈ 0.707
score       = 0.78 * 0.7 + 0.707 * 0.3
            = 0.546 + 0.212 = 0.758
penalty     = 0.0
final       = 0.758
```

### Iteration 1 result

| Group | final_score |
|-------|------------|
| G1 | 0.764 |
| **G2** | **0.772** ← highest |
| G3 | 0.758 |

**→ G2 selected.** `selected_embeddings = [emb_G2]`

---

## Iteration 2 — `selected = [G2]`

`diversity_penalty(group, [emb_G2])` = cosine_similarity(emb_G2, group_embedding)

### G1
```
penalty = cosine_similarity(G2, G1) = 0.30
final   = 0.764 - 0.30 * 0.3
        = 0.764 - 0.090 = 0.674
```

### G3
```
penalty = cosine_similarity(G2, G3) = 0.85
final   = 0.758 - 0.85 * 0.3
        = 0.758 - 0.255 = 0.503
```

### Iteration 2 result

| Group | base_score | penalty | final_score |
|-------|-----------|---------|------------|
| **G1** | 0.764 | 0.30 | **0.674** ← highest |
| G3 | 0.758 | 0.85 | 0.503 |

**→ G1 selected.**

---

## Final Selection

```
selected = [G2, G1]
```

Even though G1 had the highest raw similarity to the query (0.90), its high `existence_count` lowered its base score enough that G2 was picked first. Then, G3 was skipped in round 2 because it is semantically very close to the already-selected G2 (penalty = 0.85 × 0.3 = 0.255), while G1 is distant from G2 (penalty = 0.30 × 0.3 = 0.09), making G1 the better diverse pick.

---

## Key Takeaways

| Mechanism | Effect in this example |
|-----------|------------------------|
| `exist_score` (freshness) | Penalises G1 for being reused 4 times; boosts G2/G3 used only once |
| `diversity_penalty` | Kills G3 in round 2 because it overlaps heavily with already-selected G2 |
| `diversity_weight` | Scales how aggressively redundancy is suppressed (0.3 = moderate) |
| `alpha` (random_level) | `medium` (0.5) balances freshness vs relevance; `low` would nearly ignore reuse |
