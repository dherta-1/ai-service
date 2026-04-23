# RAG Recommendation for Test Generation Flow

## Context

Questions are extracted from uploaded exam documents and stored in the `Question` entity with the following key fields:
- `question_text`, `question_type`, `difficulty`, `subject`, `topic`
- `answers`, `correct_answer`, `sub_questions` (composite questions)
- `image_list`, `vector_embedding` (768-dim)
- Linked to `Page` → `Document` hierarchy

Sample data (from `docs/sample_res.json`) shows Vietnamese math exam questions across three types:
- `multiple_choice` — stem + 4 answer options, one correct
- `true_false` — standalone assertions (often sub-questions of a composite)
- `short_answer` — numeric or short-text answer, no options
- `composite` — shared stem with multiple sub-questions (true/false or short-answer parts)

---

## What to Embed (RAG Corpus)

### Primary embedding target: `question_text` only

Embed **only** the semantic text of questions. Do NOT prepend taxonomy metadata to the embedding input.

**Composite questions**: embed the parent `question_text` (shared stem) and each `sub_question_text` separately. The sub-question embedding should concatenate the parent stem for context:

```
embedding_input = f"{parent_question_text}\n{sub_question_text}"
```

Taxonomy fields (`subject`, `topic`, `question_type`, `difficulty`) are used as **SQL WHERE filters before cosine similarity search**, not as embedding prefixes. This separates concerns: semantic search focuses purely on text relevance, while topic/difficulty filtering ensures only candidate questions of the right taxonomy are considered.

### Do NOT embed

- `answers` list — noisy, often just "A/B/C/D" labels, hurts recall precision
- `correct_answer` alone — too short, semantically poor
- `image_list` URLs — non-semantic binary references
- Raw page `content` — too noisy; question-level granularity is always better

---

## Retrieval Strategy for Test Generation

### Query construction

When a user requests a test (e.g., "5 medium calculus questions"), construct the retrieval query as:

```
query_text = "Tìm câu hỏi liên quan đến tích phân và đạo hàm"
```

Use LLM to expand/rephrase the user intent into natural language for embedding. Do NOT include taxonomy metadata in the query text.

### Hybrid retrieval (recommended)

Combine vector search with **taxonomy pre-filtering** using SQL WHERE clauses:

```sql
SELECT * FROM questions
WHERE subject = 'math'
  AND difficulty = 'medium'
  AND topic = 'calculus'
ORDER BY vector_embedding <=> (
  SELECT embedding FROM query_embedding(?)
)
LIMIT 20;
```

This approach:
1. Pre-filters by taxonomy (SQL WHERE) to narrow the search space
2. Ranks candidates by semantic similarity (pgvector cosine distance)
3. Avoids false positives from off-topic questions that happen to mention similar keywords

### Question type distribution

When generating a test, retrieve candidates per type bucket:
- Retrieve N × 2 candidates per type (multiple_choice, true_false, short_answer)
- Let the LLM select the final N with the best coverage of sub-topics
- For composite questions, retrieve the parent and include all sub-questions as a group

### Re-ranking

After vector retrieval, apply a lightweight LLM re-rank pass to:
1. Deduplicate semantically near-identical questions (same concept, different phrasing)
2. Ensure difficulty spread matches the requested distribution
3. Prioritize questions with `image_list` non-empty only when the output format supports images

---

## Embedding Pipeline Notes (current: `src/pipelines/question_embedding.py`)

- Model: `gemini-embedding-001`, 768 dimensions (matches `VectorField(dimensions=768)`)
- Batch embed all questions after extraction completes (status = 0 → 1 transition)
- **Only embed text**, no taxonomy prefix. Empty or missing `question_text` skips embedding entirely.
- For composite questions: embed parent `question_text` + each `sub_question_text` concatenated with parent for context
- Store in `Question.vector_embedding`; sub-question vectors stored in `sub_questions` JSONB field as `{"sub_question_text": "...", "vector": [...]}`

---

## Summary Table

| Field | Embed? | Use as Filter? | Notes |
|---|---|---|---|
| `question_text` | ✅ Primary | No | Core semantic unit, no taxonomy prefix |
| `subject` | ❌ | ✅ WHERE clause | High-cardinality SQL filter |
| `topic` | ❌ | ✅ WHERE clause | Key filter dimension for retrieval |
| `difficulty` | ❌ | ✅ WHERE clause | Required for test balance filtering |
| `question_type` | ❌ | ✅ WHERE clause | Group by type during retrieval |
| `answers` | ❌ | No | Too noisy for embedding |
| `correct_answer` | ❌ | No | Not useful for retrieval |
| `sub_questions` | Embed each (with stem only) | No | Store vector inline in JSONB |
| `image_list` | ❌ | ✅ Filter (has_image) | Used to filter image-capable tests |
