# Two-Stage Upload & Processing Flow

## Overview
Split document processing into 2 decoupled stages:
1. **Stage 1 (API)**: User uploads file → S3 + metadata → returns document_id (PENDING)
2. **Stage 2 (API)**: User queues documents → publish extraction events → workers process async

---

## Stage 1: Upload & Create Metadata

### Endpoint
```
POST /documents/upload
Content-Type: multipart/form-data

file: <PDF file>
s3_prefix: "documents"  (optional, default)
```

### Response
```json
{
  "status": 200,
  "message": "Document uploaded successfully",
  "data": {
    "document_id": "UUID",
    "file_id": "UUID",
    "name": "filename.pdf",
    "status": "PENDING"
  }
}
```

### What Happens
- `DocumentService.upload_and_create_metadata()`:
  1. Read uploaded file content
  2. Upload to S3 at `s3://{bucket}/{s3_prefix}/{filename}`
  3. Create `FileMetadata` record with S3 location
  4. Create `Document` record with status=PENDING
  5. Return document_id for use in Stage 2

---

## Stage 2: Queue for Processing

### Endpoint
```
POST /ai/queue
Content-Type: application/json

{
  "document_ids": ["uuid1", "uuid2", ...]
}
```

### Response
```json
{
  "status": 200,
  "message": "Queued 2 documents for extraction",
  "data": {
    "queued": ["uuid1", "uuid2"],
    "errors": []
  }
}
```

### What Happens
- For each document_id:
  1. Validate document exists + status=PENDING
  2. Produce `document_extraction_requested` event (Kafka)
  3. Return success/error per document
- Workers subscribe to event and process async

### Event Payload
```json
{
  "event_type": "document_extraction_requested",
  "document_id": "UUID"
}
```

---

## Processing Flow (Async Workers)

### DocumentExtractionHandler (document-extraction worker)
When `document_extraction_requested` event arrives:

1. **Download from S3**:
   - Fetch FileMetadata by document.file_id
   - Download from S3 → temp directory
   
2. **Extract Pages**:
   - Call `DocumentExtractionService.extract_document()`
   - OCR + validate each page
   - Save Page records
   - Mark document status=PROCESSING

3. **Publish Per-Page Events**:
   - For each extracted page: publish `question_extraction_requested`
   - Include `is_final_page` flag for final page
   - Callback chain continues in next worker

### QuestionExtractionHandler (question-extraction worker)
When `question_extraction_requested` event arrives:

1. **Extract Questions** (4 pipelines):
   - QuestionExtractionPipeline
   - QuestionEmbeddingPipeline
   - QuestionGroupingPipeline
   - QuestionPersistencePipeline

2. **Mark Completion** (if final_page):
   - Update document status=COMPLETED
   - Update task status=COMPLETED
   - Inline completion (no event)

---

## Data Flow

```
POST /documents/upload
  ↓
DocumentService.upload_and_create_metadata()
  ├─ Upload to S3
  ├─ Create FileMetadata (object_key, size, mime_type)
  └─ Create Document (PENDING status)
    ↓ returns document_id
User stores document_id

POST /ai/queue
  ├─ Validate document exists + PENDING
  └─ Produce document_extraction_requested event
    ↓ (Kafka)
DocumentExtractionHandler
  ├─ Download from S3 (via FileMetadata.object_key)
  ├─ Extract pages
  ├─ Publish question_extraction_requested per page
  └─ Update document status=PROCESSING
    ↓ (per page)
QuestionExtractionHandler
  ├─ Extract+embed+group+persist questions
  └─ If final_page: Update document+task status=COMPLETED
```

---

## Key Changes

### Routes

**document_route.py**
- NEW: `POST /documents/upload` — Stage 1 upload + metadata
- Existing: `GET /documents/...` — queries unchanged

**ai_route.py**
- NEW: `POST /ai/queue` — Stage 2 queuing with list of document_ids
- REMOVED: Old `/extract-document` endpoint (was direct sync flow)

### Services

**DocumentService**
- NEW: `upload_and_create_metadata(file, s3_prefix)` — handles Stage 1
- Existing: queries (get_by_id, get_pending, etc.)

**DocumentExtractionHandler**
- Updated: No longer expects `local_pdf_path` in event
- NEW: Downloads from S3 using `FileMetadata.object_key`
- NEW: Creates temp directory + cleanup on finish
- Existing: Page extraction logic unchanged

### Files Required

For S3 interaction, ensure:
- `s3_client.upload_file_bytes(content, bucket, key)` exists
- `s3_client.download_file(bucket, key, local_path)` exists
- These are called via `asyncio.to_thread()` for non-blocking behavior

---

## User Workflow

```python
# 1. Upload documents
response1 = POST /documents/upload (file: exam1.pdf)
doc_id_1 = response1.data.document_id

response2 = POST /documents/upload (file: exam2.pdf)
doc_id_2 = response2.data.document_id

# 2. Queue multiple documents at once
response = POST /ai/queue (document_ids: [doc_id_1, doc_id_2])
# Returns: {queued: [doc_id_1, doc_id_2], errors: []}

# 3. Poll for progress
GET /documents/{doc_id_1}/tasks
# Returns: task.progress, task.processed_pages, task.logs

# 4. Retrieve results
GET /documents/{doc_id_1}/questions?page=1&page_size=10
# Returns: extracted questions with answers
```

---

## Benefits

1. **Decoupling**: Upload ≠ Processing
2. **Batching**: Queue multiple documents at once
3. **Async**: Heavy processing runs in separate worker pods
4. **Resumable**: If worker dies, event remains in Kafka
5. **Efficient**: S3 as buffer (not temp files in API)
6. **Observable**: Document/Task status tracking throughout
