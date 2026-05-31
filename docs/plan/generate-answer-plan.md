# Generate Answer Plan

## Overview

Add an AI-powered answer generation feature that, given a question (and its images), uses an LLM to produce answers and explanations. Supported for all question types including composite (per sub-question).

---

## Backend

### 1. `src/prompts/generate_answer_prompt.py`

Build prompt functions mirroring the pattern in `generate_similar_questions.py`.

```python
def build_generate_answer_prompt(question: dict, image_descriptions: list[str] | None) -> str:
    """Build a prompt to generate an answer for the given question."""

def parse_answer_response(response_text: str) -> dict:
    """Parse LLM JSON response into structured answer dict."""
```

**Prompt output schema** (LLM must return JSON):

- Non-choice types (`essay`, `short_answer`):
  ```json
  { "answer": "...", "explaination": "..." }
  ```
- Choice types (`multiple_choice`, `selection`, `true_false`):
  ```json
  {
    "answers": [
      { "value": "A", "is_correct": true, "explaination": "..." },
      ...
    ]
  }
  ```
- Composite type: an array keyed by `sub_question_order`:
  ```json
  {
    "sub_answers": [
      {
        "sub_question_order": 1,
        "answers": [ ... ]
      },
      ...
    ]
  }
  ```

---

### 2. `src/pipelines/question_answer_gen.py`

Single-question pipeline (no batch needed here).

```python
class QuestionAnswerGenPipeline(BasePipeline):
    """
    Input payload:
      question     dict              Full question dict (text, type, answers, sub_questions, image_list)
      image_blobs  list[bytes]|None  Raw image bytes extracted from S3

    Output:
      generated    dict              Parsed answer structure (see prompt schema above)
    """
```

Steps inside `process()`:
1. If `image_blobs` present, convert to base64 strings for multimodal LLM call.
2. Call `build_generate_answer_prompt(question, image_b64_list)`.
3. Send via `llm_client.generate(prompt, images=...)` (vision-capable call when images present).
4. Call `parse_answer_response(raw)` to get structured dict.
5. Return `{ "generated": structured_dict }`.

---

### 3. `src/services/core/generate_answer_service.py`

```python
class GenerateAnswerService:
    def __init__(self, llm_client, s3_client):
        self._llm = llm_client
        self._s3 = s3_client
        self._question_repo = QuestionRepository()
        self._answer_repo = AnswerRepository()
        self._pipeline = QuestionAnswerGenPipeline(llm_client)

    async def generate_answer(self, question_id: UUID) -> dict:
        """
        1. Fetch question + answers + sub_questions from DB.
        2. If question.image_list, download blobs from S3.
        3. Run pipeline.
        4. Return generated answer dict (not persisted yet).
        """

    async def accept_answer(self, question_id: UUID, payload: dict) -> None:
        """
        Persist the accepted answer:
        - For choice types: update is_correct flags on existing Answer rows.
        - For non-choice: upsert a single Answer row with the text + explaination.
        - For composite: delegate per sub_question.
        """
```

---

### 4. `src/routes/question_route.py`

Add two new endpoints under the existing `router`:

```
POST /questions/{question_id}/generate-answer
  -> calls GenerateAnswerService.generate_answer()
  -> returns { "generated": {...} }

POST /questions/{question_id}/accept-answer
  -> body: the generated (possibly user-edited) answer dict
  -> calls GenerateAnswerService.accept_answer()
  -> returns 200 OK
```

Both endpoints require auth (`get_current_user` dependency), matching the existing pattern.

---

### 5. `src/app.py`

Register `GenerateAnswerService` in the DI container (same pattern as `GenerateSimilarQuestionsService`).

---

## Frontend

### 6. `src/api/question.api.ts` + `src/queries/question.queries.ts`

Add two API calls and mutations:

```ts
// API
generateAnswer: (questionId: string) =>
  api.post(`/questions/${questionId}/generate-answer`).then(r => r.data)

acceptAnswer: (questionId: string, payload: GeneratedAnswerPayload) =>
  api.post(`/questions/${questionId}/accept-answer`, payload).then(r => r.data)

// Queries
export function useGenerateAnswer() { ... }   // mutation
export function useAcceptAnswer(questionId: string) { ... }   // mutation + invalidate detail
```

---

### 7. `src/components/question/question-detail-modal.tsx`

Add a **"Generate Answer"** tab alongside the existing content.

**Tab layout**:
- Tab 1: `details` — existing content (question info, answers, sub-questions, images).
- Tab 2: `generate` — new answer generation panel.

**Generate Answer panel UX**:

| State | UI |
|---|---|
| Idle | "Generate Answer" button with `Sparkles` icon |
| Loading | Spinner + disabled button |
| Result | Structured answer card(s) by question type |
| Accepting | Accept button in loading state |
| Accepted | Toast + detail query invalidated |

**Answer rendering by type**:
- `essay` / `short_answer`: single text card with answer + explanation.
- `multiple_choice` / `selection` / `true_false`: list of answer rows, correct one highlighted green.
- `composite`: accordion/list of sub-question cards, each with their own answer rows.

**Accept action**: sends the `generated` payload to `useAcceptAnswer`; on success shows toast and re-fetches question detail (answers update in the Details tab).

**Component changes**:
- Add `Tabs`, `TabsContent`, `TabsList`, `TabsTrigger` from `@/components/ui/tabs`.
- Add `Sparkles` from `lucide-react`.
- Local state: `generatedAnswer: GeneratedAnswerResponse | null`, `activeTab: 'details' | 'generate'`.

---

## Data Flow

```
User clicks "Generate Answer"
  |
  v
POST /questions/{id}/generate-answer
  |
  +-- Fetch question + sub_questions from DB
  +-- Download image blobs from S3 (if image_list present)
  +-- Build prompt  (QuestionAnswerGenPipeline)
  +-- LLM call  (text + optional images)
  +-- Parse + return structured answer JSON
  |
  v
Frontend renders generated answer by type
  |
User clicks "Accept"
  |
  v
POST /questions/{id}/accept-answer  { generated payload }
  |
  +-- Upsert / update Answer rows in DB
  +-- Return 200
  |
  v
Frontend invalidates question detail cache -> Details tab refreshes with new answers
```

---

---

## DTOs & Types

### Backend: `src/dtos/question/req.py` + `src/dtos/question/res.py`

Add to **`req.py`**:

```python
class GenerateAnswerRequest(BaseModel):
    """No request body needed — question_id comes from URL path."""
    pass


class AcceptAnswerRequest(BaseModel):
    """User-accepted (possibly edited) answer structure."""
    # Schema varies by question type; matches the "generated" shape from service
    # For simplicity, accept a generic dict
    answer: Optional[dict] = None  # { answer, explaination } | { answers: [...] } | { sub_answers: [...] }
```

Add to **`res.py`**:

```python
class GeneratedAnswerResponse(BaseModel):
    """Structured answer from LLM (before persistence)."""
    question_id: UUID
    generated: dict  # { answer, explaination } | { answers: [...] } | { sub_answers: [...] }
    created_at: datetime

    class Config:
        from_attributes = True
```

### Frontend: `src/types/question/question.req.ts` + `src/types/question/question.res.ts`

Add to **`question.req.ts`**:

```ts
export interface GenerateAnswerRequest {
  // No body needed — question_id from URL path
}

export interface AcceptAnswerRequest {
  // User-accepted answer (possibly edited)
  answer?: Record<string, any>  // { answer, explaination } | { answers: [...] } | { sub_answers: [...] }
}
```

Add to **`question.res.ts`**:

```ts
export interface GeneratedAnswerResponse {
  question_id: string
  generated: Record<string, any>  // structured by question type
  created_at: string
}
```

---

## Implementation Order

### Phase 1: Backend Setup

1. **`src/dtos/question/req.py` + `src/dtos/question/res.py`** — add DTO classes above
2. **`src/prompts/generate_answer_prompt.py`** — prompt builder + response parser
3. **`src/pipelines/question_answer_gen.py`** — pipeline wrapping prompt + LLM call
4. **`src/services/core/generate_answer_service.py`** — fetch, S3 download, pipeline, persist
5. **`src/routes/question_route.py`** — two new endpoints
6. **`src/app.py`** — DI registration

### Phase 2: Frontend Setup

7. **`src/types/question/question.req.ts` + `src/types/question/question.res.ts`** — add types above
8. **`src/api/question.api.ts` + `src/queries/question.queries.ts`** — API calls + hooks
9. **`src/components/question/question-detail-modal.tsx`** — tab UI + generate/accept UX
