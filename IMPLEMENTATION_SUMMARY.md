# ETL Flow Refactor — Implementation Summary

Date: 2026-04-26  
Status: ✅ Complete  
Based on: `docs/manual/document-etl-flow-vi.md`

---

## Architecture Overview

### 2 Core Services (Worker Pattern)
1. **DocumentExtractionService** — OCR + Validation Worker
   - File: `src/services/core/document_extraction_service.py`
   - Renders PDF pages → OCR → validates via LLM → saves Page records
   - Callback-based: calls `on_page_ready(page, task)` for each page
   - Triggers event chain for next worker

2. **QuestionExtractionService** — Question Extraction + Embed Worker
   - File: `src/services/core/question_extraction_service.py`
   - Uses 4 pipelines in sequence:
     1. QuestionExtractionPipeline — LLM extract from page markdown
     2. QuestionEmbeddingPipeline — LLM embed questions
     3. QuestionGroupingPipeline — find/create question_group via cosine search
     4. QuestionPersistencePipeline — persist questions + answers + task progress

---

## Pipelines (Business Logic)

| Pipeline | Purpose | Input | Output |
|----------|---------|-------|--------|
| `question_extraction.py` | Extract Q&A from markdown via LLM | `page_number`, `markdown_content` | `questions[]` array |
| `question_embedding.py` | Embed question_text + answers | `questions[]` dict list | same with `vector` field |
| `question_grouping.py` | Find/create QuestionGroup via similarity | `questions[]` with `vector` | same with `group_id` field |
| `question_persistence.py` | Save to DB + update task progress | `questions[]`, `task_id`, `is_final_page` | `persisted_count`, `errors` |

---

## Database Schema (Exact Match to Spec)

### New Entity: QuestionGroup
```sql
CREATE TABLE questions_groups (
  id UUID PRIMARY KEY,
  subject VARCHAR(255) NOT NULL,
  topic VARCHAR(255) NOT NULL,
  difficulty VARCHAR(50) NOT NULL,
  existence_count BIGINT DEFAULT 0,
  vector_embedding vector(768) NULL,
  created_at TIMESTAMP,
  updated_at TIMESTAMP,
  UNIQUE(subject, topic, difficulty)  -- composite index
);
```

### Updated: Question
- **New fields**:
  - `parent_question_id` (UUID, nullable) — links to parent for composite questions
  - `questions_group_id` (UUID) — foreign key to QuestionGroup
  - `variant_existence_count` (BIGINT)
- **Changed**: `page_id` now nullable (for manual questions)
- **Removed**: `answers`, `sub_questions`, `correct_answer` (now in Answer entity)
- **Made nullable**: `difficulty`, `subject`, `topic` (for sub-questions)

### Updated: Answer
- `value` (VARCHAR 512) — NOT NULL
- `is_correct` (BOOLEAN) — NOT NULL (always true/false)
- `explaination` (TEXT, nullable) — note: keeping spec's spelling

### Enhanced: Task
- `name` (VARCHAR 255) — task name
- `type` (VARCHAR 50) — "document_extraction", etc.
- `entity_id` (UUID) — document_id
- `entity_type` (VARCHAR 50) — "document"
- `logs` (JSONB) — structured event log (append-only)
- `total_pages` (INT, nullable) — total pages in document
- `processed_pages` (INT) — pages completed
- `is_final_page` (BOOLEAN) — (tracked via event payload)

### Migrations
- `m0002_etl_schema_refactor.py` — creates QuestionGroup, alters Questions/Answers/Tasks tables

---

## Repositories

| Repo | New Methods |
|------|-------------|
| `QuestionGroupRepository` | `find_by_metadata()`, `cosine_search()`, `create_with_vector()`, `increment_existence_count()` |
| `AnswerRepository` | `get_by_question()`, `create_for_question()`, `create_batch()`, `delete_by_question()` |
| `QuestionRepository` | `get_sub_questions()`, `get_by_document()`, `find_filtered()`, `count_filtered()` |
| `TaskRepository` | `get_latest_by_document()`, `increment_processed_pages()`, `append_log()` |

---

## Event Handlers

| Handler | Listens to | Does |
|---------|-----------|------|
| `QuestionExtractionHandler` | `question_extraction_requested` | Calls `QuestionExtractionService.process_page()` |
| `DocumentExtractionCompletedHandler` | `document_extraction_completed` | Marks document status = COMPLETED |

**Event Dispatcher**: Updated to register both handlers

---

## Services (High-level APIs)

- **QuestionService** — filtering, status update, answer management
- **DocumentService** — document queries + task tracking
- **PageService** — unchanged (still available)

---

## Routes (HTTP API)

### Questions
- `GET /questions` — filter by subject/topic/difficulty/status
- `GET /questions/{id}` — detail with answers + sub_questions
- `PATCH /questions/{id}/status` — approve/reject (0-2)
- `POST /questions/{id}/review` — submit answer corrections
- `GET /questions/page/{page_id}` — top-level questions for page
- `GET /questions/type/{type}` — questions by type
- `GET /questions/taxonomy/search` — filter by subject/topic

### Documents
- `GET /documents/{id}` — detail + latest task
- `GET /documents/{id}/tasks` — latest extraction task
- `GET /documents/{id}/tasks/{task_id}` — specific task progress
- `GET /documents/{id}/questions` — all extracted questions
- `GET /documents` — list all
- `GET /documents/pending` — pending extraction
- `GET /documents/status/{status}` — by status
- `GET /documents/file/{file_id}` — by file

### Pages
- `GET /pages/{id}/questions` — questions for page
- `GET /pages/{id}` — page detail
- `GET /pages/document/{doc_id}` — pages in document
- `GET /pages` — all pages

---

## Entities & DTOs

### New DTOs (src/dtos/question/res.py)
- `AnswerResponse` — id, value, is_correct, explaination, timestamps
- `SubQuestionResponse` — id, question_text, question_type, answers, status
- `QuestionResponse` — core fields
- `QuestionDetailResponse` — QuestionResponse + answers + sub_questions
- `TaskProgressResponse` — id, name, status, progress, pages, logs

---

## Flow Diagrams

### Event Chain
```
PDF Upload
  ↓
DocumentExtractionService.extract_document()
  ├─ Render pages (PDF → PNG)
  ├─ Run OCR pipeline
  ├─ Validate content via LLM
  ├─ Save Page records
  └─ For each page: call on_page_ready(page, task)
    ↓
    [Publish] question_extraction_requested event
    ↓
QuestionExtractionHandler (async worker)
  ↓
QuestionExtractionService.process_page()
  ├─ QuestionExtractionPipeline (extract questions)
  ├─ QuestionEmbeddingPipeline (embed)
  ├─ QuestionGroupingPipeline (find/create group)
  ├─ QuestionPersistencePipeline (persist + progress)
  └─ If is_final_page: [Publish] document_extraction_completed
    ↓
DocumentExtractionCompletedHandler
  └─ Mark document status = COMPLETED
```

---

## Key Design Patterns

### Separation of Concerns
- **Services**: High-level business workflows, orchestration
- **Pipelines**: Composable, isolated transformations (extract → embed → group → persist)
- **Repositories**: Data access (CRUD + domain queries)
- **Handlers**: Event routing (Kafka → Service)
- **Routes**: HTTP API layer

### Async/Await
- Services use `asyncio` for pipeline composition
- Pipelines support `async def process()`
- Handlers run async in worker context

### Append-Only Logging
- Task.logs is JSONB, never overwritten
- TaskLogger.append_log() adds timestamped event entries
- Progress tracked per-page with durations

### Vector Similarity
- Cosine distance via pgvector: `<=>` operator
- Default threshold: 0.75 (configurable)
- Groups filtered by taxonomy first, then vector search within subset

---

## Files Summary

### New
- `src/entities/question_group.py`
- `src/repos/question_group_repo.py`
- `src/repos/answer_repo.py`
- `src/services/core/document_extraction_service.py`
- `src/services/core/question_extraction_service.py`
- `src/pipelines/question_grouping.py`
- `src/pipelines/question_persistence.py`
- `src/shared/helpers/task_logger.py`
- `src/handlers/question_extraction_handler.py`
- `src/handlers/document_extraction_completed_handler.py`
- `src/lib/db/migrations/m0002_etl_schema_refactor.py`

### Updated
- `src/entities/question.py` — schema changes
- `src/entities/answer.py` — is_correct not nullable
- `src/entities/task.py` — progress tracking fields
- `src/repos/question_repo.py` — new query methods
- `src/repos/task_repo.py` — progress methods
- `src/services/question_service.py` — filtering, answer management
- `src/services/document_service.py` — task tracking
- `src/pipelines/question_embedding.py` — refactored to take dicts, embed question+answers
- `src/handlers/event_dispatcher.py` — register new handlers
- `src/routes/question_route.py` — filtering, review
- `src/routes/document_route.py` — task endpoints
- `src/routes/page_route.py` — page questions
- `src/dtos/question/res.py` — new response DTOs

---

## Next Steps (Ready for Testing)

1. **Run migrations**: `python -m src.lib.db.migration_manager up`
2. **Run unit tests**: Test each pipeline and repo independently
3. **Test flow end-to-end**: Upload PDF → validate pages → extract → group → persist
4. **Monitor**: Check task.logs for timing and error tracking
5. **Tune**: Adjust similarity_threshold (0.75) based on group quality

---

## Notes

- All code follows existing patterns (BaseEntity, BaseRepo, BasePipeline, etc.)
- Imports verified ✓
- No hardcoded thresholds (similarity_threshold configurable)
- Task progress = processed_pages / total_pages (0.0 to 1.0)
- Answer.is_correct always specified (true/false, never null)
- Sub-questions: parent_question_id != null, difficulty/subject/topic are null
