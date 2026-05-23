# Questions Extraction Flow

End-to-end walkthrough of how a PDF document goes from upload to persisted questions.

---

## Overview

```
POST /ai/queue
  │
  ▼ Kafka: document_extraction_requested
DocumentExtractionWorker
  │  (per page) Kafka: question_extraction_requested
  ▼
QuestionExtractionWorker
  │
  ▼ DB: Question + Answer + QuestionGroup + Subject + Topic records
```

Three top-level stages:

1. **Enqueue** — API receives document IDs and publishes a Kafka event
2. **Document Extraction** — Worker downloads PDF, OCRs each page, runs LLM validation, persists Page records, publishes per-page events
3. **Question Extraction** — Worker receives per-page events, runs LLM extraction → embedding → grouping → DB persistence

---

## Stage 0 — Enqueue Document

**Entry point:** `POST /ai/queue` → [`src/routes/ai_route.py:41`](../src/routes/ai_route.py#L41)

### Request

```json
{
  "document_ids": ["a1b2c3d4-0000-0000-0000-000000000001"]
}
```

### What happens per `doc_id`

1. Load `Document` record from DB — must exist with status `PENDING` or `COMPLETED`
2. Authorization check: admin can queue any document; regular users only their own
3. Send Kafka message via `kafka_producer.send()`, then `kafka_producer.flush()`

### Kafka message produced

```json
// Topic: "document_extraction_requested"
{
  "event_type": "document_extraction_requested",
  "document_id": "a1b2c3d4-0000-0000-0000-000000000001"
}
```

---

## Stage 1 — Document Extraction

### Worker bootstrap

**File:** [`src/workers/document_extraction_worker.py`](../src/workers/document_extraction_worker.py)

- Registers OCR client, LLM client, S3 client, Kafka producer into DI container
- Registers Kafka producer on topic `"question_extraction_requested"` (the outbound topic for this worker)
- Starts `KafkaConsumerImpl` on topic `"document_extraction_requested"`
- Routes events to `DocumentExtractionHandler` via `EventDispatcher`

### Handler: `DocumentExtractionHandler.handle()`

**File:** [`src/handlers/document_extraction_handler.py:60`](../src/handlers/document_extraction_handler.py#L60)

```
Event received
  ├─ Parse document_id from payload
  ├─ Load Document record → get file_id
  ├─ Load FileMetadata by file_id → get object_key (S3 path)
  ├─ Download PDF: S3 object_key → /tmp/doc_<uuid>_xxx/document.pdf
  ├─ Mark Document status = PROCESSING
  └─ Call DocumentExtractionService.extract_document(on_page_ready=callback)
```

After all pages are processed, `kafka_producer.flush()` ensures all
`question_extraction_requested` messages are delivered.

### Service: `DocumentExtractionService.extract_document()`

**File:** [`src/services/core/document_extraction_service.py:85`](../src/services/core/document_extraction_service.py#L85)

**Setup:**

- Opens PDF with PyMuPDF (`fitz`) to count `total_pages`
- Creates a `Task` record:

```
name  = "extract_<filename>"
type  = "document_extraction"
entity_id   = <document_uuid>
entity_type = "document"
status      = PROCESSING
total_pages = N
processed_pages = 0
```

**Per-page loop** — for each `page_index` in `0..N-1`:

---

#### Step 1 — Render page to image

**File:** [`src/services/core/document_extraction_service.py:287`](../src/services/core/document_extraction_service.py#L287)

```python
matrix = fitz.Matrix(2.0, 2.0)  # 2× scale for OCR quality
pix = page.get_pixmap(matrix=matrix, alpha=False)
# Saved as: /tmp/.../pages/page_1.png
```

Image is uploaded to S3:
```
s3://bucket/document-extraction/<file_id>/pages/page_1.png
```

A `FileMetadata` record is created and the returned `fm_id` is stored as `page_image_fm_id`.

---

#### Step 2 — ContentExtractionPipeline (OCR)

**File:** [`src/pipelines/content_extraction.py:65`](../src/pipelines/content_extraction.py#L65)

Calls `ocr_client.extract(OCRImageRequest(image_path=...))`.

**Raw OCR output structure** (after normalization in `_extract_page_with_ocr`):

```python
[
  {
    "page_number": 1,
    "bbox": {"x1": 50, "y1": 80, "x2": 750, "y2": 110},
    "content": "ĐỀ KIỂM TRA HỌC KỲ 1 - MÔN TOÁN 12",
    "content_type": "text",
    "accuracy": 0.98
  },
  {
    "page_number": 1,
    "bbox": {"x1": 50, "y1": 200, "x2": 750, "y2": 240},
    "content": "Câu 1. Tính giá trị của $P = \\sqrt{a^2 + b^2}$ tại $a=3, b=4$.",
    "content_type": "text",
    "accuracy": 0.95
  },
  {
    "page_number": 1,
    "bbox": {"x1": 100, "y1": 300, "x2": 600, "y2": 500},
    "content": "[figure description]",
    "content_type": "image",
    "accuracy": 0.80
  }
]
```

**Image block handling:**

For each block with `content_type == "image"`:
- Crop the region from the page PNG using `bbox`
- Save to `/tmp/.../crops/crop_p1_1.png`
- Upload to S3: `document-extraction/<file_id>/crops/crop_p1_1.png`
- Register `FileMetadata` → attach `illustration_file_id` to the block

**`_generate_page_markdown()` rendering rules:**

| `content_type`                        | Output                            |
|---------------------------------------|-----------------------------------|
| `text`, `table`, `formula`            | append `content` as-is            |
| `image`, `figure`, `chart`, `graphic` | `<dh-image>{file_id}</dh-image>`  |
| `seal`                                | skip                              |

**Example assembled markdown:**

```markdown
ĐỀ KIỂM TRA HỌC KỲ 1 - MÔN TOÁN 12
Câu 1. Tính giá trị của $P = \sqrt{a^2 + b^2}$ tại $a=3, b=4$.
<dh-image>fm-uuid-0001</dh-image>
A. 5    B. 7    C. 25    D. 12
```

**Pipeline output:**

```python
{
  "page_number": 1,
  "markdown_content": "ĐỀ KIỂM TRA...\nCâu 1. ...\n<dh-image>...",
  "image_file_ids": {
    "document-extraction/<file_id>/crops/crop_p1_1.png": "fm-uuid-0001"
  }
}
```

---

#### Step 3 — ContentValidationPipeline (LLM multimodal correction)

**File:** [`src/pipelines/content_validation.py:57`](../src/pipelines/content_validation.py#L57)  
**Prompt:** [`src/prompts/content_validation_prompt.py`](../src/prompts/content_validation_prompt.py)

Sends the **page image + OCR markdown** to the LLM (multimodal).

**Prompt template:**

```
You are validating OCR markdown for a single exam page.
Input markdown may contain OCR noise, broken formulas, wrong line breaks...
Use the provided image as the source of truth and normalize the markdown.

Rules:
1. Keep the same language as the input.
2. Preserve all information from the image, but fix OCR mistakes.
3. Keep math/science expressions in LaTeX ($...$ or $$...$$).
4. For tables, convert to latex tabular format if it improves readability.
5. Keep image references (e.g., <dh-image>...</dh-image>) if present.
6. Output only clean markdown, no JSON, no explanations.

[RAW TEXT START]
{markdown_content}
[RAW TEXT END]
```

LLM responds with corrected markdown. `_extract_markdown()` strips any accidental
` ```markdown ``` ` fences if the model adds them. On LLM failure, falls back to
raw OCR markdown unchanged.

**Pipeline output:**

```python
{
  "page_number": 1,
  "content": "ĐỀ KIỂM TRA HỌC KỲ 1 - MÔN TOÁN 12\nCâu 1. Tính giá trị của $P = \\sqrt{a^2+b^2}$ tại $a=3, b=4$.\n..."
}
```

---

#### Step 4 — PageHeadOverlapPipeline

**File:** [`src/pipelines/page_head_overlap.py:84`](../src/pipelines/page_head_overlap.py#L84)

Handles questions that span a page boundary by prepending the tail of the
previous page's content to the current page record.

- **Page 1:** no overlap — `overlap_content = None`
- **Page N (N > 1):** takes the last 500 chars of `previous_page_content`
  (the `validated_content` from the previous iteration)

```python
# Example — page 2, previous page ended mid-question:
overlap_content = {
  "previous_page": 1,
  "content": "...Câu 5. Cho hàm số $f(x) = 2\\cos x + x$."
}
```

**Pipeline output:**

```python
{
  "page_number": 2,
  "markdown_content": "<validated content of page 2, unchanged>",
  "overlap_content": {
    "previous_page": 1,
    "content": "...last 500 chars of page 1 validated content..."
  }
}
```

---

#### Step 5 — Persist Page record

```python
page_orm = page_repo.create(
    document=document,
    page_number=1,
    content=overlap["markdown_content"],        # full page content (used for question extraction)
    validated_content=validated["content"],     # LLM-corrected markdown
    overlap_content="...last 500 chars of page N-1...",
    page_image_id="fm-uuid-page-img",
)
```

`content` is what Pipeline 1 (question extraction) will read.
`validated_content` is what PageHeadOverlap reads as `previous_page_content` for the next iteration.

---

#### Step 6 — `on_page_ready` callback → Kafka event

**File:** [`src/handlers/document_extraction_handler.py:113`](../src/handlers/document_extraction_handler.py#L113)

After each page is saved:

```json
// Topic: "question_extraction_requested"
{
  "event_type": "question_extraction_requested",
  "page_id": "page-uuid-0001",
  "task_id": "task-uuid-0001",
  "is_final_page": false,
  "uploaded_by_id": "user-uuid-0001"
}
```

`is_final_page` is `true` only for the last page (`page_index == total - 1`).

---

## Stage 2 — Question Extraction

### Worker bootstrap

**File:** [`src/workers/questions_extraction_worker.py`](../src/workers/questions_extraction_worker.py)

- Registers LLM client into DI (no OCR, no Kafka producer — this worker only consumes)
- Starts `KafkaConsumerImpl` on topic `"question_extraction_requested"`
- Routes to `QuestionExtractionHandler`

### Handler: `QuestionExtractionHandler.handle()`

**File:** [`src/handlers/question_extraction_handler.py:47`](../src/handlers/question_extraction_handler.py#L47)

```
Event received
  ├─ Parse page_id, task_id, is_final_page, uploaded_by_id
  └─ Call QuestionExtractionService.process_page(...)
       On is_final_page=true after success:
         doc_repo.update(COMPLETED, progress=1.0)
         task_repo.update_status(COMPLETED)
```

On any exception: `task_repo.update_status(FAILED)`.

### Service: `QuestionExtractionService.process_page()`

**File:** [`src/services/core/question_extraction_service.py:52`](../src/services/core/question_extraction_service.py#L52)

Loads the `Page` record. If `page.content` is empty → increments task progress, returns early.

Reconstructs `overlap_content` from `page.overlap_content`:

```python
overlap_content = {
  "previous_page": page.page_number - 1,
  "content": page.overlap_content   # the 500-char tail stored during extraction
}
```

Then runs 5 pipelines in sequence.

---

#### Pipeline 1 — QuestionExtractionPipeline (LLM)

**File:** [`src/pipelines/question_extraction.py`](../src/pipelines/question_extraction.py)  
**Prompt:** [`src/prompts/question_extraction_prompt.py`](../src/prompts/question_extraction_prompt.py)

**Input payload:**

```python
{
  "page_number": 2,
  "markdown_content": "<full page content>",
  "overlap_content": {
    "previous_page": 1,
    "content": "...Câu 5. Cho hàm số $f(x) = 2\\cos x + x$."
  }
}
```

**Prompt structure (abbreviated):**

```
You are extracting questions from a single exam page.
Use BOTH inputs as context:
1) The page image (source of truth).
2) The overlap content (tail of the previous page) to resolve cross-page questions.
3) The page markdown (already OCR + normalized).

OUTPUT FORMAT EXAMPLE: { "questions": [ ... ] }

STRICT RULES:
- Return ONLY valid JSON, no markdown fences
- Extract EVERY question, do not skip sections
- Use LaTeX for all math
- question_type: one of [multiple_choice, true_false, short_answer, essay, selection, composite]
- difficulty: one of [easy, medium, hard]
- answers: [{value, is_correct}] — strip option letters (A., B., etc.), mark exactly ONE correct
- composite: answers must be null, put answers in sub_questions
- If overlap_content is provided, use it for context only, do NOT re-extract questions from it

[START OVERLAP CONTENT]
...Câu 5. Cho hàm số $f(x) = 2\cos x + x$.
[END OVERLAP CONTENT]
[START PAGE MARKDOWN]
a) $f(0)=2$; $f(\pi/2)=\pi/2$ đúng hay sai?
b) Tính $f'(x)$ và xác định cực trị.
Câu 6. Tính $P = \sqrt{a^2+b^2}$ tại $a=3, b=4$.
A. 5  B. 7  C. 25  D. 12
[END PAGE MARKDOWN]
```

**LLM JSON response:**

```json
{
  "questions": [
    {
      "question_text": "Cho hàm số $f(x) = 2\\cos x + x$.",
      "question_type": "composite",
      "difficulty": "medium",
      "subject": "math",
      "subject_vi": "Toán",
      "topic": "calculus",
      "topic_vi": "Giải tích",
      "answers": null,
      "image_list": [],
      "sub_questions": [
        {
          "order": 1,
          "sub_question_text": "$f(0)=2$; $f(\\pi/2)=\\pi/2$",
          "question_type": "true_false",
          "answers": [
            {"value": "True",  "is_correct": true},
            {"value": "False", "is_correct": false}
          ],
          "image_list": []
        },
        {
          "order": 2,
          "sub_question_text": "Tính $f'(x)$ và xác định các điểm cực trị.",
          "question_type": "short_answer",
          "answers": [
            {"value": "$f'(x) = -2\\sin x + 1$; cực trị tại ...", "is_correct": true}
          ],
          "image_list": []
        }
      ]
    },
    {
      "question_text": "Tính giá trị của biểu thức $P = \\sqrt{a^2+b^2}$ tại $a=3, b=4$.",
      "question_type": "multiple_choice",
      "difficulty": "easy",
      "subject": "math",
      "subject_vi": "Toán",
      "topic": "algebra",
      "topic_vi": "Đại số",
      "answers": [
        {"value": "5",  "is_correct": true},
        {"value": "7",  "is_correct": false},
        {"value": "25", "is_correct": false},
        {"value": "12", "is_correct": false}
      ],
      "image_list": [],
      "sub_questions": []
    }
  ]
}
```

**Pipeline output:** `{"questions": [<list above>]}`

---

#### Pipeline 2 — AnswerParsingPipeline

Pass-through for format compatibility. The LLM already returns structured
`[{value, is_correct}]` answers — no transformation needed.

**Output:** `{"questions": <same list>}`

---

#### Pipeline 3 — QuestionEmbeddingPipeline

**File:** [`src/pipelines/question_embedding.py:53`](../src/pipelines/question_embedding.py#L53)

For each question, builds an embedding input string:

```python
# _build_embedding_input():
# "<question_text> <answer1_value>, <answer2_value>, ..."
"Tính giá trị của biểu thức $P = \\sqrt{a^2+b^2}$ tại $a=3, b=4$. 5, 7, 25, 12"
```

Sub-questions are **not** embedded (only the main question carries the vector).

Sends all texts in batches of 20 to `llm_client.embed()`. Result is a list of
768-dim float vectors. Each question gets a `"vector"` key added:

```python
{
  "question_text": "Tính giá trị ...",
  ...,
  "vector": [0.023, -0.142, 0.087, ..., 0.031]   # 768 floats
}
```

Composite questions get a vector computed from their stem text + (no answers, since `answers=null`).

**Output:** `{"questions": [<questions with "vector" key>]}`

---

#### Pipeline 4 — QuestionGroupingPipeline

**File:** [`src/pipelines/question_grouping.py:62`](../src/pipelines/question_grouping.py#L62)

For each question, finds or creates a `QuestionGroup` using a two-step approach.

Questions without `subject`, `topic`, or `difficulty` get `group_id = None`.

**Step 1 — Taxonomy filter (DB query):**

```python
candidates = repo.find_by_metadata(
    subject="math",
    topic="algebra",
    difficulty="easy",
    from_user_id=uploaded_by_id   # groups are scoped per uploader
)
# Returns: List[QuestionGroup] — all groups matching this taxonomy for this user
```

**Step 2 — Cosine similarity search (in-process NumPy):**

```python
matches = repo.cosine_search(candidates, vector, threshold=0.75)
# For each candidate group:
#   sim = dot(g_vec, q_vec) / (||g_vec|| * ||q_vec||)
# Returns matches with sim >= 0.75, sorted descending by similarity
```

**Decision:**

- Match found → reuse `matches[0]` (highest similarity group)
- No match → create new `QuestionGroup`:

```python
new_group = repo.create_with_vector(
    subject="math",
    topic="algebra",
    difficulty="easy",
    vector=[0.023, -0.142, ...],
    from_user_id=uploaded_by_id
)
```

Each question dict gets `"group_id"` attached:

```python
{
  "question_text": "Tính giá trị ...",
  "subject": "math",
  "topic": "algebra",
  "difficulty": "easy",
  "vector": [...],
  "group_id": "group-uuid-0042",
  "answers": [...],
  ...
}
```

**Output:** `{"grouped_questions": [<questions with "group_id" key>]}`

---

#### Pipeline 5 — QuestionPersistencePipeline

**File:** [`src/pipelines/question_persistence.py:86`](../src/pipelines/question_persistence.py#L86)

For each question in `grouped_questions`:

**1. Ensure Subject record exists:**

```python
subject_repo.get_or_create(
    code="math",
    name="Math",          # auto-derived: code.replace("_", " ").title()
    name_vi="Toán"        # from subject_vi returned by LLM
)
```

**2. Ensure Topic record exists:**

```python
topic_repo.get_or_create(
    code="algebra",
    name="Algebra",
    name_vi="Đại số",
    subject_code="math"   # links topic → parent subject
)
```

**3. Create main Question record:**

```python
Question.create(
    page=page_id,
    parent_question=None,
    questions_group="group-uuid-0042",
    question_text="Tính giá trị của biểu thức $P = \\sqrt{a^2+b^2}$ tại $a=3, b=4$.",
    question_type="multiple_choice",
    difficulty="easy",
    subject="math",       # stored as code string
    topic="algebra",      # stored as code string
    image_list=[],
    vector_embedding=[0.023, -0.142, ...],
    variant_existence_count=1,
    status=0,
)
```

**4. Create Answer records (batch):**

```python
answer_repo.create_batch(main_q.id, [
    {"value": "5",  "is_correct": True},
    {"value": "7",  "is_correct": False},
    {"value": "25", "is_correct": False},
    {"value": "12", "is_correct": False},
])
```

**5. For composite questions — create sub-questions:**

```python
# Parent question (composite, answers=null) created first (step 3 above)

# Sub-question 1
Question.create(
    parent_question=main_q.id,
    questions_group="group-uuid-0042",  # inherits group from parent
    question_text="$f(0)=2$; $f(\\pi/2)=\\pi/2$",
    question_type="true_false",
    difficulty=None,        # sub-questions don't carry taxonomy
    subject=None,
    topic=None,
    sub_question_order=1,   # from LLM "order" field
    vector_embedding=None,
    variant_existence_count=1,
    status=0,
)
# Answer rows: True (is_correct=True), False (is_correct=False)

# Sub-question 2
Question.create(
    parent_question=main_q.id,
    ...
    question_text="Tính $f'(x)$ và xác định các điểm cực trị.",
    question_type="short_answer",
    sub_question_order=2,
    ...
)
# Answer row: {value: "...", is_correct: True}
```

**6. Update Task progress:**

```python
task.processed_pages += 1
task.progress = processed_pages / total_pages   # e.g. 3/5 = 0.6

# If is_final_page:
task.status = COMPLETED
task.progress = 1.0
```

Back in the handler, when `is_final_page=true`:

```python
doc_repo.update(document_id, status=COMPLETED, progress=1.0)
task_repo.update_status(task_id, COMPLETED)
```

---

## Complete Data Flow

```
POST /ai/queue  {"document_ids": ["abc"]}
  │
  ├─ Validate doc exists, status PENDING|COMPLETED, user authorized
  └─ kafka.send("document_extraction_requested")
       {"event_type": "document_extraction_requested", "document_id": "abc"}
                                │
                    ┌───────────▼────────────────────────────────────────┐
                    │  DocumentExtractionWorker                          │
                    │                                                    │
                    │  1. Download PDF from S3 → /tmp/doc_abc/doc.pdf   │
                    │  2. fitz.open() → total_pages = N                 │
                    │  3. Create Task(status=PROCESSING, total=N)       │
                    │                                                    │
                    │  FOR EACH page_index in 0..N-1:                   │
                    │    a. Render PNG @ 2× → upload S3                 │
                    │    b. ContentExtractionPipeline (OCR)             │
                    │       → list of {bbox, content, content_type}     │
                    │       → crop image blocks → upload S3             │
                    │       → assemble markdown (text + <dh-image>)     │
                    │    c. ContentValidationPipeline (LLM)             │
                    │       → fix OCR noise, normalize LaTeX/tables     │
                    │    d. PageHeadOverlapPipeline                     │
                    │       → last 500 chars of prev page as context    │
                    │    e. page_repo.create(content, validated, overlap)│
                    │    f. on_page_ready callback:                     │
                    │       kafka.send("question_extraction_requested") │
                    └───────────────────────────────────────────────────┘
                                │ (one event per page)
       {"event_type": "question_extraction_requested",
        "page_id": "page-uuid",
        "task_id": "task-uuid",
        "is_final_page": true|false,
        "uploaded_by_id": "user-uuid"}
                                │
                    ┌───────────▼────────────────────────────────────────┐
                    │  QuestionExtractionWorker  (per page, parallel)    │
                    │                                                    │
                    │  Load Page record → page.content                  │
                    │                                                    │
                    │  Pipeline 1: QuestionExtractionPipeline (LLM)     │
                    │    Input:  overlap_content + markdown_content      │
                    │    Output: [{question_text, question_type,         │
                    │              difficulty, subject, topic,           │
                    │              subject_vi, topic_vi,                 │
                    │              answers, sub_questions, image_list}]  │
                    │                                                    │
                    │  Pipeline 2: AnswerParsingPipeline (pass-through) │
                    │                                                    │
                    │  Pipeline 3: QuestionEmbeddingPipeline            │
                    │    Input:  "question_text answer1, answer2, ..."   │
                    │    Output: vector[768] per question               │
                    │                                                    │
                    │  Pipeline 4: QuestionGroupingPipeline             │
                    │    Step 1: find_by_metadata(subj, topic, diff,    │
                    │                             user_id)              │
                    │    Step 2: cosine_search(candidates, vec, ≥0.75)  │
                    │    → reuse group OR create new QuestionGroup      │
                    │                                                    │
                    │  Pipeline 5: QuestionPersistencePipeline          │
                    │    get_or_create Subject, Topic records            │
                    │    Question.create(main + vector + group_id)      │
                    │    answer_repo.create_batch(answers)              │
                    │    IF composite: Question.create(sub_questions)   │
                    │    task.processed_pages += 1                      │
                    │    IF is_final_page:                              │
                    │      Document → COMPLETED                         │
                    │      Task → COMPLETED                             │
                    └────────────────────────────────────────────────────┘
```

---

## Key Data Structures

### Page record (after Stage 1)

| Column              | Source                                    |
|---------------------|-------------------------------------------|
| `content`           | `overlap["markdown_content"]` — full page markdown used for question extraction |
| `validated_content` | `validated["content"]` — LLM-corrected markdown, used as `previous_page_content` for the next page's overlap |
| `overlap_content`   | `overlap["overlap_content"]["content"]` — last 500 chars of previous page, stored for Stage 2 to read |
| `page_image_id`     | `FileMetadata.id` of the page PNG         |

### Kafka events

| Event                           | Topic                           | Key fields                                                   |
|---------------------------------|---------------------------------|--------------------------------------------------------------|
| `document_extraction_requested` | `document_extraction_requested` | `document_id`                                                |
| `question_extraction_requested` | `question_extraction_requested` | `page_id`, `task_id`, `is_final_page`, `uploaded_by_id`      |

### QuestionGroup record

| Column              | Description                                          |
|---------------------|------------------------------------------------------|
| `subject`           | Subject code string (e.g., `"math"`)                 |
| `topic`             | Topic code string (e.g., `"algebra"`)                |
| `difficulty`        | `"easy"` / `"medium"` / `"hard"`                     |
| `vector_embedding`  | 768-dim float vector of the first question in group  |
| `existence_count`   | Reserved for exam generation (not incremented here)  |
| `from_user_id`      | Scopes the group to the uploading user               |

### Question record

| Column                  | Description                                         |
|-------------------------|-----------------------------------------------------|
| `parent_question`       | `null` for main questions; parent UUID for sub-questions |
| `questions_group`       | FK to `QuestionGroup`                               |
| `subject` / `topic`     | Code strings (`null` for sub-questions)             |
| `difficulty`            | `null` for sub-questions                            |
| `vector_embedding`      | 768-dim vector (`null` for sub-questions)           |
| `sub_question_order`    | 1-indexed order within composite parent             |
| `variant_existence_count` | Initialized to 1                                  |

### Answer record

| Column      | Description                                |
|-------------|--------------------------------------------|
| `question`  | FK to parent Question                      |
| `value`     | Answer text (LaTeX OK, option letters stripped) |
| `is_correct`| `true` for exactly one answer per non-composite question |
