# Exam Generation — Implementation Plan

Based on `exam-generation-flow.md`, existing entities, repos, and project patterns.

---

## 0. Gap Analysis (what's missing vs. what exists)

### Entity gaps (need migration m0005)

| Table | Missing column | Type | Notes |
|---|---|---|---|
| `exam_instances` | `is_base` | `BOOLEAN DEFAULT TRUE` | |
| `exam_instances` | `status` | `SMALLINT DEFAULT 0` | 0=pending, 1=accepted, 2=rejected |
| `question_exam_tests` | `answer_order` | `VARCHAR(1024) NULL` | JSON array of shuffled answer indices |

### Files that are empty / stub
- `src/dtos/exam/req.py`
- `src/dtos/exam/res.py`
- `src/routes/exam_route.py`

### Files to create from scratch
- `src/shared/constants/exam.py` — `ExamInstanceStatus` enum
- `src/calculations/exam_generation.py` — scoring + selection logic
- `src/repos/exam_template_repo.py`
- `src/repos/exam_instance_repo.py`
- `src/repos/exam_test_section_repo.py`
- `src/repos/question_exam_test_repo.py`
- `src/services/exam_generation_service.py`
- `src/lib/db/migrations/m0005_add_exam_generation_fields.py`

---

## 1. Migration m0005

**File**: `src/lib/db/migrations/m0005_add_exam_generation_fields.py`

```python
class Migration(BaseMigration):
    def up(self):
        db = self.db.get_db()
        db.execute_sql("""
            ALTER TABLE exam_instances
            ADD COLUMN IF NOT EXISTS is_base BOOLEAN NOT NULL DEFAULT TRUE
        """)
        db.execute_sql("""
            ALTER TABLE exam_instances
            ADD COLUMN IF NOT EXISTS status SMALLINT NOT NULL DEFAULT 0
        """)
        db.execute_sql("""
            ALTER TABLE question_exam_tests
            ADD COLUMN IF NOT EXISTS answer_order VARCHAR(1024) NULL
        """)
        # Index on status for efficient filtering
        db.execute_sql("""
            CREATE INDEX IF NOT EXISTS exam_instances_status_idx ON exam_instances(status)
        """)

    def down(self):
        db = self.db.get_db()
        db.execute_sql("DROP INDEX IF EXISTS exam_instances_status_idx")
        db.execute_sql("ALTER TABLE exam_instances DROP COLUMN IF EXISTS is_base")
        db.execute_sql("ALTER TABLE exam_instances DROP COLUMN IF EXISTS status")
        db.execute_sql("ALTER TABLE question_exam_tests DROP COLUMN IF EXISTS answer_order")
```

---

## 2. Update Entities

### `src/entities/exam_instance.py`

Add `is_base = BooleanField(default=True)` and `status = SmallIntegerField(default=0)`.

```python
from src.shared.constants.exam import ExamInstanceStatus

class ExamInstance(BaseEntity):
    exam_template = ForeignKeyField(ExamTemplate, backref="instances")
    parent_exam_instance = ForeignKeyField("self", null=True, backref="variants")
    exported_file_id = CharField(max_length=255, null=True)
    exam_test_code = CharField(max_length=255, unique=True)
    is_exported = BooleanField(default=False)
    is_base = BooleanField(default=True)          # ← ADD
    status = SmallIntegerField(default=ExamInstanceStatus.PENDING)  # ← ADD

    class Meta:
        table_name = "exam_instances"
```

### `src/entities/question_exam_test.py`

Add `answer_order = CharField(max_length=1024, null=True)` — stores a JSON-encoded list of answer indices for this version (e.g. `"[2, 0, 3, 1]"`).

```python
class QuestionExamTest(BaseEntity):
    question_group = ForeignKeyField(QuestionGroup, backref="exam_tests")
    question_id = CharField(max_length=255)
    exam_test_section = ForeignKeyField(ExamTestSection, backref="questions")
    order_count = IntegerField(default=0)
    answer_order = CharField(max_length=1024, null=True)  # ← ADD

    class Meta:
        table_name = "question_exam_tests"
```

---

## 3. Constants & Calculations

### `src/shared/constants/exam.py`

```python
from enum import IntEnum

class ExamInstanceStatus(IntEnum):
    PENDING = 0      # newly generated, awaiting review
    ACCEPTED = 1     # approved, can generate versions
    REJECTED = 2     # rejected, cannot generate versions
```

---

### `src/calculations/exam_generation.py`

Contains pure computation logic for group selection (no DB calls, no side effects).

```python
import numpy as np
from typing import List, Optional, Callable
from random import Random


def compute_score(
    group_embedding: Optional[List[float]],
    query_embedding: Optional[List[float]],
    existence_count: int,
    random_level_alpha: float,
) -> float:
    """Score a question group for selection.
    
    Args:
        group_embedding: 768-dim vector of the group
        query_embedding: 768-dim vector of the custom_text query
        existence_count: how many times this group was used before
        random_level_alpha: 0.1 (low) to 1.0 (high)
    
    Returns:
        float score in [0, 1]
    """
    # Semantic similarity (0-1, or 0 if no embeddings)
    sim = 0.0
    if group_embedding and query_embedding:
        sim = _cosine_similarity(group_embedding, query_embedding)
    
    # Inverse existence count (prefer fresh groups)
    exist_score = 1.0 / (existence_count + 1) ** random_level_alpha
    
    # Weighted combination
    return sim * 0.7 + exist_score * 0.3


def diversity_penalty(
    group_embedding: Optional[List[float]],
    selected_embeddings: List[Optional[List[float]]],
) -> float:
    """Penalty for selecting a group too similar to already-selected ones.
    
    Returns:
        max cosine similarity to any selected group (0 if none selected)
    """
    if not selected_embeddings or not group_embedding:
        return 0.0
    
    sims = []
    for sel_emb in selected_embeddings:
        if sel_emb:
            sims.append(_cosine_similarity(group_embedding, sel_emb))
    
    return max(sims) if sims else 0.0


def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Cosine similarity between two vectors."""
    q = np.array(vec1, dtype=float)
    g = np.array(vec2, dtype=float)
    nq, ng = np.linalg.norm(q), np.linalg.norm(g)
    if nq == 0 or ng == 0:
        return 0.0
    return float(np.dot(g, q) / (ng * nq))


def select_groups_greedy(
    candidates: List,          # List[QuestionGroup]
    top_k: int,
    random_level_alpha: float,
    embedding_getter: Callable,  # group -> List[float] | None
    score_fn: Callable = compute_score,
    diversity_weight: float = 0.3,
) -> List:
    """Greedy selection of top_k groups with diversity penalty.
    
    Args:
        candidates: list of QuestionGroup objects
        top_k: number of groups to select
        random_level_alpha: 0.1 to 1.0
        embedding_getter: callable(group) -> embedding or None
        score_fn: scoring function
        diversity_weight: how much to penalize similarity
    
    Returns:
        list of selected groups (size <= top_k)
    """
    selected = []
    selected_embeddings = []
    
    for _ in range(min(top_k, len(candidates))):
        best_group, best_score = None, float("-inf")
        
        for group in candidates:
            if group in selected:
                continue
            
            score = score_fn(
                embedding_getter(group),
                None,  # would be query_embedding if custom_text
                group.existence_count,
                random_level_alpha,
            )
            penalty = diversity_penalty(embedding_getter(group), selected_embeddings)
            final = score - penalty * diversity_weight
            
            if final > best_score:
                best_group, best_score = group, final
        
        if best_group is None:
            break
        
        selected.append(best_group)
        selected_embeddings.append(embedding_getter(best_group))
    
    return selected
```

---

## 4. Repositories

All follow `BaseRepo[T]` pattern. No ORM magic beyond what already exists.

### `src/repos/exam_template_repo.py`

```python
class ExamTemplateRepository(BaseRepo[ExamTemplate]):
    def get_by_name(self, name: str) -> Optional[ExamTemplate]: ...
    def get_by_subject(self, subject: str) -> List[ExamTemplate]: ...
```

### `src/repos/exam_instance_repo.py`

```python
class ExamInstanceRepository(BaseRepo[ExamInstance]):
    def get_by_template(self, template_id: UUID) -> List[ExamInstance]: ...
    def get_base_by_template(self, template_id: UUID) -> Optional[ExamInstance]:
        # filter is_base=True
    def get_versions_of(self, base_exam_id: UUID) -> List[ExamInstance]:
        # filter parent_exam_instance=base_exam_id, is_base=False
    def get_by_code(self, code: str) -> Optional[ExamInstance]: ...
```

### `src/repos/exam_test_section_repo.py`

```python
class ExamTestSectionRepository(BaseRepo[ExamTestSection]):
    def get_by_exam_instance(self, exam_instance_id: UUID) -> List[ExamTestSection]:
        # ordered by order_index
```

### `src/repos/question_exam_test_repo.py`

```python
class QuestionExamTestRepository(BaseRepo[QuestionExamTest]):
    def get_by_section(self, section_id: UUID) -> List[QuestionExamTest]:
        # ordered by order_count
    def get_by_exam_instance(self, exam_instance_id: UUID) -> List[QuestionExamTest]:
        # join through ExamTestSection
    def get_group_ids_for_exam(self, exam_instance_id: UUID) -> List[UUID]:
        # distinct question_group_ids used in this exam
    def bulk_create(self, rows: List[Dict]) -> None:
        # batch insert via QuestionExamTest.insert_many()
```

---

### `src/repos/exam_instance_repo.py` — status checking methods

```python
class ExamInstanceRepository(BaseRepo[ExamInstance]):
    # ... existing methods ...
    
    def get_accepted_base(self, template_id: UUID) -> Optional[ExamInstance]:
        """Get the accepted base exam for a template, if any."""
        return self.filter_one(
            exam_template=template_id,
            is_base=True,
            status=ExamInstanceStatus.ACCEPTED,
        )
    
    def update_status(self, exam_id: UUID, status: int) -> None:
        """Update exam instance status (0=pending, 1=accepted, 2=rejected)."""
        ExamInstance.update(status=status).where(
            ExamInstance.id == exam_id
        ).execute()
```

---

## 5. DTOs

## `src/dtos/exam/req.py`

```python
from pydantic import BaseModel
from typing import Optional, List
from uuid import UUID


class SectionConfig(BaseModel):
    name: str
    subject: str
    topic: str
    difficulty: str                            # "easy" | "medium" | "hard"
    question_type: Optional[str] = None        # filter by type; None = any
    top_k: int                                 # number of questions to pick
    random_level: str = "medium"               # "low" | "medium" | "high"
    custom_text: Optional[str] = None          # semantic hint for retrieval


class SaveExamTemplateRequest(BaseModel):
    """Create or update exam template (with optional generation config)."""
    name: str
    subject: str                               # must match Subject enum
    generation_config: Optional[List[SectionConfig]] = None  # default section configs


class GenerateBaseExamRequest(BaseModel):
    """Generate base exam from template or one-off sections.
    
    - If template_id is given → regenerate base (load template, merge sections)
    - If template_id is null → create one-off exam from sections only
    """
    template_id: Optional[UUID] = None         # None = create mode, not null = regenerate
    sections: List[SectionConfig]              # overrides template.generation_config if both given
    subject: Optional[str] = None              # required if template_id is null


class GenerateVersionsRequest(BaseModel):
    base_exam_id: UUID
    num_versions: int = 4                      # 1–10


class ReplaceQuestionRequest(BaseModel):
    exam_instance_id: UUID
    question_exam_test_id: UUID
    new_question_id: UUID                      # must be in same group
```

## `src/dtos/exam/res.py`

```python
from pydantic import BaseModel
from typing import Optional, List
from uuid import UUID
from datetime import datetime


class AnswerInExamResponse(BaseModel):
    id: UUID
    value: str
    is_correct: bool

    class Config:
        from_attributes = True


class QuestionInExamResponse(BaseModel):
    question_exam_test_id: UUID
    question_id: UUID
    question_group_id: UUID
    order_count: int
    answer_order: Optional[List[int]] = None   # shuffled index list

    question_text: str
    question_type: str
    difficulty: Optional[str] = None
    image_list: Optional[list] = None
    answers: List[AnswerInExamResponse]
    sub_questions: Optional[List["QuestionInExamResponse"]] = None

    class Config:
        from_attributes = True


class ExamSectionResponse(BaseModel):
    id: UUID
    name: str
    order_index: int
    questions: List[QuestionInExamResponse]

    class Config:
        from_attributes = True


class ExamInstanceResponse(BaseModel):
    id: UUID
    exam_test_code: str
    is_base: bool
    is_exported: bool
    template_id: UUID
    parent_exam_instance_id: Optional[UUID] = None
    sections: List[ExamSectionResponse]
    created_at: datetime

    class Config:
        from_attributes = True


class GenerateBaseExamResponse(BaseModel):
    exam_instance: ExamInstanceResponse
    total_questions: int


class GenerateVersionsResponse(BaseModel):
    versions: List[ExamInstanceResponse]
    total_versions: int


class ExamTemplateResponse(BaseModel):
    id: UUID
    name: str
    subject: str
    generation_config: Optional[List[SectionConfig]] = None  # parsed from JSON
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
```

---

## 5. Core Service — `src/services/exam_generation_service.py`

This is the main implementation. No pipelines needed — it's pure DB + algorithm logic.

### Constructor

```python
class ExamGenerationService:
    def __init__(self, llm_client=None):
        self._template_repo = ExamTemplateRepository()
        self._instance_repo = ExamInstanceRepository()
        self._section_repo = ExamTestSectionRepository()
        self._qet_repo = QuestionExamTestRepository()
        self._group_repo = QuestionGroupRepository()
        self._question_repo = QuestionRepository()
        self._answer_repo = AnswerRepository()
        self._llm_client = llm_client           # only needed when custom_text is used
```

---

### 5.0 `save_template(name, subject, generation_config) -> ExamTemplate`

Stores or updates an exam template with optional default section configurations.

```python
def save_template(
    self,
    name: str,
    subject: str,
    generation_config: Optional[List[SectionConfig]] = None,
    template_id: Optional[UUID] = None,
) -> ExamTemplate:
    """Create or update exam template.
    
    Args:
        name: template name
        subject: "math" | "science" | "history" | "literature"
        generation_config: list of default SectionConfig
        template_id: if given, update existing; else create new
    
    Returns:
        ExamTemplate with id
    """
    config_json = None
    if generation_config:
        config_json = json.dumps([s.dict() for s in generation_config])
    
    if template_id:
        template = self._template_repo.get_by_id(template_id)
        template.name = name
        template.subject = subject
        template.generation_config = config_json
        template.save()
        return template
    else:
        return self._template_repo.create(
            name=name,
            subject=subject,
            generation_config=config_json,
        )
```

---

### 5.1 `generate_base_exam(template_id, sections, subject) -> ExamInstance`

Handles both create mode (template_id=null) and regenerate mode (template_id given).

```python
def generate_base_exam(
    self,
    sections: List[SectionConfig],
    template_id: Optional[UUID] = None,
    subject: Optional[str] = None,
) -> ExamInstance:
    """Generate a base exam.
    
    Two modes:
      1. template_id given → regenerate (load template, merge sections override)
      2. template_id null → create one-off (use sections only, subject required)
    
    Returns:
        ExamInstance with is_base=True, fully populated with sections+questions
    """
    # Determine final sections list
    final_sections = sections
    
    if template_id:
        template = self._template_repo.get_by_id(template_id)
        if not template:
            raise ValueError(f"Template {template_id} not found")
        
        # If sections list provided, it overrides template config
        # If sections empty, use template.generation_config
        if not sections and template.generation_config:
            final_sections = json.loads(template.generation_config)
    else:
        # Create mode: subject is required
        if not subject:
            raise ValueError("subject required when template_id is null")
    
    # Validate all sections have required fields
    for sec in final_sections:
        if not all([sec.name, sec.subject, sec.topic, sec.difficulty, sec.top_k]):
            raise ValueError("Each section must have name, subject, topic, difficulty, top_k")
    
    # Step 1-5: Same as before — iterate sections, pick groups/variants, persist
    exam = self._create_exam_instance(
        template_id=template_id,
        sections=final_sections,
        is_base=True,
    )
    
    return exam


def _create_exam_instance(
    self,
    template_id: Optional[UUID],
    sections: List[SectionConfig],
    is_base: bool,
    parent_exam_id: Optional[UUID] = None,
) -> ExamInstance:
    """Internal: create exam instance with sections and questions.
    
    Used by both generate_base_exam and generate_versions.
    """
    code = self.generate_code()
    exam = self._instance_repo.create(
        exam_template_id=template_id,
        parent_exam_instance_id=parent_exam_id,
        exam_test_code=code,
        is_base=is_base,
    )
    
    # Create sections + questions
    all_group_ids = []
    all_question_ids = []
    
    for order_idx, section in enumerate(sections):
        sec_obj = self._section_repo.create(
            exam_instance_id=exam.id,
            name=section.name,
            order_index=order_idx,
        )
        
        candidates = self.retrieve_candidate_groups(section)
        selected = self.select_groups(candidates, section)
        
        for q_order, group in enumerate(selected):
            variant = self.pick_variant(group)
            if not variant:
                continue
            
            answer_order = self.shuffle_answers(variant)
            
            self._qet_repo.create(
                question_group_id=group.id,
                question_id=variant.id,
                exam_test_section_id=sec_obj.id,
                order_count=q_order,
                answer_order=json.dumps(answer_order),
            )
            
            all_group_ids.append(group.id)
            all_question_ids.append(variant.id)
    
    # Increment counts
    if all_group_ids:
        QuestionGroup.update(
            existence_count=QuestionGroup.existence_count + 1
        ).where(QuestionGroup.id.in_(all_group_ids)).execute()
    
    if all_question_ids:
        Question.update(
            variant_existence_count=Question.variant_existence_count + 1
        ).where(Question.id.in_(all_question_ids)).execute()
    
    return exam
```

---

### 5.2 `retrieve_candidate_groups(section) -> List[QuestionGroup]`

```python
def retrieve_candidate_groups(self, section: SectionConfig) -> List[QuestionGroup]:
    # Step 1: metadata filter
    candidates = self._group_repo.find_by_metadata(
        section.subject, section.topic, section.difficulty
    )
    # optionally filter by question_type: check if any question in group matches

    if not candidates:
        # Fallback: relax difficulty, try adjacent difficulties
        for fallback_difficulty in _difficulty_fallback(section.difficulty):
            candidates = self._group_repo.find_by_metadata(
                section.subject, section.topic, fallback_difficulty
            )
            if candidates:
                break

    # Step 2: if custom_text → vector-rank candidates
    if section.custom_text and self._llm_client and candidates:
        query_vec = self._llm_client.embed(section.custom_text)
        # use existing cosine_search, but with low threshold (0.0) just for ranking
        candidates = self._group_repo.cosine_search(candidates, query_vec, threshold=0.0)
        # returns sorted by similarity, no threshold cutoff needed here
    else:
        # random sample 5*top_k to avoid scanning all
        k = min(len(candidates), 5 * section.top_k)
        candidates = random.sample(candidates, k)

    return candidates
```

---

### 5.3 `select_groups(candidates, section) -> List[QuestionGroup]`

Greedy selection with score + diversity penalty (matches the flow doc exactly).

```python
def select_groups(
    self,
    candidates: List[QuestionGroup],
    section: SectionConfig,
    query_vec: Optional[List[float]] = None,
) -> List[QuestionGroup]:
    alpha = {"low": 0.1, "medium": 0.5, "high": 1.0}[section.random_level]
    selected: List[QuestionGroup] = []

    while len(selected) < section.top_k and candidates:
        best, best_score = None, float("-inf")

        for g in candidates:
            if g in selected:
                continue
            score = self._compute_score(g, query_vec, alpha)
            penalty = self._diversity_penalty(g, selected)
            final = score - penalty * 0.3

            if final > best_score:
                best, best_score = g, final

        if best is None:
            break
        selected.append(best)

    return selected


def _compute_score(self, group, query_vec, alpha) -> float:
    import numpy as np, json

    sim = 0.0
    if query_vec and group.vector_embedding:
        emb = group.vector_embedding
        if isinstance(emb, str):
            emb = json.loads(emb)
        q = np.array(query_vec, dtype=float)
        g = np.array(emb, dtype=float)
        nq, ng = np.linalg.norm(q), np.linalg.norm(g)
        if nq > 0 and ng > 0:
            sim = float(np.dot(g, q) / (ng * nq))

    exist_score = 1.0 / (group.existence_count + 1) ** alpha
    return sim * 0.7 + exist_score * 0.3


def _diversity_penalty(self, group, selected) -> float:
    if not selected:
        return 0.0
    # max cosine similarity to already-selected groups
    sims = []
    for s in selected:
        sims.append(self._cosine_between(group, s))
    return max(sims) if sims else 0.0
```

---

### 5.4 `pick_variant(group, rng=None) -> Question`

```python
def pick_variant(
    self, group: QuestionGroup, rng: Optional[Random] = None
) -> Optional[Question]:
    # Only top-level questions (no parent)
    variants = list(
        Question.select().where(
            (Question.questions_group == group.id)
            & (Question.parent_question.is_null())
        )
    )
    if not variants:
        return None

    weights = [1.0 / (v.variant_existence_count + 1) for v in variants]
    total = sum(weights)
    probs = [w / total for w in weights]

    _rng = rng or random
    return _rng.choices(variants, weights=probs, k=1)[0]
```

---

### 5.5 `shuffle_answers(question) -> List[int]`

Returns a permutation of answer indices (e.g. `[2, 0, 3, 1]`).  
Stored as JSON string in `QuestionExamTest.answer_order`.

```python
def shuffle_answers(self, question: Question, rng=None) -> List[int]:
    answers = self._answer_repo.get_by_question(question.id)
    indices = list(range(len(answers)))
    _rng = rng or random
    _rng.shuffle(indices)
    return indices
```

---

### 5.6 `generate_versions(base_exam_id, num_versions) -> List[ExamInstance]`

```python
def generate_versions(
    self, base_exam_id: UUID, num_versions: int
) -> List[ExamInstance]:
    """Generate version exams from an accepted base exam.
    
    Args:
        base_exam_id: the base exam instance (must be is_base=True, status=ACCEPTED)
        num_versions: how many versions to create (1-10)
    
    Raises:
        ValueError: if base is not found, not is_base=True, or status != ACCEPTED
    
    Returns:
        list of newly created ExamInstance objects (is_base=False)
    """
    from src.shared.constants.exam import ExamInstanceStatus
    
    base = self._instance_repo.get_by_id(base_exam_id)
    if not base:
        raise ValueError(f"Exam {base_exam_id} not found")
    if not base.is_base:
        raise ValueError(f"Exam {base_exam_id} is not a base exam")
    if base.status != ExamInstanceStatus.ACCEPTED:
        raise ValueError(f"Base exam must be ACCEPTED to generate versions (current status: {base.status})")
    
    # Load all sections from base
    base_sections = self._section_repo.get_by_exam_instance(base.id)
    
    versions = []
    for i in range(num_versions):
        seed = str(uuid4())
        version = self._create_version_from_base(base, base_sections, seed)
        versions.append(version)
    
    return versions


def _create_version_from_base(
    self,
    base_exam: ExamInstance,
    base_sections: List[ExamTestSection],
    seed: str,
) -> ExamInstance:
    """Create a single version from a base exam using seed-based RNG."""
    from random import Random
    
    version = self._instance_repo.create(
        exam_template_id=base_exam.exam_template_id,
        parent_exam_instance_id=base_exam.id,
        exam_test_code=self.generate_code(),
        is_base=False,
        status=ExamInstanceStatus.PENDING,
    )
    
    all_group_ids = []
    all_question_ids = []
    
    for section in base_sections:
        version_section = self._section_repo.create(
            exam_instance_id=version.id,
            name=section.name,
            order_index=section.order_index,
        )
        
        base_qets = self._qet_repo.get_by_section(section.id)
        
        for q_order, base_qet in enumerate(base_qets):
            group = base_qet.question_group
            
            # Seed RNG per group for reproducibility
            group_rng = Random(seed + str(group.id))
            variant = self.pick_variant(group, rng=group_rng)
            
            if not variant:
                continue
            
            # Seed RNG per variant for answer shuffling
            answer_rng = Random(seed + str(variant.id))
            answer_order = self.shuffle_answers(variant, rng=answer_rng)
            
            self._qet_repo.create(
                question_group_id=group.id,
                question_id=variant.id,
                exam_test_section_id=version_section.id,
                order_count=q_order,
                answer_order=json.dumps(answer_order),
            )
            
            all_group_ids.append(group.id)
            all_question_ids.append(variant.id)
    
    # Increment counts
    if all_group_ids:
        QuestionGroup.update(
            existence_count=QuestionGroup.existence_count + 1
        ).where(QuestionGroup.id.in_(all_group_ids)).execute()
    
    if all_question_ids:
        Question.update(
            variant_existence_count=Question.variant_existence_count + 1
        ).where(Question.id.in_(all_question_ids)).execute()
    
    return version
```

**Seed-based RNG**: each group/variant gets its own derived seed so results are reproducible:

```python
from random import Random
from uuid import uuid4

seed = str(uuid4())
group_rng = Random(seed + str(group.id))
variant = self.pick_variant(group, rng=group_rng)

answer_rng = Random(seed + str(variant.id))
answer_order = self.shuffle_answers(variant, rng=answer_rng)
```

---

### 5.7 `update_exam_status(exam_id, status) -> ExamInstance`

Update exam status (accept/reject after review).

```python
def update_exam_status(self, exam_id: UUID, status: int) -> ExamInstance:
    """Update exam instance status.
    
    Args:
        exam_id: exam instance id
        status: 0=pending, 1=accepted, 2=rejected
    
    Returns:
        updated ExamInstance
    """
    from src.shared.constants.exam import ExamInstanceStatus
    
    exam = self._instance_repo.get_by_id(exam_id)
    if not exam:
        raise ValueError(f"Exam {exam_id} not found")
    
    if status not in [ExamInstanceStatus.PENDING, ExamInstanceStatus.ACCEPTED, ExamInstanceStatus.REJECTED]:
        raise ValueError(f"Invalid status: {status}")
    
    self._instance_repo.update_status(exam_id, status)
    
    # Return updated object
    return self._instance_repo.get_by_id(exam_id)
```

---

### 5.8 `replace_question(exam_instance_id, qet_id, new_question_id) -> QuestionExamTest`

For user review step (allowed on any exam, not just pending).

```python
def replace_question(
    self,
    exam_instance_id: UUID,
    qet_id: UUID,
    new_question_id: UUID,
) -> QuestionExamTest:
    """Replace a question in an exam with another variant from same group.
    
    Args:
        exam_instance_id: exam to modify
        qet_id: QuestionExamTest row to replace
        new_question_id: new question (must be in same group)
    
    Returns:
        updated QuestionExamTest
    """
    # Load qet and verify it belongs to this exam
    qet = self._qet_repo.get_by_id(qet_id)
    if not qet:
        raise ValueError(f"QuestionExamTest {qet_id} not found")
    
    section = self._section_repo.get_by_id(qet.exam_test_section_id)
    if section.exam_instance_id != exam_instance_id:
        raise ValueError(f"QuestionExamTest does not belong to exam {exam_instance_id}")
    
    # Load new question, verify it's in same group
    new_question = self._question_repo.get_by_id(new_question_id)
    if not new_question or new_question.questions_group_id != qet.question_group_id:
        raise ValueError(f"Question {new_question_id} not in group {qet.question_group_id}")
    
    # Update and recompute answer order
    qet.question_id = new_question_id
    qet.answer_order = json.dumps(self.shuffle_answers(new_question))
    qet.save()
    
    return qet
```

---

### 5.9 Helper — `generate_code() -> str`

```python
import uuid, string, random as _random

def generate_code() -> str:
    return "EXAM-" + "".join(_random.choices(string.ascii_uppercase + string.digits, k=8))
```

---

## 6. Routes — `src/routes/exam_route.py`

Follow the pattern in `document_route.py` / `question_route.py`.

```
POST   /exam/templates                   → SaveExamTemplateRequest → ExamTemplateResponse
GET    /exam/templates                   → List[ExamTemplateResponse]
GET    /exam/templates/{id}              → ExamTemplateResponse

POST   /exam/generate-base               → GenerateBaseExamRequest → GenerateBaseExamResponse
POST   /exam/generate-versions           → GenerateVersionsRequest → GenerateVersionsResponse

GET    /exam/instances/{id}              → ExamInstanceResponse (with sections + questions)
GET    /exam/instances/{id}/versions     → List[ExamInstanceResponse]
PATCH  /exam/instances/{id}/status       → {status: 0|1|2} → ExamInstanceResponse

PATCH  /exam/instances/{id}/replace-question → ReplaceQuestionRequest → QuestionInExamResponse
```

### Template Create / Regenerate Flow

```
Create template:
  POST /exam/templates { name, subject, generation_config? } 
  → saves template, returns template_id

Use for generate-base (two modes):
  
  Mode 1 (Regenerate):
    POST /exam/generate-base { template_id, sections? }
    → loads template, merges sections override, generates exam
  
  Mode 2 (One-off, no template):
    POST /exam/generate-base { template_id: null, sections, subject }
    → creates exam directly from sections, no template saved
```

Each endpoint:
1. Validates input via Pydantic DTO
2. Calls `ExamGenerationService` method
3. Serializes result to response DTO
4. Returns `JSONResponse` (same pattern as existing routes)

---

## 7. ExamTemplate CRUD (simple)

`ExamTemplate.generation_config` stores section defaults as JSON:

```json
{
  "sections": [
    {
      "name": "Phần I — Trắc nghiệm",
      "subject": "math",
      "topic": "algebra",
      "difficulty": "easy",
      "question_type": "multiple_choice",
      "top_k": 10,
      "random_level": "medium"
    }
  ]
}
```

Service parses this with `json.loads(template.generation_config)` and merges with request-level overrides. Request `sections` always wins.

---

## 8. Build Order

Implement in this order so each step is testable:

1. **Migration m0005** — add `is_base`, `status`, `answer_order` columns + index on status
2. **Constants** — `src/shared/constants/exam.py` with `ExamInstanceStatus` enum
3. **Calculations** — `src/calculations/exam_generation.py` with `compute_score()`, `diversity_penalty()`, `select_groups_greedy()`
4. **Update entities** — `ExamInstance` (add `is_base`, `status`), `QuestionExamTest` (add `answer_order`)
5. **New repos** — `ExamTemplateRepo`, `ExamInstanceRepo` (with status methods), `ExamTestSectionRepo`, `QuestionExamTestRepo`
6. **DTOs** — `req.py`, `res.py` (include `SaveExamTemplateRequest`, `ExamTemplateResponse`, etc.)
7. **ExamGenerationService** — in this sub-order:
   - `generate_code()`
   - `retrieve_candidate_groups()` (no LLM path first)
   - `select_groups()` + scoring helpers (use calculations module)
   - `pick_variant()`
   - `shuffle_answers()`
   - `save_template()` — create/update template with generation_config
   - `_create_exam_instance()` — internal shared logic for base + versions
   - `generate_base_exam()` — handles template_id=null (create) vs template_id given (regenerate)
   - `generate_versions()` + `_create_version_from_base()` — seed-based variant selection (check status=ACCEPTED)
   - `update_exam_status()` — accept/reject after review
   - `replace_question()` — modify questions during review
8. **Routes** — `exam_route.py` with:
   - `POST /exam/templates` → save template
   - `GET /exam/templates` → list
   - `POST /exam/generate-base` → generate base exam
   - `POST /exam/generate-versions` → generate versions (only if base.status=ACCEPTED)
   - `PATCH /exam/instances/{id}/status` → update status
   - `PATCH /exam/instances/{id}/replace-question` → replace question during review

---

## 9. What NOT to build (out of scope)

- No new Kafka events or pipeline stages — exam generation is synchronous HTTP
- No pgvector index changes — existing cosine_search (NumPy, Python-side) is sufficient
- No Redis caching — can be added later if generation proves slow
- No grading/scoring (UserTestAttempt) — separate feature
