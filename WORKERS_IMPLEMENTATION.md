# Workers Implementation Summary

## Overview
Implemented two specialized worker modules following the existing `src/worker.py` pattern but tailored for specific event-driven tasks:

### 1. Document Extraction Worker
**File**: `src/workers/document_extraction_worker.py`

**Purpose**: Handles `document_extraction_requested` events and orchestrates OCR + validation

**Key Components**:
- `setup_worker_environment()`: Initializes DI container, database connections, model binding
- `handle_document_extraction_event()`: Async event handler that:
  - Creates DocumentExtractionService instance
  - Calls service.extract_document() with on_page_ready callback
  - Callback publishes `question_extraction_requested` events to Kafka for each page
  - Logs progress and errors
- `create_event_handler()`: Wrapper that validates event type and dispatches to async handler
- `main()`: Entry point with graceful shutdown handling (SIGINT/SIGTERM)

**Event Flow**:
```
document_extraction_requested (Kafka)
  ↓
DocumentExtractionWorker.handle_document_extraction_event()
  ↓
DocumentExtractionService.extract_document()
  ├─ Renders PDF pages
  ├─ Runs OCR pipeline
  ├─ Validates content via LLM
  ├─ Saves Page records
  └─ For each page: callback → publishes question_extraction_requested
```

### 2. Question Extraction Worker
**File**: `src/workers/questions_extraction_worker.py`

**Purpose**: Handles `question_extraction_requested` events and orchestrates question extraction + embedding + grouping + persistence

**Key Components**:
- `setup_worker_environment()`: Same initialization as document worker
- `handle_question_extraction_event()`: Async event handler that:
  - Receives page_id, task_id, is_final_page from event
  - Creates QuestionExtractionService instance
  - Calls service.process_page() which chains 4 pipelines:
    1. QuestionExtractionPipeline — extract from markdown
    2. QuestionEmbeddingPipeline — embed questions + answers
    3. QuestionGroupingPipeline — find/create semantic groups
    4. QuestionPersistencePipeline — save to DB, update task progress
  - If is_final_page=true: publishes `document_extraction_completed` event
  - Handles errors: updates task status to FAILED if exception occurs
- `create_event_handler()`: Wrapper that validates event type
- `main()`: Entry point with graceful shutdown

**Event Flow**:
```
question_extraction_requested (Kafka)
  ↓
QuestionExtractionWorker.handle_question_extraction_event()
  ↓
QuestionExtractionService.process_page()
  ├─ QuestionExtractionPipeline (extract)
  ├─ QuestionEmbeddingPipeline (embed)
  ├─ QuestionGroupingPipeline (group)
  ├─ QuestionPersistencePipeline (persist + progress)
  └─ If is_final_page: publishes document_extraction_completed
```

---

## Shared Infrastructure

### DI Container Registration (src/app.py)
Updated `setup_di_container()` to register:

```python
# Kafka messaging
container.register_singleton("kafka_producer", KafkaProducerImpl())
container.register_singleton("kafka_consumer", KafkaConsumerImpl())

# High-level services
container.register_singleton("document_service", DocumentService())
container.register_singleton("question_service", QuestionService())
container.register_singleton("page_service", PageService())

# Core extraction services (factories, non-singleton)
container.register_type(
    DocumentExtractionService,
    lambda: DocumentExtractionService(...),
    singleton=False
)
container.register_type(
    QuestionExtractionService,
    lambda: QuestionExtractionService(llm_client=...),
    singleton=False
)
```

### Model Binding
Updated `bind_models_to_database()` to include new entities:
- QuestionGroup (new)
- Answer (new)
- Question, Document, Page, Task, etc. (existing)

---

## Running the Workers

### Start Document Extraction Worker
```bash
python -m src.workers.document_extraction_worker
```

### Start Question Extraction Worker
```bash
python -m src.workers.questions_extraction_worker
```

### Combined Monitoring
Both workers:
- Subscribe to their respective Kafka topics
- Support graceful shutdown (SIGINT/SIGTERM)
- Log all operations (asyncio events, errors, progress)
- Update task status on failures
- Publish downstream events for the next stage

---

## Architecture Alignment

### Worker Pattern
- **Consistent**: Follow `src/worker.py` structure (setup_worker_environment, create_event_handler, main)
- **Specific**: Each worker handles its own event type and calls its service
- **Observable**: Detailed logging at each stage
- **Resilient**: Error handling with task status updates

### Service Separation
- **DocumentExtractionWorker**: Focuses on document → pages
- **QuestionExtractionWorker**: Focuses on pages → questions → persistence
- **Handlers**: Stay thin (route events to workers, run in FastAPI context)
- **Workers**: Heavy lifting (run in separate processes, handle async work)

### Event Chain
```
PDF Upload API
  ↓ (sync)
FastAPI endpoint
  ├─ Calls DocumentProcessingService (for direct API flow)
  └─ Or publishes document_extraction_requested (for async event flow)
    ↓
DocumentExtractionWorker (separate process)
  └─ Publishes question_extraction_requested per page
    ↓
QuestionExtractionWorker (separate process)
  └─ Publishes document_extraction_completed (final page only)
    ↓
DocumentExtractionCompletedHandler (FastAPI context)
  └─ Updates document status to COMPLETED
```

---

## Next Steps

1. **Test locally**: Run both workers and publish test events via CLI
2. **Monitor Kafka topics**: `question_extraction_requested`, `document_extraction_completed`
3. **Check logs**: Verify graceful shutdown handling
4. **Performance**: Monitor page extraction rate, embedding latency, persistence throughput
5. **Reliability**: Implement dead-letter queue for failed events (optional)
