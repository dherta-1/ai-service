# Exam Taking Flow - Visual Diagrams

## 1. Complete Exam Attempt Lifecycle

```
USER STARTS EXAM
POST /exam-templates/{template_id}/attempts
Body: { use_existing_instance: false }
              │
   ┌──────────┴──────────┐
   │                     │
   ▼                     ▼
Path A: NEW         Path B: REUSE
Query Eligible Q    Fetch Existing
Apply rules         Validate
Shuffle order       - PENDING/ACTIVE
Shuffle answers     - Only eligible Qs
   │                     │
   └──────────┬──────────┘
              │
              ▼
    CREATE UserTestAttempt
    status = IN_PROGRESS
    started_at = now
              │
              ▼
    GENERATE OPAQUE TOKEN
    - 256-bit random
    - Store SHA-256 hash
    - TTL: 2 hours
              │
              ▼
    BUILD SANITIZED QUESTIONS
    question_token (opaque)
    option_token (opaque)
    NO internal IDs
              │
              ▼
    RETURN TO FRONTEND
    {
      attempt_token,
      questions: [{
        question_token,
        options: [...]
      }]
    }
              │
              ▼
    FRONTEND: EXAM IN PROGRESS
    localStorage:
    - attempt_token
    - answers
    Display: Timer, Questions
              │
         ┌────┴────┐
         │          │
         ▼          ▼
    Continue    Submit
    answer      exam
         │          │
         └────┬─────┘
              │
              ▼
    POST /exam-attempts/{token}/submit
    { answers: [...] }
              │
              ▼
    SCORE ANSWERS (Backend)
    FOR EACH answer:
    - Decode tokens
    - Lookup correct answer
    - Mark is_correct
    - Create UserTestAttemptAnswer
    - Invalidate token
              │
              ▼
    RETURN RESULT
    {
      score: 75.5,
      correct_count: 23,
      details: [...]
    }
              │
              ▼
    SHOW RESULT PAGE
```

---

## 2. Reconnection Flow

```
USER LOSES CONNECTION
(crash, no internet)
         │
         ▼
Check localStorage
- attempt_token?
- answers?
         │
    ┌────┴────┐
    │          │
   YES        NO
    │          │
    ▼          ▼
Reconnect   Start
with token  new attempt
    │
    ▼
GET /exam-attempts/current
X-Attempt-Token: <token>
    │
    ├──────────────────┬──────────┐
    │                  │          │
   200              401          409
   OK              EXPIRED       SUBMITTED
    │                  │          │
    ▼                  ▼          ▼
RECONNECTED      EXPIRED      ALREADY DONE
- SAME instance  - Clear cache - Show result
- SAME questions - Start new   - Cannot retake
- Restore answers - ✓ Answers
  from cache       preserved
- Resume exam    in DB
- ✓ Can submit
```

---

## 3. Question Type Filtering

```
ELIGIBLE TYPES:
✅ multiple_choice
✅ true_false
✅ selection

INELIGIBLE TYPES:
❌ short_answer
❌ essay
❌ composite

FILTERING at 3 Layers:

1. Instance Creation (NEW PATH)
   Query only eligible types
   SELECT * FROM questions
   WHERE question_type IN ('multiple_choice', 
                           'true_false',
                           'selection')
   AND status = 'APPROVED'

2. Existing Instance Validation (REUSE PATH)
   Fetch instance questions
   FOR EACH question:
     IF type NOT IN eligible:
       REJECT instance
     END IF

3. List Available Instances (API)
   GET /exam-templates/{id}/instances
   Return only instances with 100% eligible Qs
```

---

## 4. Token Lifecycle

```
T₀: TOKEN CREATED
│
├─ Generate 256-bit random token
├─ Store SHA-256 hash
├─ Create mapping with 2-hour TTL
│
│◄────── 2 HOURS ───────►│
│                        │
│ VALID WINDOW          │ EXPIRED WINDOW
│ - Token can be used    │ - Token invalid
│ - Multiple calls OK    │ - 401 response
│                        │
│ User submits before    │ User submits after
│ 2-hour limit          │ 2-hour limit
│         │              │         │
│         ▼              │         ▼
│ POST /submit          │ Token lookup fails
│         │              │ Return 401
│ Validate token        │ TOKEN_EXPIRED
│         │              │
│ ✓ Found & active      │ ❌ Expired
│         │              │
│ Score answers         │ User must start
│         │              │ new attempt
│ INVALIDATE TOKEN      │
│ is_invalidated=true   │ (Old answers
│         │              │  preserved in DB)
│ Return 200 Result     │
│         │              │
│ Subsequent calls with │
│ same token → 401      │
│ (prevents double-     │
│  submission)          │
```

---

## 5. Answer Tracking Options

```
OPTION 1: AUTO-SAVE (Recommended)
┌─────────────────────────────────┐
│ User selects answer             │
│ ↓                               │
│ Store in localStorage           │
│ ↓                               │
│ Debounce 30s timer              │
│ ↓ (timer fires)                 │
│ POST /exam-attempts/{}/save     │
│ ↓                               │
│ Backend stores in cache         │
│ ↓                               │
│ Return 204 OK                   │
│ ↓                               │
│ On Submit: Final answers        │
│ POST /exam-attempts/{}/submit   │
│ ↓                               │
│ Create UserTestAttemptAnswer    │
│ ↓                               │
│ Invalidate token                │
│                                 │
│ Benefits:                        │
│ ✅ Answers safe in DB           │
│ ✅ Survive browser crash        │
│ ✅ Debounced (limited calls)    │
│ ✅ True real-time safety        │
└─────────────────────────────────┘

OPTION 2: SAVE ON SUBMIT
┌─────────────────────────────────┐
│ User selects answer             │
│ ↓                               │
│ Store in localStorage only      │
│ ↓                               │
│ Continue exam                   │
│ ↓                               │
│ User submits                    │
│ ↓                               │
│ Restore from localStorage       │
│ ↓                               │
│ POST /submit with all answers   │
│ ↓                               │
│ Create UserTestAttemptAnswer    │
│                                 │
│ Benefits:                        │
│ ✅ Minimal API calls            │
│ ✅ Simple to implement          │
│ ❌ Risk: Cache clear = loss     │
│ ❌ Cannot restore from backend  │
└─────────────────────────────────┘

OPTION 3: HYBRID
┌─────────────────────────────────┐
│ User selects answer             │
│ ↓                               │
│ localStorage + in-memory        │
│ ↓                               │
│ Debounce 30s → POST /save       │
│ ↓                               │
│ Backend stores in cache         │
│ ↓                               │
│ On submit: Final answers        │
│ ↓                               │
│ Create UserTestAttemptAnswer    │
│                                 │
│ Benefits:                        │
│ ✅ Fast UI response             │
│ ✅ Safe backup (backend cache)  │
│ ✅ Moderate API overhead        │
│ ✅ Handles both crashes         │
└─────────────────────────────────┘
```
