# New ETL Flow Refactor Plan

## Overview
This document outlines the refactor plan for the document extraction flow based on the manual specification (`document-etl-flow-vi.md`) and current codebase analysis. The goal is to align the implementation with the architectural design while improving clarity, maintainability, and event-driven architecture.

---

## Current State Analysis

### Architecture Overview
The current system implements a document ETL flow with:
- **OCR Pipeline**: Extracts content from document pages
- **Content Validation**: Validates OCR output against images
- **Question Extraction**: Extracts questions from validated content
- **Question Embedding**: Embeds questions for vector search
- **Event-driven Worker**: Processes document events from Kafka

### Key Components
1. **DocumentProcessingService** - Orchestrates the entire flow
2. **QuestionExtractionPipeline** - Extracts questions from markdown content
3. **QuestionEmbeddingPipeline** - Generates embeddings for questions
4. **Event Dispatcher** - Routes events to handlers
5. **Repositories** - Handle persistence (Document, Page, Question, Answer)
6. **Database Entities** - Models for Question, Answer, Page, Document, etc.

### Current Gaps vs. Specification

| Requirement | Current State | Gap |
|---|---|---|
| Event-driven architecture | Partially implemented (Kafka consumer) | Need to separate OCR+Validate worker from Question Extraction+Embed worker |
| Question persistence with vector search | Basic insertion | Missing question_group matching and cosine search |
| Composite question handling | Partially supported | Need proper sub-question relationship (parent_question_id) |
| Task progress tracking | Minimal | Missing per-page progress + final_page flag |
| Answer structure | Uses BinaryJSON | Needs refactor to use Answer entity with is_correct field |
| Vector embeddings for grouping | VectorField exists | Missing similarity search logic |

---

## Exact Database Schema (per specification)

### Entity Definitions

#### 1. **QuestionGroup** (NEW) - `src/entities/question_group.py`
Match exact specification from document-etl-flow-vi.md:
```python
class QuestionGroup(BaseEntity):
    # Database columns (exact match to specification)
    subject = CharField(max_length=255, null=False)
    topic = CharField(max_length=255, null=False)
    difficulty = CharField(max_length=50, null=False)
    existence_count = BigIntegerField(default=0)
    vector_embedding = VectorField(dimensions=768, null=True)
    created_at = DateTimeField(auto_now_add=True)
    updated_at = DateTimeField(auto_now=True)
    
    class Meta:
        collection_name = "questions_groups"
        indexes = [
            ("subject", "topic", "difficulty"),  # Composite index for grouping
        ]
```

#### 2. **Question** (UPDATE) - Update `src/entities/question.py`
Match exact specification:
```python
class Question(BaseEntity):
    # Foreign keys
    page = ForeignKeyField(Page, backref="questions", null=True)  # null for manual created
    parent_question = ForeignKeyField("self", backref="sub_questions", null=True)  # for composite
    questions_group = ForeignKeyField(QuestionGroup, backref="questions")
    
    # Core fields
    question_text = TextField(null=False)
    question_type = CharField(max_length=50, null=False)  # one of: multiple_choice, selection, true_false, short_answer, essay, composite
    
    # Taxonomy (nullable for sub-questions when parent_question_id != null)
    difficulty = CharField(max_length=50, null=True)  # easy, medium, hard
    subject = CharField(max_length=255, null=True)
    topic = CharField(max_length=255, null=True)
    
    # Content (nullable for sub-questions)
    image_list = BinaryJSONField(null=True)  # JSON array of image/table references
    
    # Tracking
    variant_existence_count = BigIntegerField(default=1)
    vector_embedding = VectorField(dimensions=768, null=True)
    status = SmallIntegerField(default=0)  # 0=pending, 1=approved, 2=rejected
    
    created_at = DateTimeField(auto_now_add=True)
    updated_at = DateTimeField(auto_now=True)
    
    class Meta:
        collection_name = "questions"
        indexes = [
            "page",
            "parent_question",
            "questions_group",
            ("subject", "topic", "difficulty"),
        ]
```

#### 3. **Answer** (ALIGN) - Update `src/entities/answer.py`
Match exact specification:
```python
class Answer(BaseEntity):
    # Foreign key
    question = ForeignKeyField(Question, backref="answers")
    
    # Fields (exact match to specification - note: "explaination" typo in spec kept for DB compatibility)
    value = CharField(max_length=512, null=False)
    is_correct = BooleanField(null=False)  # NOT nullable - always specify true/false
    explaination = TextField(null=True)  # Note: keeping spec's spelling for DB column name
    
    created_at = DateTimeField(auto_now_add=True)
    updated_at = DateTimeField(auto_now=True)
    
    class Meta:
        collection_name = "answers"
        indexes = [
            "question",
        ]
```

#### 4. **Task** (ENHANCE) - Update `src/entities/task.py`
Already exists, add progress tracking fields:
```python
class Task(BaseEntity):
    # Existing fields (unchanged)
    name = CharField(max_length=255)
    type = CharField(max_length=50)  # e.g., "document_extraction", "question_extraction"
    entity_id = UUIDField()  # document_id for extraction tasks
    entity_type = CharField(max_length=50)  # "document"
    logs = BinaryJSONField(null=True)  # JSONB for structured logging
    status = SmallIntegerField()  # 0=pending, 1=processing, 2=completed, 3=failed
    progress = DecimalField(default=0.0)  # 0.0 to 1.0
    
    # Add for tracking progress
    total_pages = IntegerField(null=True)  # Total pages in document
    processed_pages = IntegerField(default=0)  # Pages completed
    is_final_page = BooleanField(default=False)  # Flag for completion detection
    
    created_at = DateTimeField(auto_now_add=True)
    updated_at = DateTimeField(auto_now=True)
```

---

## Refactor Plan - Phase 1: Data Model (Database Schema)

### Task 1.1: Create QuestionGroup Entity
**File**: `src/entities/question_group.py`
```python
# Create exact entity matching specification
- subject: CharField(255) - NOT NULL
- topic: CharField(255) - NOT NULL  
- difficulty: CharField(50) - NOT NULL
- existence_count: BigIntegerField - default 0
- vector_embedding: VectorField(768) - nullable
- Composite index: (subject, topic, difficulty)
```
- [ ] Create entity file
- [ ] Add pgvector import and VectorField
- [ ] Add proper Meta.indexes for query performance

### Task 1.2: Update Question Entity
**File**: `src/entities/question.py`

Modify structure to match specification exactly:
```python
# Update existing fields
- page: ForeignKeyField(Page) → make nullable (null for manual created)
- Add parent_question: ForeignKeyField("self") - nullable, backref="sub_questions"
- Add questions_group: ForeignKeyField(QuestionGroup) - NOT NULL

# Rename field
- Remove: answers (BinaryJSON) - will use Answer entity instead
- Ensure: difficulty, subject, topic are nullable
- Ensure: image_list is nullable

# Add new tracking
- Add variant_existence_count: BigIntegerField
- Ensure: vector_embedding exists
- Ensure: status field exists

# Update indexes
- Add composite index: (subject, topic, difficulty)
- Add index: parent_question
- Add index: questions_group
```
- [ ] Update entity class
- [ ] Update field definitions
- [ ] Update Meta.indexes

### Task 1.3: Update Answer Entity
**File**: `src/entities/answer.py`

Match specification exactly:
```python
# Ensure exact column names
- question: ForeignKeyField(Question) - backref="answers"
- value: CharField(512) - NOT NULL
- is_correct: BooleanField() - NOT NULL (always true or false)
- explaination: TextField() - nullable (keep spec's typo for DB compatibility)
- created_at, updated_at: DateTimeField
```
- [ ] Verify foreign key relationship
- [ ] Ensure is_correct is NOT nullable
- [ ] Keep "explaination" spelling from spec for DB column name

### Task 1.4: Update Task Entity (if needed)
**File**: `src/entities/task.py`

Add progress tracking fields:
```python
# Add if not present
- total_pages: IntegerField - nullable
- processed_pages: IntegerField - default 0
- is_final_page: BooleanField - default False
```
- [ ] Add fields for progress tracking
- [ ] Verify logs field is JSONB

### Task 1.5: Create Database Migrations
**Location**: `src/lib/db/migrations/`

- [ ] Migration: Create `questions_groups` table with exact specification
- [ ] Migration: Alter `questions` table - add parent_question_id, questions_group_id, variant_existence_count
- [ ] Migration: Alter `questions` table - make page_id nullable, make difficulty/subject/topic nullable
- [ ] Migration: Alter `questions` table - remove answers column if exists
- [ ] Migration: Create composite indexes
- [ ] Migration: Add progress tracking fields to tasks table if not exist

---

## Refactor Plan - Phase 2: Core Service Logic

Core services go in **`src/services/core/`** - these contain business logic for the ETL flow.
Event handlers in **`src/handlers/`** will use these services.

### Task 2.1: Create QuestionGroupRepository
**File**: `src/repos/question_group_repo.py`

Implement repository for question grouping:
```python
class QuestionGroupRepository(BaseRepository):
    def find_by_metadata(self, subject: str, topic: str, difficulty: str) -> List[QuestionGroup]:
        """Query groups by exact metadata match"""
        return self.query(
            (QuestionGroup.subject == subject) &
            (QuestionGroup.topic == topic) &
            (QuestionGroup.difficulty == difficulty)
        )
    
    def cosine_search(self, vector: List[float], subject: str, topic: str, 
                     difficulty: str, threshold: float = 0.75) -> List[QuestionGroup]:
        """
        Perform cosine similarity search against groups with matching metadata.
        Uses PostgreSQL pgvector distance operator (<=>).
        Returns groups with similarity >= threshold, ordered by distance.
        """
        # Implementation using pgvector distance
        pass
    
    def create_with_vector(self, subject: str, topic: str, difficulty: str, 
                          vector: List[float]) -> QuestionGroup:
        """Create new question group with embedding"""
        pass
    
    def increment_existence_count(self, group_id: UUID) -> None:
        """Increment existence_count when adding question to group"""
        pass
```
- [ ] Create repository file
- [ ] Implement metadata filtering
- [ ] Implement cosine_search using pgvector
- [ ] Implement creation method

### Task 2.2: Create QuestionGroupService
**File**: `src/services/core/question_group_service.py`

High-level service for question grouping logic (per specification):
```python
class QuestionGroupService:
    def __init__(self, question_group_repo: QuestionGroupRepository, 
                 embedding_service: QuestionEmbeddingService):
        pass
    
    async def find_or_create_group(self, question_data: Dict, 
                                   vector: List[float], 
                                   similarity_threshold: float = 0.75) -> QuestionGroup:
        """
        Specification: Persist câu hỏi step 2-3:
        1. Extract metadata: subject, topic, difficulty
        2. Query question_groups by metadata
        3. Cosine search against matching groups
        4. If found (sim >= threshold): return group with highest similarity
        5. If not found: create new group with vector
        """
        subject = question_data.get("subject")
        topic = question_data.get("topic")
        difficulty = question_data.get("difficulty")
        
        # Query groups by metadata
        candidates = self.question_group_repo.find_by_metadata(subject, topic, difficulty)
        
        if candidates:
            # Cosine search to find best match
            matches = self.question_group_repo.cosine_search(
                vector, subject, topic, difficulty, similarity_threshold
            )
            if matches:
                return matches[0]  # highest similarity
        
        # No match found, create new group
        return self.question_group_repo.create_with_vector(
            subject, topic, difficulty, vector
        )
```
- [ ] Create service file
- [ ] Implement grouping logic from specification
- [ ] Handle similarity threshold (default 0.75, configurable)

### Task 2.3: Create QuestionPersistenceService
**File**: `src/services/core/question_persistence_service.py`

Core business logic for persisting questions (main ETL logic):
```python
class QuestionPersistenceService:
    def __init__(self, question_repo, answer_repo, question_group_service, 
                 embedding_service, task_repo):
        pass
    
    async def persist_extracted_questions(self, 
                                         page_id: UUID,
                                         extracted_questions: List[Dict],
                                         task_id: UUID,
                                         is_final_page: bool) -> Dict:
        """
        Specification: Persist câu hỏi (step 1-4)
        
        For each extracted question:
        1. Embed question content (question_text + answers)
        2. Find or create question_group using embedding
        3. If composite: save main question, then sub-questions with parent_question_id
        4. If not composite: save normally
        5. Create Answer records for each answer (is_correct boolean)
        
        Return: {
            "persisted_count": int,
            "failed_count": int,
            "errors": List[str]
        }
        """
        results = {"persisted_count": 0, "failed_count": 0, "errors": []}
        
        for question_data in extracted_questions:
            try:
                # Step 1: Embed
                vector = await self.embedding_service.embed_question(question_data)
                
                # Step 2: Find or create group
                group = await self.question_group_service.find_or_create_group(
                    question_data, vector
                )
                
                # Step 3-4: Persist question
                if question_data.get("question_type") == "composite":
                    # Composite: save main question first
                    main_question = self._create_main_question(
                        question_data, page_id, group, vector
                    )
                    
                    # Then save sub-questions with parent reference
                    for sub_q in question_data.get("sub_questions", []):
                        self._create_sub_question(sub_q, page_id, group, main_question)
                else:
                    # Regular question
                    question = self._create_main_question(
                        question_data, page_id, group, vector
                    )
                
                # Step 5: Create Answer records
                for answer_data in question_data.get("answers", []):
                    self.answer_repo.create(
                        question_id=question.id,
                        value=answer_data["value"],
                        is_correct=answer_data["is_correct"],
                        explaination=answer_data.get("explaination")
                    )
                
                results["persisted_count"] += 1
                
            except Exception as e:
                results["failed_count"] += 1
                results["errors"].append(f"Question error: {str(e)}")
        
        # Update task progress
        await self._update_task_progress(task_id, page_id, is_final_page)
        
        return results
    
    async def _update_task_progress(self, task_id: UUID, page_id: UUID, 
                                   is_final_page: bool):
        """
        Specification: Update progress + log task
        - Update processed_pages += 1
        - Calculate progress = processed_pages / total_pages
        - If is_final_page: status = COMPLETED, progress = 1.0
        - Log to task.logs (JSONB)
        """
        task = self.task_repo.get_by_id(task_id)
        task.processed_pages += 1
        task.progress = task.processed_pages / task.total_pages
        
        if is_final_page:
            task.status = 2  # COMPLETED
            task.progress = 1.0
        
        self.task_repo.update(task)
```
- [ ] Create service file
- [ ] Implement full persistence workflow
- [ ] Handle composite questions with parent relationships
- [ ] Create Answer records with is_correct boolean
- [ ] Update task progress tracking

### Task 2.4: Create AnswerRepository
**File**: `src/repos/answer_repo.py`

Simple repository for Answer entity:
```python
class AnswerRepository(BaseRepository):
    def get_by_question(self, question_id: UUID) -> List[Answer]:
        """Get all answers for a question"""
        pass
    
    def create_batch(self, question_id: UUID, answers: List[Dict]) -> List[Answer]:
        """Create multiple answers for a question"""
        pass
```
- [ ] Create repository file

### Task 2.5: Update QuestionExtractionPipeline
**File**: `src/pipelines/question_extraction.py`

Update output format to match Answer structure:
```python
# Expected extracted question format:
{
    "question_text": "...",
    "question_type": "multiple_choice|composite|...",
    "difficulty": "easy|medium|hard",
    "subject": "math|science|...",
    "topic": "...",
    "answers": [
        {"value": "option A", "is_correct": true},
        {"value": "option B", "is_correct": false},
        ...
    ],
    "image_list": [...],
    "sub_questions": [  # only for composite
        {
            "sub_question_text": "...",
            "question_type": "...",
            "answers": [{"value": "...", "is_correct": ...}]
        }
    ]
}
```
- [ ] Verify output structure matches specification
- [ ] Remove correct_answer field (now in Answer.is_correct)
- [ ] Ensure answers is array of {value, is_correct} objects

### Task 2.6: Update QuestionEmbeddingPipeline
**File**: `src/pipelines/question_embedding.py`

Create QuestionEmbeddingService:
```python
class QuestionEmbeddingService:
    async def embed_question(self, question_data: Dict) -> List[float]:
        """
        Embed question for similarity search:
        Concatenate: question_text + " " + answers (joined by ", ")
        Return 768-dim vector
        """
        text_to_embed = question_data["question_text"]
        if question_data.get("answers"):
            answers_text = ", ".join([a["value"] for a in question_data["answers"]])
            text_to_embed = f"{text_to_embed} {answers_text}"
        
        return await self._embed_text(text_to_embed)
```
- [ ] Create service wrapper around pipeline
- [ ] Implement text concatenation strategy
- [ ] Test embedding output dimensions

---

## Refactor Plan - Phase 3: Event-Driven Architecture & Handlers

Core services are used by event handlers defined in `src/handlers/`.

### Task 3.1: Create Event Handlers (use core services)

#### Handler 1: Page Content Extraction Handler (EXISTING)
**File**: `src/handlers/page_content_extracted_event.py`

Listens to: `page_content_extracted` event
Publishes to: Question extraction phase
```python
# Existing handler - needs update to trigger question extraction
class PageContentExtractedEventHandler:
    def __init__(self, document_processing_service):
        pass
    
    def handle(self, event_key: str, event_value: Dict):
        # For each page extracted: 
        # - trigger question extraction
        # - publish next event
        pass
```
- [ ] Update to publish event for question extraction
- [ ] Pass task_id through event chain
- [ ] Include is_final_page flag

#### Handler 2: Question Extraction Handler (NEW)
**File**: `src/handlers/question_extraction_handler.py`

Listens to: `page_content_extracted` event (with page_id)
Uses: QuestionPersistenceService
```python
class QuestionExtractionHandler:
    def __init__(self, 
                 question_persistence_service: QuestionPersistenceService,
                 question_extraction_pipeline: QuestionExtractionPipeline,
                 page_repo: PageRepository,
                 task_repo: TaskRepository):
        pass
    
    async def handle(self, event_key: str, event_value: Dict):
        """
        Event payload:
        {
            "event_type": "question_extraction_requested",
            "page_id": UUID,
            "document_id": UUID,
            "task_id": UUID,
            "is_final_page": bool
        }
        
        Steps:
        1. Load page content from page_id
        2. Extract questions using pipeline
        3. Persist extracted questions using QuestionPersistenceService
        4. Update task progress
        5. Publish completion event
        """
        page_id = event_value["page_id"]
        task_id = event_value["task_id"]
        is_final_page = event_value.get("is_final_page", False)
        
        try:
            # Load page
            page = self.page_repo.get_by_id(page_id)
            
            # Extract questions
            extraction_result = await self.question_extraction_pipeline.process({
                "page_number": page.page_number,
                "markdown_content": page.content
            })
            
            # Persist with grouping
            persist_result = await self.question_persistence_service.persist_extracted_questions(
                page_id=page_id,
                extracted_questions=extraction_result["questions"],
                task_id=task_id,
                is_final_page=is_final_page
            )
            
            # Publish completion event
            if is_final_page:
                # Document complete
                self._publish_event("document_extraction_completed", {
                    "document_id": event_value["document_id"],
                    "task_id": task_id,
                    "total_questions": persist_result["persisted_count"]
                })
            else:
                # Continue with next page
                self._publish_event("question_extraction_completed", {
                    "page_id": page_id,
                    "document_id": event_value["document_id"],
                    "task_id": task_id
                })
                
        except Exception as e:
            logger.error(f"Question extraction failed for page {page_id}: {e}")
            # Mark task as failed
            task = self.task_repo.get_by_id(task_id)
            task.status = 3  # FAILED
            self.task_repo.update(task)
```
- [ ] Create handler file
- [ ] Implement event handling workflow
- [ ] Call QuestionPersistenceService
- [ ] Handle final page completion
- [ ] Publish events for next phase

#### Handler 3: Document Extraction Completion (NEW)
**File**: `src/handlers/document_extraction_completed_handler.py`

Listens to: `document_extraction_completed` event
```python
class DocumentExtractionCompletedHandler:
    def __init__(self, document_repo: DocumentRepository):
        pass
    
    def handle(self, event_key: str, event_value: Dict):
        # Update document status to COMPLETED
        # Set document.progress = 1.0
        # Ready for review
        pass
```
- [ ] Create handler file
- [ ] Update document status
- [ ] Mark as ready for review

### Task 3.2: Update Event Dispatcher
**File**: `src/handlers/event_dispatcher.py`

Register new event handlers:
```python
def initialize_event_handlers():
    dispatcher = get_event_dispatcher()
    
    # Existing
    dispatcher.register("document_queued", DocumentQueuedEventHandler)
    dispatcher.register("page_content_extracted", PageContentExtractedEventHandler)
    
    # New
    dispatcher.register("question_extraction_requested", QuestionExtractionHandler)
    dispatcher.register("document_extraction_completed", DocumentExtractionCompletedHandler)
```
- [ ] Register QuestionExtractionHandler
- [ ] Register DocumentExtractionCompletedHandler
- [ ] Map to topic subscriptions

### Task 3.3: Update Document Processing Service
**File**: `src/services/document_processing_service.py`

Refactor to emit events instead of chaining:
```python
class DocumentProcessingService:
    async def process_document(self, local_file_path: str, 
                               original_filename: str) -> Dict:
        """
        Refactored flow:
        1. Extract pages from PDF (synchronous - OCR + validation)
        2. Create document record
        3. Create task record
        4. Publish event: "question_extraction_requested" for first page
        5. Return (worker will handle rest async)
        
        Note: OCR + validation still done synchronously before event,
        then question extraction happens async in worker via events.
        """
        
        # Existing: Extract pages, run OCR, validate
        pages = await self.extraction_pipeline.process(...)
        
        # Create document and task
        document = self._doc_repo.create(...)
        task = self._task_repo.create({
            "name": f"extract_{document.name}",
            "type": "document_extraction",
            "entity_id": document.id,
            "entity_type": "document",
            "total_pages": len(pages),
            "processed_pages": 0,
            "status": 1,  # PROCESSING
            "progress": 0.0
        })
        
        # Publish event for first page
        self._publish_event("question_extraction_requested", {
            "page_id": pages[0].id,
            "document_id": document.id,
            "task_id": task.id,
            "is_final_page": (len(pages) == 1)
        })
        
        return {"document_id": document.id, "task_id": task.id}
```
- [ ] Update to emit events
- [ ] Keep OCR+validation synchronous
- [ ] Make question extraction async via events
- [ ] Publish event for first page

### Task 3.4: Event Flow Diagram
Event chain for document extraction:

```
User uploads PDF
    ↓
POST /documents/extract
    ↓
DocumentProcessingService.process_document()
    ├─ Extract pages (OCR + validation - SYNC)
    ├─ Create document record
    ├─ Create task record
    └─ Publish "question_extraction_requested" → page[0]
    ↓
Worker / QuestionExtractionHandler
    ├─ Extract questions from page
    ├─ Persist with grouping (QuestionPersistenceService)
    ├─ Update task progress
    └─ If is_final_page=true:
    │   └─ Publish "document_extraction_completed"
    └─ Else:
        └─ (Next page triggered separately or batched)
    ↓
DocumentExtractionCompletedHandler
    └─ Update document.status = COMPLETED
    
User Reviews Questions
    ↓
Question approval/rejection via API
```

- [ ] Document event contract for each event type
- [ ] Add event schema validation

---

## Refactor Plan - Phase 4: Task Progress & Logging

Already covered in Phase 2.3 (QuestionPersistenceService._update_task_progress).

### Task 4.1: Create Task Logger Utility
**File**: `src/shared/helpers/task_logger.py`

Structured logging for task.logs (JSONB field):
```python
class TaskLogger:
    def __init__(self, task_repo: TaskRepository):
        pass
    
    def append_log(self, task_id: UUID, event: Dict):
        """
        Append event to task.logs without overwriting.
        Each log entry includes: timestamp, event_type, message, metadata
        
        Example log entry:
        {
            "timestamp": "2024-01-01T10:00:00Z",
            "event": "page_processed",
            "page_number": 1,
            "questions_count": 5,
            "duration_ms": 1234,
            "status": "success"
        }
        """
        task = self.task_repo.get_by_id(task_id)
        logs = task.logs or []
        
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            **event
        }
        logs.append(log_entry)
        
        task.logs = logs
        self.task_repo.update(task)
    
    def log_page_processed(self, task_id: UUID, page_number: int, 
                          questions_count: int, duration_ms: int):
        """Log page completion"""
        self.append_log(task_id, {
            "event": "page_processed",
            "page_number": page_number,
            "questions_count": questions_count,
            "duration_ms": duration_ms
        })
    
    def log_error(self, task_id: UUID, error_msg: str, page_number: int = None):
        """Log error"""
        self.append_log(task_id, {
            "event": "error",
            "message": error_msg,
            "page_number": page_number
        })
```
- [ ] Create utility file
- [ ] Implement append-only logging
- [ ] Add helper methods for common events

### Task 4.2: Integrate TaskLogger in QuestionPersistenceService
- [ ] Inject TaskLogger into QuestionPersistenceService
- [ ] Log each page completion
- [ ] Log errors with context
- [ ] Track timing metrics

---

## Refactor Plan - Phase 5: API & Route Updates

### Task 5.1: Update Document Routes
**File**: `src/routes/document_route.py`

```python
@router.get("/documents/{id}")
async def get_document(id: UUID):
    """Get document with task progress"""
    document = document_service.get_by_id(id)
    task = task_repo.get_by_entity(document.id, "document")
    return {
        "document": document,
        "task": {
            "id": task.id,
            "status": task.status,
            "progress": task.progress,
            "processed_pages": task.processed_pages,
            "total_pages": task.total_pages,
            "logs": task.logs
        }
    }

@router.post("/documents/{id}/extract")
async def trigger_extraction(id: UUID):
    """Trigger question extraction for document"""
    # Document already has pages from upload
    # Just create task and publish first event
    task = await document_processing_service.process_document(...)
    return {"task_id": task.id, "status": "processing"}

@router.get("/documents/{id}/tasks/{task_id}")
async def get_task_progress(id: UUID, task_id: UUID):
    """Get detailed task progress"""
    task = task_repo.get_by_id(task_id)
    return {
        "id": task.id,
        "status": task.status,
        "progress": task.progress,
        "processed_pages": task.processed_pages,
        "total_pages": task.total_pages,
        "logs": task.logs
    }

@router.get("/documents/{id}/questions")
async def get_document_questions(id: UUID, skip: int = 0, limit: int = 20):
    """Get extracted questions for document"""
    questions = question_repo.get_by_document(id, skip, limit)
    return {
        "total": question_repo.count_by_document(id),
        "questions": questions
    }
```
- [ ] Update GET /documents/{id}
- [ ] Update POST /documents/{id}/extract
- [ ] Create GET /documents/{id}/tasks/{task_id}
- [ ] Create GET /documents/{id}/questions

### Task 5.2: Update Question Routes
**File**: `src/routes/question_route.py`

```python
@router.get("/questions")
async def list_questions(
    subject: Optional[str] = None,
    topic: Optional[str] = None,
    difficulty: Optional[str] = None,
    status: Optional[int] = None,
    skip: int = 0,
    limit: int = 20
):
    """List questions with filtering"""
    filters = {}
    if subject:
        filters["subject"] = subject
    if topic:
        filters["topic"] = topic
    if difficulty:
        filters["difficulty"] = difficulty
    if status is not None:
        filters["status"] = status
    
    questions = question_repo.find(filters, skip, limit)
    return {
        "total": question_repo.count(filters),
        "questions": questions
    }

@router.get("/questions/{id}")
async def get_question(id: UUID):
    """Get question with full context"""
    question = question_repo.get_by_id(id)
    answers = answer_repo.get_by_question(id)
    page = page_repo.get_by_id(question.page_id) if question.page_id else None
    
    return {
        "question": question,
        "answers": answers,
        "page": page,
        "sub_questions": question_repo.get_sub_questions(id) if question.question_type == "composite" else []
    }

@router.patch("/questions/{id}/status")
async def update_question_status(id: UUID, status: int):
    """Update question approval status"""
    # status: 0=pending, 1=approved, 2=rejected
    question = question_repo.get_by_id(id)
    question.status = status
    question_repo.update(question)
    return {"id": id, "status": status}

@router.post("/questions/{id}/review")
async def submit_question_review(id: UUID, corrections: Dict):
    """Submit manual corrections for question"""
    # corrections: {"question_text": "...", "answers": [...], ...}
    question = question_repo.get_by_id(id)
    
    if "question_text" in corrections:
        question.question_text = corrections["question_text"]
    
    if "answers" in corrections:
        # Delete old answers
        answer_repo.delete_by_question(id)
        # Create new answers
        for ans in corrections["answers"]:
            answer_repo.create(
                question_id=id,
                value=ans["value"],
                is_correct=ans["is_correct"]
            )
    
    question_repo.update(question)
    return {"id": id, "updated": True}
```
- [ ] Create GET /questions with filtering
- [ ] Create GET /questions/{id}
- [ ] Create PATCH /questions/{id}/status
- [ ] Create POST /questions/{id}/review

### Task 5.3: Update Page Routes
**File**: `src/routes/page_route.py`

```python
@router.get("/pages/{id}/questions")
async def get_page_questions(id: UUID):
    """Get questions for specific page"""
    questions = question_repo.get_by_page(id)
    return {
        "page_id": id,
        "questions": questions
    }
```
- [ ] Create GET /pages/{id}/questions

### Task 5.4: Create DTOs for responses
**Files**: `src/dtos/question/res.py`, `src/dtos/answer/res.py`

Add response DTOs for new endpoints:
```python
class QuestionDetailResponse(BaseModel):
    id: UUID
    question_text: str
    question_type: str
    difficulty: Optional[str]
    subject: Optional[str]
    topic: Optional[str]
    status: int
    page_id: Optional[UUID]
    parent_question_id: Optional[UUID]
    questions_group_id: UUID
    answers: List[AnswerResponse]
    sub_questions: Optional[List[QuestionDetailResponse]]

class AnswerResponse(BaseModel):
    id: UUID
    value: str
    is_correct: bool
    explaination: Optional[str]

class TaskProgressResponse(BaseModel):
    id: UUID
    status: int
    progress: float
    processed_pages: int
    total_pages: int
    logs: Optional[List[Dict]]
```
- [ ] Create answer response DTO
- [ ] Create question detail response DTO
- [ ] Create task progress response DTO

---

## Refactor Plan - Phase 6: Validation & Testing

### Task 6.1: Unit Tests
- [ ] Test QuestionGroupRepository cosine search logic
- [ ] Test QuestionPersistenceService workflow
- [ ] Test composite question handling
- [ ] Test Answer creation from extracted data

### Task 6.2: Integration Tests
- [ ] Test full ETL flow with sample PDF
- [ ] Test event publishing and handling
- [ ] Test progress tracking through complete flow
- [ ] Test answer persistence and retrieval

### Task 6.3: Pipeline Tests
- [ ] Test QuestionExtractionPipeline output structure
- [ ] Test question normalization logic
- [ ] Test sub-question extraction

---

## Implementation Order (Recommended)

### Timeline: 6 weeks total

**Week 1: Database Schema**
- Phase 1 (all tasks 1.1-1.5)
- Create entities and migrations
- Test schema changes on staging

**Week 2: Core Service Logic**
- Phase 2.1: QuestionGroupRepository
- Phase 2.2: QuestionGroupService
- Phase 2.3: QuestionPersistenceService (main business logic)
- Phase 2.4: AnswerRepository
- Unit test core logic

**Week 3: Integration & Pipelines**
- Phase 2.5: Update QuestionExtractionPipeline
- Phase 2.6: QuestionEmbeddingService
- Integration test extraction → persistence flow

**Week 4: Event-Driven Architecture**
- Phase 3.1: Create event handlers (QuestionExtractionHandler, DocumentExtractionCompletedHandler)
- Phase 3.2: Update event dispatcher
- Phase 3.3: Refactor DocumentProcessingService
- Phase 4.1-4.2: Task logging

**Week 5: API & Routes**
- Phase 5.1-5.4: All API updates
- Create response DTOs
- API documentation

**Week 6: Testing & Deployment**
- Phase 6: Full testing suite
- E2E testing with real PDFs
- Performance testing
- Staging validation
- Production rollout

---

## Architecture Summary

### Directory Structure After Refactor

```
src/
├── entities/
│   ├── question.py          (UPDATED - parent_question_id, questions_group_id)
│   ├── answer.py            (UPDATED - aligned to spec)
│   ├── question_group.py    (NEW)
│   ├── task.py              (UPDATED - progress fields)
│   └── ...
│
├── repos/
│   ├── question_repo.py          (UPDATED - add parent/group queries)
│   ├── answer_repo.py            (NEW)
│   ├── question_group_repo.py    (NEW - cosine search)
│   ├── task_repo.py              (UPDATED - progress methods)
│   └── ...
│
├── services/
│   ├── core/
│   │   ├── question_group_service.py        (NEW - grouping logic)
│   │   ├── question_persistence_service.py  (NEW - main ETL logic)
│   │   ├── question_embedding_service.py    (NEW - embedding wrapper)
│   │   ├── document_extraction_service.py   (EXISTING)
│   │   └── question_extraction_service.py   (EXISTING)
│   │
│   ├── document_service.py        (UNCHANGED)
│   ├── question_service.py        (UNCHANGED)
│   ├── page_service.py            (UNCHANGED)
│   └── document_processing_service.py   (UPDATED - emit events)
│
├── handlers/
│   ├── event_dispatcher.py                  (UPDATED - register new handlers)
│   ├── document_queued_event.py             (EXISTING)
│   ├── page_content_extracted_event.py      (UPDATED - publish next event)
│   ├── question_extraction_handler.py       (NEW - main worker handler)
│   └── document_extraction_completed_handler.py (NEW - completion)
│
├── routes/
│   ├── document_route.py         (UPDATED)
│   ├── question_route.py         (UPDATED)
│   ├── page_route.py             (UPDATED)
│   └── ...
│
├── pipelines/
│   ├── question_extraction.py    (UPDATED - output format)
│   ├── question_embedding.py     (UNCHANGED)
│   └── ...
│
├── dtos/
│   ├── question/res.py           (UPDATED)
│   ├── answer/res.py             (NEW)
│   └── ...
│
├── shared/
│   ├── helpers/
│   │   ├── task_logger.py        (NEW)
│   │   └── ...
│   └── ...
│
└── lib/
    └── db/
        └── migrations/
            ├── m000X_create_question_groups.py
            ├── m000Y_update_questions_schema.py
            ├── m000Z_update_answers_schema.py
            └── ...
```

### Core Service Layer Design

**`src/services/core/`** - Business logic for ETL flow
- QuestionGroupService: Question grouping & vector search
- QuestionPersistenceService: Full persistence workflow
- QuestionEmbeddingService: Embedding generation
- These are used by handlers and can be reused for API endpoints

**`src/handlers/`** - Event-driven handlers
- QuestionExtractionHandler: Main worker - uses QuestionPersistenceService
- DocumentExtractionCompletedHandler: Completion handling
- Handlers orchestrate the flow, core services contain business logic

**`src/routes/`** - HTTP API endpoints
- Use repositories and services directly for query-only operations
- Can use core services for custom workflows

### Key Design Decisions

1. **Vector Similarity Threshold**: Default 0.75 (configurable via settings)
2. **Composite Question Handling**: Parent-child via parent_question_id FK
3. **Answer Storage**: Always use Answer entity (is_correct boolean)
4. **Event-Driven**: Question extraction async via Kafka, OCR+validation sync
5. **Progress Tracking**: per-page with is_final_page flag
6. **Embeddings**: Combined vector (question_text + answers concatenated)

### Performance Considerations

1. **Indexing**:
   - Composite index on `(subject, topic, difficulty)` for group filtering
   - Index on `parent_question_id` for sub-question queries
   - Index on `questions_group_id` for group membership
   
2. **Query Optimization**:
   - Batch cosine search within metadata constraints
   - Query groups by taxonomy before vector search
   - Cache hot question_groups in memory if needed
   
3. **Database**:
   - pgvector extension for similarity search
   - JSONB indexes on task.logs for logging
   - Connection pooling (already in place)
   
4. **Worker**:
   - Process pages sequentially to avoid race conditions
   - Kafka partitioning by document_id ensures ordering
   - Retry logic for transient failures (3 retries max)

### Error Handling & Resilience

1. **Extraction Errors**:
   - If question extraction fails: log error, continue with next page
   - If persistence fails: mark questions as failed, log error
   - Task marked as FAILED only if critical error (can't load page, etc)

2. **Event Errors**:
   - Dead-letter queue for failed events (configured in Kafka)
   - Manual intervention via admin API
   - Detailed error logging in task.logs

3. **Data Consistency**:
   - Foreign key constraints ensure referential integrity
   - Transaction support at service level
   - Idempotent operations where possible

### Backward Compatibility

- Old extracted questions (with inline answers) can coexist
- API supports both formats in queries
- Gradual migration: new questions use Answer entity, old queries still work
- No breaking changes to existing APIs until all data migrated

### Monitoring & Observability

1. **Metrics**:
   - Questions extracted per document
   - Average extraction time per page
   - Vector similarity distribution
   - Question group growth
   - Task failure rate

2. **Logging**:
   - Structured logs in task.logs (JSONB)
   - Error stack traces captured
   - Page-level timing metrics
   - Event correlation IDs

3. **Alerts**:
   - High failure rate alert
   - Slow extraction alert
   - Dead-letter queue growing alert

---

## Success Criteria

- [ ] All questions properly persisted with parent-child relationships
- [ ] Question grouping works via vector similarity search
- [ ] Task progress tracked accurately per page
- [ ] Events properly published and handled
- [ ] Sub-questions maintain parent relationship
- [ ] Answer entities replace inline JSON
- [ ] Integration tests pass
- [ ] Zero data loss during refactor
- [ ] Performance: Full document extraction within SLA (TBD)

---

## Risk Assessment

| Risk | Impact | Mitigation |
|---|---|---|
| Data migration failure | High | Test on staging first, backup database |
| Event ordering issues | Medium | Use Kafka partitioning by document_id |
| Vector search performance | Medium | Add indexes, monitor query performance |
| Schema backward compatibility | Medium | Support both old and new formats during transition |

---

## Notes & References

- **Manual Specification**: `docs/manual/document-etl-flow-vi.md`
- **Current Implementation**: Review in `src/services/document_processing_service.py`
- **Database**: PostgreSQL with pgvector extension
- **Event Bus**: Kafka (existing setup in codebase)
- **LLM Integration**: Existing pipelines work, no changes needed to prompt logic
