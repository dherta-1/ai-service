# Schema Recommendation for Test Generation Flow

## Overview

The test generation flow takes ingested `Question` records (extracted from uploaded documents) and assembles them into a structured `Test`. The schema must support:
1. Flexible question selection (by type, topic, difficulty)
2. Composite question grouping (parent + sub-questions)
3. Answer key storage per question type
4. Score calculation rules (Vietnamese exam scoring conventions)
5. Test-level metadata for reuse and versioning

---

## Proposed Entities

### `Test`

Represents a generated exam. Linked to one or more source `Document`s.

```python
class Test(BaseEntity):
    title = CharField(max_length=500)
    description = TextField(null=True)
    subject = CharField(max_length=255, null=True)        # e.g., "math"
    grade = SmallIntegerField(null=True)                  # e.g., 12
    duration_minutes = SmallIntegerField(null=True)       # e.g., 90
    total_score = FloatField(default=10.0)
    status = CharField(max_length=50, default="draft")    # draft | published | archived
    generation_config = BinaryJSONField(null=True)        # stores the RAG query params used
    metadata = BinaryJSONField(null=True)

    class Meta:
        table_name = "tests"
```

**`generation_config` example:**
```json
{
  "subject": "math",
  "topics": ["calculus", "logarithms"],
  "difficulty_distribution": {"easy": 0.3, "medium": 0.5, "hard": 0.2},
  "type_distribution": {"multiple_choice": 12, "true_false": 4, "short_answer": 6},
  "source_document_ids": ["uuid-1", "uuid-2"]
}
```

---

### `TestSection`

Groups questions within a test by type (mirrors Vietnamese exam structure: Phần I, II, III).

```python
class TestSection(BaseEntity):
    test = ForeignKeyField(Test, backref="sections")
    section_order = SmallIntegerField()                   # 1, 2, 3
    section_label = CharField(max_length=100)             # "PHẦN I", "PHẦN II"
    question_type = CharField(max_length=50)              # multiple_choice | true_false | short_answer
    instructions = TextField(null=True)                   # Displayed instructions for this section
    score_per_question = FloatField(default=0.25)         # Score per correctly answered item
    score_per_sub_question = FloatField(null=True)        # For composite/true_false partial scoring

    class Meta:
        table_name = "test_sections"
```

**Scoring note:** Vietnamese true/false sections use partial scoring:
- 1 correct sub-answer = 0.1 pts
- 2 correct = 0.25 pts
- 3 correct = 0.5 pts
- 4 correct = 1.0 pts

Store the full scoring table in `score_per_sub_question` or as a JSON array in `TestSection.metadata`.

---

### `TestQuestion`

Join table linking `Question` records into a `TestSection`, with ordering and point override.

```python
class TestQuestion(BaseEntity):
    section = ForeignKeyField(TestSection, backref="test_questions")
    question = ForeignKeyField(Question, backref="test_appearances")
    question_order = SmallIntegerField()                  # Display order within section
    display_label = CharField(max_length=50, null=True)  # "Câu 1.", "1.", etc.
    score_override = FloatField(null=True)                # Override section default score

    class Meta:
        table_name = "test_questions"
        indexes = (
            (("section", "question_order"), True),        # unique order within section
        )
```

**Why a separate join table instead of embedding test_id in `Question`:** A single `Question` can appear in multiple tests (question bank reuse). The join table preserves order and per-test overrides without polluting the canonical `Question` record.

---

### `TestAttempt` (for future student submission flow)

```python
class TestAttempt(BaseEntity):
    test = ForeignKeyField(Test, backref="attempts")
    student_id = CharField(max_length=255)                # external user id
    started_at = DateTimeField(null=True)
    submitted_at = DateTimeField(null=True)
    total_score = FloatField(null=True)
    answers = BinaryJSONField(null=True)                  # {test_question_id: answer_value}
    status = CharField(max_length=50, default="in_progress")  # in_progress | submitted | graded

    class Meta:
        table_name = "test_attempts"
```

---

## Entity Relationship

```
Document
  └── Page
        └── Question (with vector_embedding)
              └── TestQuestion ──► TestSection ──► Test
```

- `Question` is the canonical question bank — extracted once, reused across tests.
- `TestSection` defines structure and scoring rules.
- `TestQuestion` is the ordered, per-test selection.

---

## `Question` Schema Additions Needed

The current `Question` entity is missing a few fields needed for test generation:

| Field | Type | Reason |
|---|---|---|
| `parent_question_id` | `ForeignKeyField(Question, null=True)` | Link sub-questions extracted independently back to a composite parent |
| `source_section` | `CharField(null=True)` | "PHẦN I" / "PHẦN II" — preserves original exam section context for RAG filtering |
| `question_order` | `SmallIntegerField(null=True)` | Original order within the source page, helps deterministic test ordering |

> **Note:** `sub_questions` JSONB on the parent `Question` already stores inline sub-question data. The `parent_question_id` FK is only needed if sub-questions are also promoted to standalone `Question` rows for independent retrieval.

---

## Migration Plan

```sql
-- 1. tests table
CREATE TABLE tests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(500) NOT NULL,
    description TEXT,
    subject VARCHAR(255),
    grade SMALLINT,
    duration_minutes SMALLINT,
    total_score FLOAT DEFAULT 10.0,
    status VARCHAR(50) DEFAULT 'draft',
    generation_config JSONB,
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. test_sections table
CREATE TABLE test_sections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    test_id UUID REFERENCES tests(id) ON DELETE CASCADE,
    section_order SMALLINT NOT NULL,
    section_label VARCHAR(100),
    question_type VARCHAR(50) NOT NULL,
    instructions TEXT,
    score_per_question FLOAT DEFAULT 0.25,
    score_per_sub_question FLOAT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3. test_questions join table
CREATE TABLE test_questions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    section_id UUID REFERENCES test_sections(id) ON DELETE CASCADE,
    question_id UUID REFERENCES questions(id),
    question_order SMALLINT NOT NULL,
    display_label VARCHAR(50),
    score_override FLOAT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (section_id, question_order)
);

-- 4. Additions to questions table
ALTER TABLE questions ADD COLUMN IF NOT EXISTS source_section VARCHAR(100);
ALTER TABLE questions ADD COLUMN IF NOT EXISTS question_order SMALLINT;
ALTER TABLE questions ADD COLUMN IF NOT EXISTS parent_question_id UUID REFERENCES questions(id);
```

---

## Test Generation API Shape (recommended)

```
POST /tests/generate
{
  "document_ids": ["uuid-1"],
  "subject": "math",
  "topics": ["calculus", "logarithms"],
  "difficulty_distribution": { "easy": 0.4, "medium": 0.4, "hard": 0.2 },
  "sections": [
    { "question_type": "multiple_choice", "count": 12, "score_per_question": 0.25 },
    { "question_type": "true_false",      "count": 4,  "score_per_question": 1.0 },
    { "question_type": "short_answer",    "count": 6,  "score_per_question": 0.5 }
  ],
  "title": "Đề thi thử Toán - Học kỳ II",
  "duration_minutes": 90
}
```

Response: created `Test` with populated `TestSection` and `TestQuestion` rows, ready to render.
