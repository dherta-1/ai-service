# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Quick Setup

```bash
# Install dependencies (using uv)
uv sync                                  # Install all dependencies
uv sync --extra dev                      # Install with dev tools

# Running services
python main.py                           # Start FastAPI server (port 8000)
uv run -m src.worker                     # Start Kafka consumer worker
docker-compose up -d                     # Start Docker stack (PostgreSQL, Redis, Kafka)

# Database operations
uv run -m src.cli migrate run             # Run pending migrations
uv run -m src.cli migrate create <name>   # Create new migration
uv run -m src.cli seed run                # Run seeds

# Code quality
uv run pytest tests/ -v --cov=src         # Run tests with coverage
uv run flake8 src/ && uv run mypy src/    # Lint and type-check
uv run black src/                         # Format code
uv run python scripts/generate_grpc.py    # Generate gRPC code from .proto files
```

---

## Project Overview

**ai-service** is a FastAPI microservice for document processing and AI-powered question extraction. It handles:

1. **Document Processing**: Render PDFs → OCR → content validation
2. **Question Extraction**: Extract questions from markdown using LLM
3. **Question Grouping**: Cluster questions by semantic similarity (vector embeddings)
4. **Persistence**: Save questions, answers, and task progress to PostgreSQL

### Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Web Framework | FastAPI | Async REST API with auto-docs |
| RPC | gRPC + Protocol Buffers | Inter-service communication |
| ORM | Peewee | Database abstraction with migrations |
| Cache | Redis | Query caching, event delivery |
| Event Bus | Kafka | Async document processing pipeline |
| AI/LLM | Gemini, OpenAI, Ollama | Question extraction & embedding |
| OCR | PaddleOCR | Document text extraction |
| Storage | S3/Boto3 | File persistence |
| DI | Custom DIContainer | Lightweight dependency injection |

---

## Architecture: Worker Pattern + Pipelines

The system follows a **two-stage processing model** with event-driven orchestration:

### Stage 1: Document Extraction Worker
- **Service**: `src/services/core/document_extraction_service.py`
- **Flow**: PDF pages → render to images → OCR extract → LLM validate → save Page records
- **Output**: Emits `question_extraction_requested` event for each page

### Stage 2: Question Extraction Worker
- **Service**: `src/services/core/question_extraction_service.py`
- **5 Sequential Pipelines**:
  1. **QuestionExtractionPipeline** — LLM extracts questions from page markdown
  2. **AnswerParsingPipeline** — Converts answers to structured `{value, is_correct}` format
  3. **QuestionEmbeddingPipeline** — LLM embeds question + answers as vectors
  4. **QuestionGroupingPipeline** — Finds/creates QuestionGroup via cosine similarity
  5. **QuestionPersistencePipeline** — Creates subject/topic records, saves questions, updates task progress

**Event Flow**:
```
File Upload
  ↓
DocumentExtractionService (extracts pages via event)
  ↓
Emits: question_extraction_requested (per page)
  ↓
QuestionExtractionService (processes via event)
  ↓
Emits: question_extraction_completed (final page)
  ↓
Document marked COMPLETED
```

**Key Design**:
- Each pipeline is **composable** and testable independently
- Answer format: All questions use `answers: [{value: str, is_correct: bool}]` or `null`
- Vector similarity uses **cosine distance** in Python (avoids pgvector ops)
- Question grouping: **Two-step approach** → taxonomy filter (subject/topic/difficulty) then vector similarity

---

## Database Schema (Focus Areas)

### QuestionGroup (New Entity)
```
id: UUID (primary key)
subject: VARCHAR(255)
topic: VARCHAR(255)
difficulty: VARCHAR(50)
existence_count: BIGINT          # How many questions reused this group
vector_embedding: vector(768)    # Semantic vector for similarity search
```
- **No composite index** on taxonomy — multiple groups can share same subject/topic/difficulty
- Groups differentiated primarily by vector_embedding

### Question (Updated)
```
parent_question: UUID (nullable)     # Links to parent for composite questions
questions_group: UUID                # FK to QuestionGroup
variant_existence_count: BIGINT      # Track reuse count
```
- `subject`, `topic`, `difficulty` now nullable (sub-questions inherit from parent)

### Answer (New Dedicated Table)
```
question: UUID (FK)
value: VARCHAR(512)            # Answer text
is_correct: BOOLEAN            # Always true/false
explaination: TEXT (nullable)  # Note: keeping spec's spelling
```

### Migrations
- `m0001_create_entities.py` — Core schema
- `m0002_add_overlap_content.py` — Content validation improvements

---

## Key Pipelines & Data Flow

### Question Extraction Pipeline
**Input**: Page markdown  
**Output**: `{question_text, question_type, difficulty, subject, subject_vi, topic, topic_vi, answers: [{value, is_correct}], sub_questions: [{order, sub_question_text, question_type, answers, image_list}], image_list}`

**Normalization Rules**:
- Answer format is **already structured** in LLM output (no JSON string conversion)
- True/False: answers list with both options, exactly one marked `is_correct: true`
- Multiple choice, selection: list of options, exactly one correct
- Short answer, essay: single answer in list with `is_correct: true` or `null` if unknown
- Composite: answers must be `null`, sub_questions contain the answers
- **New**: Returns `subject_vi` and `topic_vi` (Vietnamese translations) alongside subject/topic codes
- **New**: Sub-questions include `order` field (1-indexed) for sequence preservation

### Question Persistence Pipeline
**Three-Step Process**:
1. **Create Subject/Topic Records**: For each question, ensure subject and topic codes exist in Subject/Topic tables
   - Uses `SubjectRepository.get_or_create(code, name, name_vi)` 
   - Uses `TopicRepository.get_or_create(code, name, name_vi)`
   - Creates records with Vietnamese translations if provided
2. **Persist Questions**: Save Question records with subject/topic codes as string references
3. **Update Task**: Increment processed pages count and update task status

**Important**: Subject and topic are stored as string codes in Question table, but corresponding records are created in Subject/Topic tables with Vietnamese translations.

### Debug Export (Development)
When `log_results = true`, all pipelines export debug files to `/debug/<pipeline_name>/`:
- `input_p<num>_<timestamp>.json` — Input payload
- `output_p<num>_<timestamp>.json` — Output payload (sanitized)
- `error_p<num>_<timestamp>.json` — Errors with context

---

## Common Tasks

### Adding a New Pipeline
1. Create `src/pipelines/my_pipeline.py` inheriting from `BasePipeline`
2. Implement `validate(payload)`, `async process(payload) -> dict`, `postprocess(result)`
3. Add debug export: `export_pipeline_debug(pipeline_name, stage, data, page_number)`
4. Integrate into service as a processing step
5. Test with sample data

### Modifying Question Extraction Prompt
- File: `src/prompts/question_extraction_prompt.py`
- Update template, examples, and strict rules
- Schema fields: `question_text`, `question_type`, `difficulty`, `subject`, `topic`, `answers`, `image_list`, `sub_questions`
- Answer format: `[{value: "...", is_correct: true|false}]` (no `correct_answer` field)

### Debugging Question Grouping
1. Enable `log_results = true` in `.env`
2. Check `/debug/question_extraction/` for extracted questions
3. Verify `vector_embedding` is not `None`
4. Adjust threshold (currently 0.75) if matches too strict/loose

### Adding a Question Field
1. Update `src/pipelines/question_extraction.py` → `_normalize_questions()`
2. Update `src/entities/question.py` if persisting to schema
3. Create migration if adding column
4. Update prompt template to request field
5. Update `question_persistence.py` to pass field to `Question.create()`

---

## Important Conventions

### Answer Data Format
**From extraction**: `answers: [{value: "True", is_correct: true}, {value: "False", is_correct: false}]`  
**To persistence**: Same format  
**In DB**: Split into Answer rows with `question_id`, `value`, `is_correct`

### Vector Embeddings
- **Dimension**: 768 (fixed)
- **Model**: Configured LLM embedding model (e.g., `text-embedding-3-small`)
- **Search**: Cosine similarity via NumPy
- **Threshold**: 0.75 default (adjustable)

### Question Types
Enum: `multiple_choice`, `true_false`, `short_answer`, `essay`, `selection`, `composite`

---

## File Structure (Key Paths)

```
src/
├── pipelines/
│   ├── question_extraction.py          # LLM extract + normalize
│   ├── answer_parsing.py               # Pass-through for compatibility
│   ├── question_embedding.py           # LLM embed
│   ├── question_grouping.py            # Vector-based grouping
│   ├── question_persistence.py         # Save to DB
│   ├── content_extraction.py           # OCR + cropping
│   └── content_validation.py           # LLM validate
│
├── services/core/
│   ├── document_extraction_service.py  # Stage 1 worker
│   └── question_extraction_service.py  # Stage 2 worker
│
├── handlers/
│   ├── question_extraction_handler.py  # Event handler
│   └── event_dispatcher.py             # Kafka event router
│
├── repos/
│   ├── question_repo.py
│   ├── question_group_repo.py          # Taxonomy + vector matching
│   └── answer_repo.py
│
├── entities/
│   ├── question.py
│   ├── question_group.py
│   └── answer.py
│
├── prompts/
│   └── question_extraction_prompt.py
│
├── shared/helpers/
│   └── debug_export.py                 # Debug file export
│
└── settings.py
```

---

## Testing & Debugging

### Run Tests
```bash
uv run pytest tests/ -v --cov=src                    # All tests with coverage
uv run pytest tests/test_question_extraction.py -v   # Specific file
uv run pytest -k "test_pattern" -v                   # By pattern
```

### Inspect Debug Files
```bash
ls debug/question_extraction/
cat debug/question_extraction/output_p1_*.json | jq .
```

### Manual Vector Similarity Check
```python
import numpy as np

vec1 = [0.1, 0.2, 0.3, ...]
vec2 = [0.15, 0.21, 0.32, ...]

q_vec = np.array(vec1, dtype=float)
g_vec = np.array(vec2, dtype=float)
cosine_sim = float(np.dot(g_vec, q_vec) / (np.linalg.norm(g_vec) * np.linalg.norm(q_vec)))
print(cosine_sim)  # 0.0 to 1.0
```

---

## Environment Setup (.env)

```
# Database
DATABASE_URL=postgresql://user:pass@localhost/ai_service
POSTGRES_USER=postgres
POSTGRES_PASSWORD=password
POSTGRES_DB=ai_service

# Redis
REDIS_URL=redis://localhost:6379/0

# Kafka
KAFKA_BOOTSTRAP_SERVERS=localhost:9092

# LLM
LLM_PROVIDER=gemini
LLM_API_KEY=sk-...
LLM_MODEL=gemini-2.0-flash
LLM_EMBEDDING_MODEL=text-embedding-3-small
LLM_EMBEDDING_DIMENSION=768

# S3
AWS_S3_BUCKET=ai-service-documents
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=us-east-1

# Debug
DEBUG=true
LOG_RESULTS=true
```

---

## Before Committing

1. **Run tests**: `uv run pytest tests/ -v`
2. **Format & lint**: `uv run black src/` then `uv run flake8 src/ && uv run mypy src/`
3. **Verify migrations**: `uv run -m src.cli migrate run`
4. **Check debug exports**: If adding pipeline, verify `export_pipeline_debug()` calls
5. **Update prompts**: If changing LLM behavior, update prompt template + examples

---

## Architecture Principles

- **Composable pipelines**: Each independently testable and debuggable
- **Unified answer format**: `answers: [{value, is_correct}]` across all question types
- **Vector-first grouping**: Semantic similarity is primary matching criterion
- **Two-step efficiency**: Taxonomy filter first, then vector search
- **Debug-friendly**: `log_results=true` exports all intermediate states
- **No correct_answer field**: Use `is_correct` boolean in answers list instead
