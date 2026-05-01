Dưới đây là **implementation plan hoàn chỉnh (production-ready, nhưng vẫn lean)** cho:

- Luồng **tạo đề thi (base exam)**
- Luồng **tạo nhiều mã đề (versions)**

Tôi viết theo dạng **có thể code trực tiếp** (service + SQL + thuật toán).

---

# I. KIẾN TRÚC TỔNG THỂ

```
exam_template (input config)
        ↓
Generate base exam (exam_instance.is_base = true)
        ↓
User review
        ↓
Generate versions (exam_instance.is_base = false)
```

---

# II. LUỒNG TẠO ĐỀ THI (BASE EXAM)

---

## 1. API

```
POST /exam/generate-base
```

### Input

```json
{
  "template_id": "uuid",
  "sections": [
    {
      "name": "Algebra",
      "topic": "algebra",
      "difficulty": "easy",
      "question_type": "multiple_choice",
      "top_k": 10,
      "random_level": "medium",
      "custom_text": "ưu tiên biến đổi biểu thức"
    }
  ]
}
```

---

## 2. Service Flow

---

## Step 1 — Load config

```python
template = get_template(template_id)
sections = input.sections or template.generation_config.sections
```

---

## Step 2 — Với mỗi section

```python
for section in sections:
    groups = retrieve_groups(section)
    selected_groups = select_groups(groups, section)
    questions = pick_variants(selected_groups)
```

---

# III. RETRIEVE GROUPS

---

## 3.1 Metadata filter

```sql
SELECT *
FROM question_groups
WHERE subject = :subject
AND topic = :topic
AND difficulty = :difficulty
LIMIT 500;
```

---

## 3.2 Nếu có custom_text → dùng embedding

```python
if section.custom_text:
    query_embedding = embed(section.custom_text)

    groups = vector_search(
        query_embedding,
        filters,
        limit = 5 * top_k
    )
```

---

## 3.3 Nếu không có custom_text

```python
groups = random_sample(filtered_groups, k=5 * top_k)
```

---

# IV. GROUP SCORING (CORE)

---

## 4.1 Compute score

```python
def compute_score(group, query_emb, random_level):
    sim = cosine(query_emb, group.embedding) if query_emb else 0

    alpha = map_random_level(random_level)

    exist_score = 1 / (group.existence_count + 1) ** alpha

    return sim * 0.7 + exist_score * 0.3
```

---

## 4.2 Diversity penalty

```python
def diversity_penalty(group, selected):
    return max(cosine(group.embedding, g.embedding) for g in selected)
```

---

## 4.3 Select groups

```python
def select_groups(groups, section):
    selected = []

    while len(selected) < section.top_k:
        best = None
        best_score = -inf

        for g in groups:
            if g in selected:
                continue

            score = compute_score(g)

            penalty = diversity_penalty(g, selected)
            final = score - penalty * 0.3

            if final > best_score:
                best = g
                best_score = final

        selected.append(best)

    return selected
```

---

# V. PICK VARIANTS

---

## 5.1 Query variants

```sql
SELECT *
FROM questions
WHERE question_group_id = :group_id
AND parent_question_id IS NULL;
```

---

## 5.2 Weighted random

```python
def pick_variant(variants):
    weights = [
        1 / (v.variant_existence_count + 1)
        for v in variants
    ]
    return random_weighted_choice(variants, weights)
```

---

## 5.3 Composite handling

```python
if question.is_composite:
    sub_questions = get_sub_questions(question.id)
```

---

# VI. PERSIST BASE EXAM

---

## 6.1 Create exam_instance

```sql
INSERT INTO exam_instances
(id, exam_template_id, is_base)
VALUES (:id, :template_id, true);
```

---

## 6.2 Insert sections

```sql
INSERT INTO exam_test_sections
(id, exam_instance_id, name, order_index)
```

---

## 6.3 Insert questions

```sql
INSERT INTO question_exam_tests
(
  question_group_id,
  question_id,
  exam_test_section_id,
  order_index,
  answer_order
)
```

---

## 6.4 Shuffle answer

```python
def shuffle_answers(question):
    order = list(range(len(question.answers)))
    random.shuffle(order)
    return order
```

---

# VII. USER REVIEW

---

Cho phép:

- replace variant (same group)
- add/remove group

---

👉 Khi replace:

```sql
UPDATE question_exam_tests
SET question_id = :new_variant
WHERE id = :id;
```

---

# VIII. LUỒNG TẠO NHIỀU MÃ ĐỀ

---

## 8.1 API

```
POST /exam/generate-versions
```

### Input

```json
{
  "base_exam_id": "uuid",
  "num_versions": 4
}
```

---

## 8.2 Load base exam

```python
base = get_exam(base_exam_id)
groups = get_all_groups(base)
```

---

## 8.3 Generate versions

---

## Step 1 — Loop

```python
for i in range(num_versions):
    version = create_exam_instance(parent=base_id)
```

---

## Step 2 — Với mỗi group

```python
for group in groups:
    variants = get_variants(group.id)

    variant = pick_variant_seeded(variants, seed, group.id)

    answer_order = shuffle_answers_seeded(variant, seed)
```

---

## 8.4 Seed-based variant selection

```python
def pick_variant_seeded(variants, seed, group_id):
    rng = Random(hash(seed + group_id))

    weights = [
        1 / (v.variant_existence_count + 1)
        for v in variants
    ]

    return weighted_choice(variants, weights, rng)
```

---

## 8.5 Shuffle question order

```python
def shuffle_questions(questions, seed):
    rng = Random(seed)
    rng.shuffle(questions)
```

---

## 8.6 Persist version

```sql
INSERT INTO exam_instances
(
  id,
  parent_exam_instance_id,
  is_base
)
VALUES (:id, :base_id, false);
```

---

## Insert questions giống base nhưng khác:

- `question_id`
- `answer_order`
- `order_index` (có thể shuffle)

---

# IX. UPDATE EXISTENCE COUNT

---

## Sau khi tạo exam (base + versions)

```sql
UPDATE question_groups
SET existence_count = existence_count + 1
WHERE id IN (...)
```

---

## Variant

```sql
UPDATE questions
SET variant_existence_count = variant_existence_count + 1
WHERE id IN (...)
```

---

# X. EDGE CASES

---

## 1. Không đủ group

```python
if len(groups) < top_k:
    fallback:
        - relax difficulty
        - hoặc lấy thêm topic gần
```

---

## 2. Group chỉ có 1 variant

→ vẫn OK, nhưng version sẽ giống nhau

---

## 3. Duplicate variant trong cùng batch

```python
avoid picking same variant if possible
```

---

# XI. PERFORMANCE

---

## Nên có

- index:
  - `(subject, topic, difficulty)`
  - vector index (pgvector HNSW)
- cache:
  - group embedding (Redis)

---

## Batch optimize

- load variants theo group batch
- tránh N+1 query

---

# XII. TL;DR

---

## Base exam

```
filter group → score → pick group → pick variant → save
```

---

## Versions

```
copy group → pick variant (seed) → shuffle → save
```

---

## Nguyên tắc

```
group = cố định
variant = random
```

---
