# Exam Taking Flow - Implementation Plan

## Overview

This document provides a comprehensive implementation plan for the exam taking feature, following the security and architecture principles outlined in `exam-taking-suggested-flow.md`. The plan covers both Backend and Frontend components.

**Key Principle**: Frontend never sees internal IDs (template_id, instance_id, question_id). All operations use opaque tokens mapped to server-side data.

---

## Architecture & Entity Relationships

```
ExamTemplate
├─ name, subject, generation_config
├─ created_by (User)
└─ instances (ExamInstance)

ExamInstance
├─ exam_test_code (unique)
├─ exam_template (nullable FK)
├─ parent_exam_instance (self-referential for variants)
├─ created_by (User)
├─ status (PENDING, ACTIVE, COMPLETED, CANCELLED)
├─ is_base, is_exported
└─ questions (QuestionExamTest via ExamTestSection)

ExamTestSection
├─ exam_instance (FK)
├─ name, order_index
└─ questions (QuestionExamTest)

QuestionExamTest
├─ question_group, question_id
├─ exam_test_section (FK)
├─ order_count (display order)
└─ answer_order (shuffled indices as JSON)

AttemptTokenMapping (NEW - Token Security)
├─ id (UUID, PK)
├─ token_hash (VARCHAR 255, unique, indexed)
├─ attempt_id (VARCHAR 255, indexed)
├─ created_at (DATETIME, indexed)
├─ expires_at (DATETIME, indexed)
├─ is_invalidated (BOOLEAN, default=false)

UserTestAttempt (Exam Session)
├─ user (FK)
├─ exam_template_id (CharField)
├─ exam_instance_id (FK, nullable)
├─ score (DECIMAL, nullable)
├─ status (SMALLINT: IN_PROGRESS=0, SUBMITTED=1, EXPIRED=2)
├─ started_at (DATETIME)
├─ submitted_at (DATETIME, nullable)
└─ answers (UserTestAttemptAnswer)

UserTestAttemptAnswer
├─ attempt (FK)
├─ question_id (CharField)
├─ selected_answer_id (CharField, nullable)
├─ is_correct (BOOLEAN)
└─ time_spent (BIGINT, milliseconds)

Question
├─ question_text, question_type
├─ difficulty, subject, topic (nullable for sub-questions)
├─ parent_question (self-referential for composite questions)
├─ image_list, vector_embedding
└─ status (PENDING, APPROVED, REJECTED)
```

---

## AttemptTokenMapping Schema (Security & Token Management)

**Table**: `attempt_token_mappings`

**Purpose**: Store opaque token mappings to prevent token value leakage while maintaining the ability to look up attempts.

**Columns**:

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PRIMARY KEY | Unique identifier for the mapping record |
| `token_hash` | VARCHAR(255) | UNIQUE, INDEX | SHA-256 hash of the opaque token (never store plaintext) |
| `attempt_id` | VARCHAR(255) | INDEX | Reference to UserTestAttempt.id (internal use only) |
| `created_at` | DATETIME | INDEX | When token was generated |
| `expires_at` | DATETIME | INDEX | Token expiration time (2 hours from creation) |
| `is_invalidated` | BOOLEAN | DEFAULT=false | One-time invalidation after submission |

**Indexes**:
- `UNIQUE(token_hash)` — Fast token lookup, prevents duplicates
- `INDEX(expires_at)` — Efficient cleanup of expired tokens
- `INDEX(attempt_id)` — Reverse lookup from attempt to token (if needed)

**Entity Definition** (`src/entities/attempt_token_mapping.py`):

```python
from peewee import CharField, BooleanField, DateTimeField
from src.shared.base.base_entity import BaseEntity
from datetime import datetime, timedelta

class AttemptTokenMapping(BaseEntity):
    token_hash = CharField(max_length=255, unique=True, index=True)
    attempt_id = CharField(max_length=255, index=True)
    created_at = DateTimeField(default=datetime.utcnow, index=True)
    expires_at = DateTimeField(index=True)
    is_invalidated = BooleanField(default=False)

    class Meta:
        table_name = "attempt_token_mappings"
        indexes = (
            (('token_hash',), True),  # unique
            (('expires_at',), False),
            (('attempt_id',), False),
        )

    @classmethod
    def create_token_mapping(cls, attempt_id: str, token_hash: str, expires_in_minutes: int = 120):
        """Create a new token mapping"""
        expires_at = datetime.utcnow() + timedelta(minutes=expires_in_minutes)
        return cls.create(
            token_hash=token_hash,
            attempt_id=attempt_id,
            expires_at=expires_at
        )

    def is_expired(self) -> bool:
        """Check if token has expired"""
        return datetime.utcnow() > self.expires_at

    def is_valid(self) -> bool:
        """Check if token is still usable"""
        return not self.is_invalidated and not self.is_expired()
```

**Token Generation & Storage Logic**:

```python
import secrets
import hashlib

def generate_and_store_token(attempt_id: str, expires_in_minutes: int = 120) -> str:
    """
    Generate opaque random token and store hash mapping
    
    Returns: plain opaque token (sent to frontend)
    """
    # Generate 256-bit (32-byte) random token
    token = secrets.token_urlsafe(32)
    
    # Store only hash of token
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    
    AttemptTokenMapping.create_token_mapping(
        attempt_id=attempt_id,
        token_hash=token_hash,
        expires_in_minutes=expires_in_minutes
    )
    
    return token

def validate_token(token: str) -> Optional[str]:
    """
    Validate token and return attempt_id
    
    Returns: attempt_id if valid, None if invalid/expired
    """
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    
    try:
        mapping = AttemptTokenMapping.get(
            AttemptTokenMapping.token_hash == token_hash
        )
        
        if not mapping.is_valid():
            return None
        
        return mapping.attempt_id
    except AttemptTokenMapping.DoesNotExist:
        return None

def invalidate_token(token: str) -> bool:
    """
    Invalidate token (one-time use after submission)
    
    Returns: True if invalidated, False if not found
    """
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    
    result = (
        AttemptTokenMapping.update(is_invalidated=True)
        .where(AttemptTokenMapping.token_hash == token_hash)
        .execute()
    )
    
    return result > 0
```

---

## Phase 1: Backend API Layer

### 1.1 Create Exam Attempt Endpoints

**Endpoint**: `POST /api/v1/exam-templates/{template_id}/attempts`

**Request**:
```json
{
  "template_id": "uuid",
  "use_existing_instance": false,
  "existing_instance_id": null
}
```

**Note**: 
- `use_existing_instance` (boolean, optional, default=false) — Use a pre-existing exam instance instead of generating new
- `existing_instance_id` (UUID, optional) — ID of existing exam instance to reuse. Must belong to this template. If provided, `use_existing_instance` is ignored and treated as true.

**Response** (Success - 201):
```json
{
  "attempt_token": "opaque_token_here",
  "attempt_id": "internal_uuid",
  "exam_instance_id": "internal_uuid",
  "expires_at": "2026-05-13T14:30:00Z",
  "total_questions": 30,
  "time_limit_minutes": 60,
  "started_at": "2026-05-13T13:30:00Z",
  "questions": [
    {
      "question_no": 1,
      "question_token": "opaque_q_token_1",
      "content": "What is...?",
      "question_type": "multiple_choice",
      "has_image": false,
      "options": [
        {
          "option_token": "opaque_opt_token_1",
          "content": "Option A"
        },
        {
          "option_token": "opaque_opt_token_2",
          "content": "Option B"
        }
      ]
    }
  ]
}
```

**Process Flow**:

**Path A: Create New ExamInstance (Default)**
1. Validate user is authenticated
2. Fetch ExamTemplate by template_id
3. Validate template exists and is active
4. Query eligible questions:
   - Filter by template rules (difficulty distribution, subject, topic)
   - **ONLY include questions with question_type in: `multiple_choice`, `true_false`, `selection`**
   - Exclude composite/essay questions
5. Select & shuffle questions per template rules
6. Create ExamInstance record
7. Create ExamTestSection record (if needed for organizing)
8. Create QuestionExamTest records for each question:
   - Store display order
   - Store shuffled answer order as JSON (e.g., `[2,0,3,1]`)
   - Pre-compute correct answer indices for scoring

**Path B: Reuse Existing ExamInstance**
1. Validate user is authenticated
2. Fetch ExamTemplate by template_id
3. Validate template exists and is active
4. Fetch existing ExamInstance:
   - Must belong to the same template
   - Must have status = PENDING or ACTIVE
   - Validate it contains ONLY choice questions (multiple_choice, true_false, selection)
5. **Reuse the snapshot** — don't re-randomize
6. Create new UserTestAttempt linked to this instance

**Unified Steps (Both Paths)**
7. Create UserTestAttempt record:
   - user_id = authenticated user
   - exam_template_id = template_id
   - exam_instance_id = instance (new or existing)
   - status = IN_PROGRESS
   - started_at = now
8. Generate opaque attempt_token:
   - Generate 256-bit random token
   - Store SHA-256 hash in AttemptTokenMapping
   - Map to attempt_id with 2-hour expiry
9. Build sanitized question list (no internal IDs, only tokens):
   - For each QuestionExamTest in instance:
     - Generate opaque question_token for this attempt
     - Fetch question content + answers
     - Generate opaque option_tokens for each answer option (in shuffled order)
     - Return only these tokens, never the original IDs
10. Return opaque data to FE

**Database Operations (New Path)**:
- INSERT ExamInstance
- INSERT ExamTestSection
- INSERT QuestionExamTest (for each question)
- INSERT UserTestAttempt
- INSERT AttemptTokenMapping

**Database Operations (Reuse Path)**:
- SELECT ExamInstance + verify
- INSERT UserTestAttempt
- INSERT AttemptTokenMapping

**Validation Rules**:
```python
# Question filtering for instance creation
ELIGIBLE_QUESTION_TYPES = {'multiple_choice', 'true_false', 'selection'}

# Check before returning to FE
if any(q.question_type not in ELIGIBLE_QUESTION_TYPES 
       for q in instance.questions()):
    raise ValueError("Instance contains ineligible question types")
```

---

### 1.1.5 List Available Instances for Reuse (Optional)

**Endpoint**: `GET /api/v1/exam-templates/{template_id}/instances`

**Purpose**: Retrieve list of existing exam instances that can be reused (for UI to show "Use Previous Instance" option)

**Query Parameters**:
- `reusable_only` (boolean, optional, default=true) — Filter to only PENDING/ACTIVE instances with eligible question types

**Response** (200 OK):
```json
{
  "instances": [
    {
      "instance_id": "internal_uuid",
      "exam_test_code": "EXAM_ABC123",
      "total_questions": 30,
      "created_at": "2026-05-10T10:00:00Z",
      "status": "PENDING",
      "is_base": true
    }
  ],
  "count": 1
}
```

**Process Flow**:
1. Validate user is authenticated
2. Fetch ExamTemplate by template_id
3. Query ExamInstance records:
   - WHERE exam_template == template_id
   - WHERE status IN (PENDING, ACTIVE)
   - WHERE is_base == true (only base instances)
4. Validate each instance has only eligible question types
5. Return sanitized list (no internal question IDs)

**Use Case**: 
- FE shows dropdown: "Start New Exam" vs "Retake Previous Instance"
- User can retry the exact same set of questions
- Useful for practice exams or retakes

---

### 1.2 Get Current Attempt Endpoint

**Endpoint**: `GET /api/v1/exam-attempts/current`

**Request Headers**:
```
Authorization: Bearer {auth_token}
X-Attempt-Token: {opaque_attempt_token}
```

**Response** (200 OK):
```json
{
  "attempt_token": "opaque_token_here",
  "status": "in_progress",
  "started_at": "2026-05-13T13:30:00Z",
  "expires_at": "2026-05-13T14:30:00Z",
  "time_elapsed_ms": 120000,
  "total_questions": 30,
  "answered_count": 5,
  "questions": [
    {
      "question_no": 1,
      "question_token": "opaque_q_token_1",
      "content": "What is...?",
      "question_type": "multiple_choice",
      "has_image": false,
      "options": [
        {
          "option_token": "opaque_opt_token_1",
          "content": "Option A"
        }
      ]
    }
  ]
}
```

**Process Flow**:
1. Decode attempt_token from header
2. Lookup token in AttemptTokenMapping
3. Fetch UserTestAttempt + related data
4. Validate attempt is not expired or already submitted
5. Rebuild question list from cache (to maintain order consistency)
6. Return opaque data

---

### 1.3 Submit Exam Endpoint

**Endpoint**: `POST /api/v1/exam-attempts/{attempt_token}/submit`

**Request**:
```json
{
  "answers": [
    {
      "question_token": "opaque_q_token_1",
      "selected_option_token": "opaque_opt_token_2"
    },
    {
      "question_token": "opaque_q_token_2",
      "selected_option_token": null
    }
  ]
}
```

**Response** (200 OK):
```json
{
  "attempt_id": "internal_uuid",
  "status": "submitted",
  "submitted_at": "2026-05-13T14:25:00Z",
  "score": 75.5,
  "total_questions": 30,
  "correct_count": 23,
  "result_available": true
}
```

**Process Flow**:
1. Decode attempt_token + lookup in mapping
2. Fetch UserTestAttempt (validate NOT already submitted)
3. Validate answers not after time limit
4. For each answer:
   - Decode question_token → question_id
   - Decode option_token → answer_id
   - Lookup correct answer from Question/Answer schema
   - Determine is_correct
   - Create UserTestAttemptAnswer record
5. Calculate score (sum of correct answers / total × 100)
6. Update UserTestAttempt: score, status=SUBMITTED, submitted_at
7. Delete/invalidate attempt_token (one-time submission)
8. Return result

**Database Operations**:
- INSERT UserTestAttemptAnswer (batch)
- UPDATE UserTestAttempt
- DELETE/UPDATE AttemptTokenMapping

---

### 1.4 Get Exam Result Endpoint

**Endpoint**: `GET /api/v1/exam-attempts/{attempt_token}/result`

**Response** (200 OK):
```json
{
  "attempt_id": "internal_uuid",
  "score": 75.5,
  "total_questions": 30,
  "correct_count": 23,
  "submitted_at": "2026-05-13T14:25:00Z",
  "review_available": true,
  "details": [
    {
      "question_no": 1,
      "content": "What is...?",
      "question_type": "multiple_choice",
      "user_answer": "Option B",
      "is_correct": true,
      "explanation": null
    }
  ]
}
```

**Process Flow**:
1. Decode attempt_token + lookup
2. Fetch UserTestAttempt + UserTestAttemptAnswer
3. Rebuild question/answer details
4. Return sanitized result (no option tokens, show correct answer)

---

## Exam Attempt Lifecycle & Reconnection Flow

### Lifecycle States

```
                          ┌─────────────┐
                          │   PENDING   │
                          └──────┬──────┘
                                 │ POST /attempts
                                 │ (create attempt)
                                 ▼
                          ┌─────────────┐
                          │ IN_PROGRESS │◄─────────────┐
                          └──────┬──────┘              │
                                 │                     │
                    ┌────────────┬┴────────────┐       │
                    │            │             │       │
        Time Out    │            │   Submit    │       │
        (2hr)       │     GET    │            │       │
        expires     │   /current │            │       │
        token       │            │            │       │
                    ▼            │            ▼       │
               EXPIRED       (refresh)    ┌────────────┼──┐
               ──────        token        │ SUBMITTED  │  │
                                         └────────────┴──┘
                                                     │
                                                     │
                                        User reconnects
                                        with same token
                                        (if not yet expired)
```

### Scenario 1: User Reconnects During IN_PROGRESS (Unexpected Disconnect)

**User Action**: 
- Connection lost during exam
- Closes browser / loses internet
- User reopens exam page within 2 hours

**Reconnection Flow**:

1. **Frontend Recovery**:
   - Store `attempt_token` in localStorage immediately after exam starts
   - On page reload/reconnect, check for stored attempt_token
   - If token exists, call `GET /exam-attempts/current` with the token

2. **Backend Validation** (`GET /exam-attempts/current`):
   ```python
   attempt_token = request.headers['X-Attempt-Token']
   attempt_id = validate_token(attempt_token)  # returns None if expired
   
   if not attempt_id:
       return 401 {"error": "Session expired"}
   
   attempt = UserTestAttempt.get_by_id(attempt_id)
   if attempt.status != IN_PROGRESS:
       return 409 {"error": "Attempt already submitted"}
   
   # Return the SAME instance + questions to resume
   return current_questions_with_tokens(attempt)
   ```

3. **Database State**:
   - `UserTestAttempt` record remains unchanged
   - No new records created
   - `AttemptTokenMapping` is still valid (2-hour TTL)
   - **Answers saved so far are NOT lost** — FE can display them

4. **Answer Tracking**:
   - Frontend should also store `answers` in localStorage
   - On reconnect, restore the answers from localStorage
   - Display the question the user was on
   - Continue where they left off

5. **Important**: 
   - ✅ **Answers already saved are preserved** (not lost)
   - ✅ **Same exam instance** — no re-randomization
   - ✅ **Same token** — can use stored attempt_token
   - ❌ **Cannot change answers after disconnect** — they're already submitted to backend
   - Timer resets from current time (time doesn't accumulate)

---

### Scenario 2: User Reconnects After 2-Hour Token Expiry

**User Action**:
- Exam token expired (exceeds 2-hour limit)
- Tries to reconnect after 2+ hours

**Reconnection Flow**:

1. **Frontend Try to Restore**:
   - Stored attempt_token exists
   - Call `GET /exam-attempts/current` with expired token

2. **Backend Response**:
   ```
   401 Unauthorized
   {
     "error": "Session expired",
     "code": "TOKEN_EXPIRED",
     "message": "Your exam session has expired. Please start a new exam."
   }
   ```

3. **Frontend Action**:
   - Clear localStorage
   - Redirect to exam list
   - User must start a new attempt
   - **Previous answers are preserved** in database (linked to old attempt_id)

---

### Scenario 3: User Submits Exam Then Wants to Reconnect

**User Action**:
- Already submitted exam
- Tries to use the same token to continue

**Reconnection Flow**:

1. **Backend Validation**:
   ```python
   attempt = UserTestAttempt.get_by_id(attempt_id)
   
   if attempt.status == SUBMITTED:
       return 409 {
           "error": "Exam already submitted",
           "score": attempt.score,
           "submitted_at": attempt.submitted_at
       }
   ```

2. **Frontend Action**:
   - Display result page instead of exam page
   - Show score and review

---

### Answer Tracking During Session

**When Answers Are Recorded**:

**Option 1: Auto-Save Answers (Recommended)**
- Every time user selects an answer, also POST to backend
- Endpoint: `POST /exam-attempts/{attempt_token}/save-answer` (new, optional)
- Request: `{ "question_token": "...", "selected_option_token": "..." }`
- **Pros**: Answers are safe in DB even if user disconnects
- **Cons**: More API calls

**Option 2: Save Only on Submit**
- Answers stored in localStorage only
- On submit, send all answers at once
- On reconnect, restore from localStorage
- **Pros**: Fewer API calls
- **Cons**: User loses answers if they clear cache

**Recommended Approach**: Hybrid
- Auto-save answers to localStorage (instant)
- Batch save to backend every 30 seconds (debounced)
- On submit, send final answer list + backend saves to UserTestAttemptAnswer
- On reconnect, FE can display answers from localStorage or backend

**Implementation**:
```python
# Optional endpoint for incremental saves
@router.post("/exam-attempts/{attempt_token}/save-answer")
async def save_answer(
    attempt_token: str,
    question_token: str,
    selected_option_token: Optional[str]
):
    """
    Optionally save answer as user selects it (for safety)
    Not required for main submission flow
    """
    attempt_id = validate_token(attempt_token)
    if not attempt_id:
        return 401 {"error": "Session expired"}
    
    # Store in cache or temp table for recovery
    # No need to insert into UserTestAttemptAnswer yet
    return 204  # No content
```

---

### Database Schema Changes for Lifecycle Support

The schema already supports this through:

1. **UserTestAttempt.status** — Tracks IN_PROGRESS vs SUBMITTED
2. **UserTestAttempt.started_at** — When attempt began
3. **UserTestAttempt.submitted_at** — When answer submitted (null if in progress)
4. **UserTestAttemptAnswer** — Stores final answers (created only on submit)
5. **AttemptTokenMapping.expires_at** — 2-hour hard limit
6. **AttemptTokenMapping.is_invalidated** — Marks token as used (after submit)

**No additional schema needed** — current design supports full lifecycle.

---

## Phase 2: Backend Service & Repository Layer

### 2.1 ExamAttemptService

**Location**: `src/services/exam_attempt_service.py`

**Methods**:

```python
class ExamAttemptService:
    """Manages exam attempt creation and submission"""

    async def create_attempt(
        self,
        user_id: str,
        template_id: str
    ) -> ExamAttemptDTO:
        """
        1. Fetch template, validate active
        2. Create instance (randomize questions + shuffle)
        3. Create UserTestAttempt record
        4. Generate opaque token
        5. Return sanitized attempt DTO
        """
        pass

    async def get_current_attempt(
        self,
        attempt_token: str,
        user_id: str
    ) -> ExamAttemptDTO:
        """Retrieve ongoing attempt by token"""
        pass

    async def submit_attempt(
        self,
        attempt_token: str,
        answers: List[SubmittedAnswer],
        user_id: str
    ) -> ExamResultDTO:
        """
        1. Validate token & user
        2. Score answers
        3. Save attempt answers
        4. Calculate total score
        5. Update attempt status
        6. Invalidate token
        """
        pass

    async def get_attempt_result(
        self,
        attempt_token: str,
        user_id: str
    ) -> ExamResultDTO:
        """Fetch submitted attempt result"""
        pass
```

---

### 2.2 ExamInstanceService

**Location**: `src/services/core/exam_instance_service.py` (extend existing)

**Constants**:
```python
ELIGIBLE_QUESTION_TYPES = {'multiple_choice', 'true_false', 'selection'}
```

**New Methods**:

```python
class ExamInstanceService:
    """Manages instance creation, reuse, and question randomization"""

    async def create_from_template(
        self,
        template_id: str,
        user_id: str,
        use_existing_instance: bool = False,
        existing_instance_id: Optional[str] = None
    ) -> ExamInstance:
        """
        Create new instance or reuse existing one
        
        Args:
            template_id: Template to use
            user_id: User creating the attempt
            use_existing_instance: Whether to reuse existing instance
            existing_instance_id: Specific instance to reuse (takes precedence)
        
        Returns: ExamInstance (new or reused)
        """
        template = ExamTemplate.get_by_id(template_id)
        if not template:
            raise TemplateNotFoundError(template_id)
        
        # Path B: Reuse existing instance
        if use_existing_instance or existing_instance_id:
            return await self._get_and_validate_existing_instance(
                existing_instance_id or template_id
            )
        
        # Path A: Create new instance
        return await self._create_new_instance(template, user_id)

    async def _create_new_instance(
        self,
        template: ExamTemplate,
        user_id: str
    ) -> ExamInstance:
        """
        Create new randomized exam instance from template
        
        1. Query eligible questions (only multiple_choice, true_false, selection)
        2. Apply template selection rules (difficulty, subject, topic)
        3. Shuffle question order
        4. Create instance + questions with shuffled answers
        """
        # 1. Query eligible questions
        eligible_questions = self._query_eligible_questions(
            template.subject,
            rules=parse_generation_config(template.generation_config)
        )
        
        if not eligible_questions:
            raise NoEligibleQuestionsError(template.id)
        
        # 2. Select questions per rules
        selected_questions = self._select_by_distribution(
            eligible_questions,
            rules=parse_generation_config(template.generation_config)
        )
        
        # 3. Shuffle order
        import random
        shuffled = random.shuffle(selected_questions)
        
        # 4. Create instance
        instance = ExamInstance.create(
            exam_template=template,
            created_by_id=user_id,
            exam_test_code=self._generate_unique_code(),
            is_base=True,
            status=ExamInstanceStatus.PENDING
        )
        
        # 5. Create section + questions with shuffled answers
        section = ExamTestSection.create(
            exam_instance=instance,
            name="Questions",
            order_index=0
        )
        
        for order, question in enumerate(shuffled):
            # Shuffle answer order
            answer_indices = self._get_shuffled_answer_order(question)
            
            QuestionExamTest.create(
                exam_instance=instance,
                question_group=question.questions_group,
                question_id=question.id,
                exam_test_section=section,
                order_count=order,
                answer_order=json.dumps(answer_indices)
            )
        
        return instance

    async def _get_and_validate_existing_instance(
        self,
        instance_id: str
    ) -> ExamInstance:
        """
        Fetch existing instance and validate it's eligible
        
        Validation:
        - Must exist
        - Must have status PENDING or ACTIVE
        - All questions must be eligible types (multiple_choice, true_false, selection)
        """
        instance = ExamInstance.get_by_id(instance_id)
        if not instance:
            raise InstanceNotFoundError(instance_id)
        
        # Validate instance questions
        for qet in instance.questions():  # QuestionExamTest
            question = Question.get_by_id(qet.question_id)
            if question.question_type not in ELIGIBLE_QUESTION_TYPES:
                raise IneligibleQuestionInInstanceError(
                    f"Question {qet.question_id} has type {question.question_type}"
                )
        
        return instance

    def _query_eligible_questions(
        self,
        subject: str,
        rules: Dict
    ) -> List[Question]:
        """
        Query questions matching:
        - Subject code
        - Question type in (multiple_choice, true_false, selection)
        - Status = APPROVED
        - Difficulty distribution per rules
        """
        query = (
            Question.select()
            .where(
                (Question.subject == subject)
                & (Question.question_type.in_(ELIGIBLE_QUESTION_TYPES))
                & (Question.status == QuestionStatus.APPROVED)
                & (Question.parent_question.is_null(True))  # Only top-level questions
            )
        )
        return list(query)

    def _select_by_distribution(
        self,
        questions: List[Question],
        rules: Dict
    ) -> List[Question]:
        """
        Select questions matching difficulty distribution
        e.g., rules = {"easy": 10, "medium": 15, "hard": 5}
        """
        result = []
        
        for difficulty, count in rules.get('difficulties', {}).items():
            matching = [q for q in questions if q.difficulty == difficulty]
            if len(matching) < count:
                raise InsufficientQuestionsError(
                    f"Only {len(matching)} questions found for difficulty {difficulty}, "
                    f"but {count} required"
                )
            # Random sample without replacement
            selected = random.sample(matching, count)
            result.extend(selected)
        
        return result

    def _get_shuffled_answer_order(self, question: Question) -> List[int]:
        """
        Shuffle answer option indices
        
        Returns: e.g., [2, 0, 3, 1] — means display answer 2 first, then 0, then 3, then 1
        """
        answers = Answer.select().where(Answer.question == question.id)
        indices = list(range(len(answers)))
        random.shuffle(indices)
        return indices

    def _generate_unique_code(self) -> str:
        """Generate unique exam_test_code"""
        import uuid
        return f"exam_{uuid.uuid4().hex[:8].upper()}"

    async def get_questions_with_tokens(
        self,
        instance_id: str,
        attempt_id: str
    ) -> List[ExamQuestionDTO]:
        """
        Fetch questions for instance and generate opaque tokens
        
        For each question:
        - Generate unique question_token
        - Fetch answers in shuffled order
        - Generate unique option_token for each answer
        - Return sanitized question DTO (no internal IDs)
        """
        instance = ExamInstance.get_by_id(instance_id)
        result = []
        
        for qet in instance.questions():
            question = Question.get_by_id(qet.question_id)
            question_token = self.token_service.generate_question_token(
                question.id, attempt_id
            )
            
            # Get answers in shuffled order
            answers = Answer.select().where(Answer.question == question.id)
            shuffled_answers = self._apply_shuffle(
                list(answers),
                json.loads(qet.answer_order)
            )
            
            options = []
            for answer in shuffled_answers:
                option_token = self.token_service.generate_option_token(
                    answer.id, question.id, attempt_id
                )
                options.append(ExamOption(
                    option_token=option_token,
                    content=answer.value
                ))
            
            result.append(ExamQuestionDTO(
                question_no=qet.order_count + 1,
                question_token=question_token,
                content=question.question_text,
                question_type=question.question_type,
                has_image=bool(question.image_list),
                image_url=question.image_list[0] if question.image_list else None,
                options=options
            ))
        
        return result

    def _apply_shuffle(self, items: List, order: List[int]) -> List:
        """Apply shuffle order to items"""
        return [items[i] for i in order]
```

---

### 2.3 Token Management Service

**Location**: `src/services/token_service.py` (new)

```python
class ExamTokenService:
    """Manages opaque tokens for exams"""

    async def generate_attempt_token(
        self,
        attempt_id: str,
        expires_in_minutes: int = 120
    ) -> str:
        """Generate random opaque token + store hash mapping"""
        pass

    async def validate_and_decode_token(
        self,
        token: str
    ) -> str:  # returns attempt_id
        """Lookup token hash, validate expiry, return attempt_id"""
        pass

    async def invalidate_token(self, token: str) -> bool:
        """Delete token mapping (one-time submission)"""
        pass

    async def generate_question_token(
        self,
        question_id: str,
        attempt_id: str
    ) -> str:
        """Generate opaque token for a question within attempt"""
        pass

    async def generate_option_token(
        self,
        answer_id: str,
        question_id: str,
        attempt_id: str
    ) -> str:
        """Generate opaque token for an answer option"""
        pass

    async def decode_question_token(
        self,
        token: str
    ) -> str:  # returns question_id
        """Decode question token"""
        pass

    async def decode_option_token(
        self,
        token: str
    ) -> str:  # returns answer_id
        """Decode option token"""
        pass
```

**Token Strategy**:
- Use **opaque random tokens** (256-bit entropy)
- Store token_hash (SHA-256) → actual_id mapping in Redis
- 2-hour TTL for attempt tokens
- 30-day TTL for historical mapping
- One-time tokens invalidated after use

---

### 2.4 Answer Scoring Service

**Location**: `src/services/answer_scoring_service.py` (new)

```python
class AnswerScoringService:
    """Scores submitted answers"""

    async def score_answers(
        self,
        attempt_id: str,
        submitted_answers: List[SubmittedAnswer]
    ) -> Tuple[float, List[ScoredAnswer]]:
        """
        For each answer:
        1. Lookup question from attempt
        2. Fetch correct answer(s) from Question/Answer schema
        3. Compare with submission
        4. Mark is_correct
        5. Calculate score percentage
        """
        pass

    def _is_answer_correct(
        self,
        answer_id: str,
        question_type: str,
        correct_answer_ids: List[str]
    ) -> bool:
        """Determine correctness based on question type"""
        pass
```

---

### 2.5 ExamInstanceRepository Extensions

**Location**: `src/repos/exam_instance_repo.py` (extend existing)

```python
class ExamInstanceRepository:
    """Data access for exam instances"""

    async def create_with_questions(
        self,
        template_id: str,
        question_ids: List[str],
        shuffled_answer_orders: Dict[str, List[int]],
        created_by_id: str
    ) -> ExamInstance:
        """Create instance + QuestionExamTest records in transaction"""
        pass

    async def get_by_code(self, exam_test_code: str) -> ExamInstance:
        """Lookup instance by unique code"""
        pass

    async def get_questions_for_instance(
        self,
        instance_id: str
    ) -> List[QuestionExamTest]:
        """Fetch all questions for an instance"""
        pass
```

---

### 2.6 UserTestAttemptRepository

**Location**: `src/repos/user_test_attempt_repo.py` (extend existing)

```python
class UserTestAttemptRepository:
    """Data access for user exam attempts"""

    async def create(
        self,
        user_id: str,
        exam_template_id: str,
        exam_instance_id: str
    ) -> UserTestAttempt:
        """Create new attempt record"""
        pass

    async def get_by_id(self, attempt_id: str) -> UserTestAttempt:
        """Fetch attempt by ID"""
        pass

    async def update_after_submission(
        self,
        attempt_id: str,
        score: float,
        submitted_at: datetime
    ) -> UserTestAttempt:
        """Update attempt with score and submission time"""
        pass

    async def save_answers(
        self,
        attempt_id: str,
        answers: List[UserTestAttemptAnswer]
    ) -> None:
        """Batch insert attempt answers"""
        pass
```

---

## Phase 3: Frontend Implementation

### 3.1 Data Types & Models

**Location**: `@/frontend/src/types/exam.ts`

```typescript
// Opaque token types (not actual values, just strings)
type AttemptToken = string & { readonly __brand: 'AttemptToken' };
type QuestionToken = string & { readonly __brand: 'QuestionToken' };
type OptionToken = string & { readonly __brand: 'OptionToken' };

interface ExamQuestion {
  question_no: number;
  question_token: QuestionToken;
  content: string;
  question_type: 'multiple_choice' | 'true_false' | 'short_answer' | 'essay' | 'selection';
  has_image: boolean;
  image_url?: string;
  options: ExamOption[];
}

interface ExamOption {
  option_token: OptionToken;
  content: string;
}

interface ExamAttempt {
  attempt_token: AttemptToken;
  attempt_id: string;  // only for internal tracking
  expires_at: string;
  total_questions: number;
  time_limit_minutes: number;
  started_at: string;
  questions: ExamQuestion[];
}

interface SubmittedAnswer {
  question_token: QuestionToken;
  selected_option_token?: OptionToken;
}

interface ExamResult {
  attempt_id: string;
  score: number;
  total_questions: number;
  correct_count: number;
  submitted_at: string;
  details: ExamResultDetail[];
}

interface ExamResultDetail {
  question_no: number;
  content: string;
  question_type: string;
  user_answer: string;
  is_correct: boolean;
  explanation?: string;
}
```

---

### 3.2 State Management (Zustand)

**Location**: `@/frontend/src/stores/exam-store.ts`

```typescript
interface ExamState {
  // Current attempt
  currentAttempt: ExamAttempt | null;
  attemptToken: AttemptToken | null;
  
  // Answers
  answers: Map<QuestionToken, OptionToken | null>;
  timeSpent: Map<QuestionToken, number>;  // milliseconds
  
  // UI State
  currentQuestionNo: number;
  isSubmitting: boolean;
  error: string | null;
  
  // Result
  result: ExamResult | null;

  // Actions
  startAttempt: (templateId: string) => Promise<void>;
  getCurrentAttempt: () => Promise<void>;
  selectAnswer: (questionToken: QuestionToken, optionToken: OptionToken) => void;
  clearAnswer: (questionToken: QuestionToken) => void;
  submitExam: () => Promise<void>;
  getResult: () => Promise<void>;
  resetState: () => void;
}
```

---

### 3.3 API Client

**Location**: `@/frontend/src/api/exam-api.ts`

```typescript
class ExamAPI {
  async startExam(templateId: string): Promise<ExamAttempt> {
    const response = await fetch(`/api/v1/exam-templates/${templateId}/attempts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    return response.json();
  }

  async getCurrentAttempt(attemptToken: AttemptToken): Promise<ExamAttempt> {
    const response = await fetch('/api/v1/exam-attempts/current', {
      headers: { 'X-Attempt-Token': attemptToken },
    });
    return response.json();
  }

  async submitExam(
    attemptToken: AttemptToken,
    answers: SubmittedAnswer[]
  ): Promise<ExamResult> {
    const response = await fetch(
      `/api/v1/exam-attempts/${attemptToken}/submit`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ answers }),
      }
    );
    return response.json();
  }

  async getResult(attemptToken: AttemptToken): Promise<ExamResult> {
    const response = await fetch(
      `/api/v1/exam-attempts/${attemptToken}/result`,
      {
        headers: { 'X-Attempt-Token': attemptToken },
      }
    );
    return response.json();
  }
}
```

---

## Phase 4: Database Migrations & Schema Changes

### 4.1 Create AttemptTokenMapping Table

**Location**: `src/migrations/m0003_create_attempt_token_mapping.py`

```python
def migrate(migrator, database, fake=False):
    """Create mapping for opaque exam tokens"""
    migrator.create_table(
        'attempt_token_mappings',
        {
            'id': UUIDField(primary_key=True, default=uuid.uuid4),
            'token_hash': CharField(max_length=255, unique=True, index=True),
            'attempt_id': CharField(max_length=255),
            'created_at': DateTimeField(default=datetime.utcnow),
            'expires_at': DateTimeField(index=True),
            'is_invalidated': BooleanField(default=False),
        }
    )
```

### 4.2 Update UserTestAttempt Status

**Location**: `src/migrations/m0004_add_attempt_status_fields.py`

```python
def migrate(migrator, database, fake=False):
    """Add timing and status fields to UserTestAttempt"""
    migrator.add_fields(
        'user_test_attempts',
        {
            'status': SmallIntegerField(default=0),  # IN_PROGRESS=0, SUBMITTED=1, EXPIRED=2
            'started_at': DateTimeField(default=datetime.utcnow),
            'submitted_at': DateTimeField(null=True),
        }
    )
```

### 4.3 Add ExamInstance Reference to UserTestAttempt

**Location**: `src/migrations/m0005_link_attempt_to_instance.py`

```python
def migrate(migrator, database, fake=False):
    """Link UserTestAttempt to ExamInstance"""
    migrator.add_fields(
        'user_test_attempts',
        {
            'exam_instance_id': ForeignKeyField(
                'ExamInstance',
                column_name='exam_instance_id',
                null=True
            ),
        }
    )
```

---

## Phase 5: Testing Strategy

### 5.1 Backend Tests

```python
class TestExamAttemptService:
    @pytest.mark.asyncio
    async def test_create_attempt_success(self):
        """Test successful attempt creation"""
        pass

    @pytest.mark.asyncio
    async def test_submit_attempt_calculates_score(self):
        """Test answer scoring"""
        pass
```

### 5.2 Frontend Tests

```typescript
describe('ExamStore', () => {
  it('should start exam and load questions', async () => {
    pass
  });

  it('should select answer for question', () => {
    pass
  });

  it('should submit exam and get result', async () => {
    pass
  });
});
```

---

## Phase 6: Security Considerations

### 6.1 Token Security
- ✅ Use opaque random tokens (256-bit entropy)
- ✅ Store token hash (SHA-256) in database, never plaintext
- ✅ Validate token expiry on every API call
- ✅ Invalidate token after submission (one-time use)
- ✅ Never expose attempt_id, instance_id, question_id in responses

### 6.2 Answer Security
- ✅ Compare answers server-side (never client-side)
- ✅ Never send correct answer to client before submission
- ✅ Validate answer options belong to the question
- ✅ Log answer submission with timestamp (audit trail)

### 6.3 Timing Attack Prevention
- ✅ Fixed response time for token validation (use constant-time comparison)
- ✅ Don't leak attempt existence through error messages
- ✅ Return generic 401 for invalid tokens

### 6.4 Rate Limiting
- ✅ Limit attempt creation: 10 per user per day
- ✅ Limit submission attempts: 1 per attempt
- ✅ Implement CAPTCHA for repeated failures

---

## Phase 7: Implementation Timeline

| Phase | Task | Duration | Dependencies |
|-------|------|----------|--------------|
| 1 | Database migrations | 1-2 days | None |
| 2 | Token service | 2-3 days | DB migrations |
| 3 | Exam attempt service | 3-4 days | Token service |
| 4 | Answer scoring service | 2-3 days | Exam attempt service |
| 5 | REST API endpoints | 3-4 days | Services |
| 6 | Frontend store | 2-3 days | API endpoints |
| 7 | Frontend components | 4-5 days | Store |
| 8 | Integration testing | 3-4 days | All components |
| 9 | Bug fixes & optimization | 2-3 days | Testing |
| **Total** | | **23-31 days** | |

---

---

## Key Design Decisions Summary

### 1. AttemptTokenMapping Schema

✅ **Implemented** — See [AttemptTokenMapping Schema](#attempttokenmapping-schema-security--token-management) section.

**Purpose**: Securely store opaque token mappings without exposing internal IDs.

**Storage**: 
- `token_hash` (SHA-256) — Indexed, unique
- `attempt_id` — FK reference, indexed
- `expires_at` — 2-hour TTL, indexed for cleanup
- `is_invalidated` — One-time use flag

**Usage**: 
- Frontend receives `attempt_token` (256-bit random, opaque string)
- Backend never exposes the token value; only stores SHA-256 hash
- Every API call validates token hash, checks expiry, verifies not invalidated

---

### 2. Exam Taking Flow with Instance Reuse

✅ **Two Paths** — See [1.1 Create Exam Attempt Endpoints](#11-create-exam-attempt-endpoints) section.

**Path A: Create New Instance** (default)
- Random selection of questions per template rules
- Shuffle question order
- Shuffle answer order for each question
- Store snapshot in DB (immutable for this attempt)

**Path B: Reuse Existing Instance** (optional)
- Frontend sends `use_existing_instance: true` or `existing_instance_id: "..."`
- Backend validates instance:
  - Belongs to same template
  - Status = PENDING or ACTIVE
  - **ALL questions have eligible types** (multiple_choice, true_false, selection)
  - NO composite/essay questions allowed
- Backend reuses exact same question order + answer shuffling
- No re-randomization

**Question Type Filtering**:
```python
ELIGIBLE_TYPES = {'multiple_choice', 'true_false', 'selection'}

# Applied at:
1. Instance creation — only select eligible questions
2. Existing instance validation — reject if any ineligible question found
3. Frontend — only return instances with 100% eligible questions
```

**Benefit**: Users can retake same exam, practice with same questions, or continue interrupted session with identical layout.

---

### 3. Exam Lifecycle & Reconnection Support

✅ **Full Lifecycle** — See [Exam Attempt Lifecycle & Reconnection Flow](#exam-attempt-lifecycle--reconnection-flow) section.

**Scenario A: Disconnect & Reconnect (Within 2 Hours)**
- User loses connection during exam
- Stored `attempt_token` in localStorage
- Calls `GET /exam-attempts/current` with token
- Backend returns SAME instance + questions
- Frontend restores answers from localStorage
- **Answers are preserved** — not lost
- Can continue exam from where left off
- Timer resets from current time

**Scenario B: Disconnect & Reconnect (After 2+ Hours)**
- `attempt_token` expired
- Backend returns 401 TOKEN_EXPIRED
- Frontend clears localStorage
- User must start new attempt
- **Previous answers are preserved** in DB (linked to old attempt_id)

**Scenario C: Already Submitted, Try to Reconnect**
- `attempt.status == SUBMITTED`
- Backend returns 409 "Exam already submitted"
- Frontend shows result page instead

**Answer Tracking**:
- **Option 1 (Recommended)**: Auto-save to backend every 30s (debounced)
  - Safe in DB even if browser crashes
  - Incremental saves via optional `POST /exam-attempts/{token}/save-answer`
- **Option 2**: Save only on submit
  - Fewer API calls
  - Loss on cache clear
- **Option 3 (Hybrid)**: localStorage + backend batch saves
  - Best of both worlds

**No Additional Schema Needed**: Current design supports full lifecycle via:
- `UserTestAttempt.status` (IN_PROGRESS, SUBMITTED, EXPIRED)
- `UserTestAttempt.started_at` / `submitted_at`
- `AttemptTokenMapping.expires_at` (2-hour hard limit)
- `AttemptTokenMapping.is_invalidated` (one-time use)
- `UserTestAttemptAnswer` (created only on final submit)

---

## Checklist

- [ ] AttemptTokenMapping entity created (`src/entities/attempt_token_mapping.py`)
- [ ] AttemptTokenMapping migration created (`m0003_create_attempt_token_mapping.py`)
- [ ] UserTestAttempt migration for status/timing fields (`m0004_...`)
- [ ] ExamTokenService implemented (generate, validate, invalidate tokens)
- [ ] ExamInstanceService extended (create new + reuse existing + question filtering)
- [ ] ExamAttemptService implemented (create, get, submit, result)
- [ ] AnswerScoringService implemented
- [ ] API endpoints implemented (create attempt, get current, submit, result)
- [ ] Optional API: list reusable instances
- [ ] Optional API: auto-save answers
- [ ] Frontend types created (with branded token types)
- [ ] Frontend store (Zustand) with lifecycle support
- [ ] Frontend components (exam page, question panel, sidebar, timer, result)
- [ ] localStorage persistence for answers + token
- [ ] Integration tests for all scenarios
- [ ] E2E tests for reconnection flows
- [ ] Security audit (token generation, answer validation, timing attacks)
- [ ] Documentation updated
- [ ] Deployed to staging
- [ ] Load testing completed

---

## References

- `exam-taking-suggested-flow.md` — Security & design principles
- `CLAUDE.md` — Architecture & conventions
- `entities/` — Current schema definitions
- `exam_instance.py` — ExamInstance entity
- `exam_test_section.py` — ExamTestSection entity  
- `question_exam_test.py` — QuestionExamTest entity
- `user_test_attempt.py` — UserTestAttempt entity
- `user_test_attempt_answer.py` — UserTestAttemptAnswer entity
