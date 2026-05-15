# Exam Taking Flow - Implementation Plan Summary

**Date**: 2026-05-13  
**Status**: Ready for Implementation  
**Priority**: High  

---

## Overview

Comprehensive implementation plan for the exam taking feature covering:
- ✅ AttemptTokenMapping schema with security best practices
- ✅ Exam flow supporting both new instance creation and existing instance reuse
- ✅ Complete lifecycle management with reconnection support for unexpected disconnects
- ✅ Frontend and backend implementation details
- ✅ Security considerations and testing strategy

**Total Plan Size**: 1,627 lines + visual diagrams  

---

## Key Deliverables

### 1. Main Plan Document
**File**: `exam-taking-flow.md`

**Sections**:
- Architecture & entity relationships
- AttemptTokenMapping schema (complete with token generation logic)
- Phase 1: Backend API Layer (5 endpoints)
- Phase 2: Backend Services & Repositories
- Phase 3: Frontend Implementation
- Phase 4: Database Migrations (3 migrations)
- Phase 5: Testing Strategy
- Phase 6: Security Considerations
- Phase 7: Implementation Timeline (23-31 days)
- Key design decisions summary
- Complete checklist (22 tasks)

### 2. Visual Diagrams
**File**: `exam-flow-diagram.md`

**Diagrams**:
- Complete exam attempt lifecycle
- Reconnection flow with 3 scenarios
- Question type filtering at 3 layers
- Token lifecycle and expiry
- Answer tracking options (3 approaches)

---

## Critical Design Decisions

### 1. ✅ AttemptTokenMapping Schema

**Purpose**: Securely manage opaque tokens without exposing internal IDs

**Key Features**:
- 256-bit random opaque tokens generated with `secrets.token_urlsafe(32)`
- SHA-256 hash storage (never plaintext)
- 2-hour TTL with indexed `expires_at` for cleanup
- One-time use flag (`is_invalidated`)
- Constant-time token validation to prevent timing attacks

**Implementation**:
```python
# Generate opaque token
token = generate_and_store_token(attempt_id)  # -> "opaque_random_string"

# Validate token
attempt_id = validate_token(token)  # -> lookup hash, check expiry

# Invalidate after submission
invalidate_token(token)  # -> one-time use
```

---

### 2. ✅ Exam Flow with Instance Reuse

**Two Execution Paths**:

#### Path A: Create New Instance (Default)
- Query eligible questions (only: multiple_choice, true_false, selection)
- Apply template distribution rules (difficulty, subject, topic)
- Shuffle question order & answer order
- Store immutable snapshot

#### Path B: Reuse Existing Instance (Optional)
- Request: `POST /exam-attempts` with `existing_instance_id`
- Validation: Instance must have ONLY eligible question types
- Reuse: No re-randomization, exact same layout
- Benefit: Retake, practice, or continue interrupted session

**Question Type Filtering**:
```python
ELIGIBLE_TYPES = {'multiple_choice', 'true_false', 'selection'}

# Applied at 3 layers:
1. Instance creation — only select eligible Qs
2. Existing instance validation — reject if ineligible found
3. Frontend API — only return instances with 100% eligible Qs
```

**API Request**:
```json
{
  "template_id": "uuid",
  "use_existing_instance": false,  // optional
  "existing_instance_id": null     // optional, takes precedence
}
```

---

### 3. ✅ Complete Lifecycle & Reconnection Support

**Scenario A: Disconnect & Reconnect (< 2 hours)**
- User loses connection (crash, offline)
- Frontend stored `attempt_token` in localStorage
- On reconnect: `GET /exam-attempts/current` with token
- Backend returns: **SAME instance + questions**
- Frontend restores: **answers from localStorage**
- **Result: ✅ Answers preserved, can continue exam**

**Scenario B: Disconnect & Reconnect (> 2 hours)**
- Token expired (2-hour hard TTL)
- Backend returns: 401 TOKEN_EXPIRED
- User must start new attempt
- **Result: ✅ Old answers preserved in DB (linked to old attempt_id)**

**Scenario C: Already Submitted**
- User tries to reconnect after submission
- Backend returns: 409 "Exam already submitted"
- Frontend shows result page
- **Result: ✅ Cannot double-submit**

**Answer Tracking** (3 options):
1. **Auto-Save (Recommended)**: Debounced 30s POST to backend
   - Safest: answers stored in DB even if browser crashes
2. **Save on Submit Only**: Minimum API calls
   - Risk: loss if cache cleared
3. **Hybrid**: localStorage + backend batch saves
   - Balance of speed and safety

**No Additional Schema Needed**:
Current schema already supports via:
- `UserTestAttempt.status` (IN_PROGRESS, SUBMITTED, EXPIRED)
- `UserTestAttempt.started_at` / `submitted_at`
- `AttemptTokenMapping.expires_at` (2-hour TTL)
- `AttemptTokenMapping.is_invalidated` (prevents double-submit)

---

## Implementation Breakdown

### Backend (Python/FastAPI)

**Services**:
1. `ExamAttemptService` — Create attempt, get current, submit, result
2. `ExamInstanceService` — Extended with create_from_template + reuse logic
3. `ExamTokenService` — Token generation, validation, invalidation
4. `AnswerScoringService` — Score submitted answers

**Repositories**:
1. `ExamInstanceRepository` — Extended with reuse methods
2. `UserTestAttemptRepository` — Create, get, update attempts

**Entities**:
1. `AttemptTokenMapping` — NEW entity for token security

**API Endpoints**:
1. `POST /api/v1/exam-templates/{template_id}/attempts` — Create attempt
2. `GET /api/v1/exam-templates/{template_id}/instances` — List reusable instances
3. `GET /api/v1/exam-attempts/current` — Get current attempt
4. `POST /api/v1/exam-attempts/{token}/save-answer` — Optional: auto-save
5. `POST /api/v1/exam-attempts/{token}/submit` — Submit exam
6. `GET /api/v1/exam-attempts/{token}/result` — Get result

**Migrations**:
1. `m0003_create_attempt_token_mapping.py` — Token mapping table
2. `m0004_add_attempt_status_fields.py` — Status fields for UserTestAttempt
3. `m0005_link_attempt_to_instance.py` — exam_instance_id FK

### Frontend (TypeScript/React)

**Types**:
- Branded token types for compile-time safety
- ExamQuestion, ExamOption, ExamAttempt, ExamResult DTOs

**State Management** (Zustand):
- Current attempt + token
- Selected answers (Map<QuestionToken, OptionToken>)
- UI state (current question, error, submitting)
- Result data

**Components**:
1. ExamPage — Main exam container
2. ExamQuestionPanel — Question display + answer selection
3. ExamSidebar — Progress + question navigator
4. ExamHeader — Timer countdown
5. ExamResultPage — Result review

**Persistence**:
- localStorage: `attempt_token`, `answers`, `currentQuestionNo`
- Automatic restoration on page reload

---

## Timeline & Effort

| Phase | Task | Days | Dependencies |
|-------|------|------|--------------|
| 1 | Migrations | 1-2 | None |
| 2 | Token service | 2-3 | Migrations |
| 3 | Exam services | 3-4 | Token service |
| 4 | Answer scoring | 2-3 | Exam services |
| 5 | API endpoints | 3-4 | Services |
| 6 | Frontend store | 2-3 | API endpoints |
| 7 | Frontend components | 4-5 | Store |
| 8 | Integration tests | 3-4 | All components |
| 9 | Refinement | 2-3 | Testing |
| **Total** | | **23-31 days** | |

---

## Security Highlights

### Token Security
- ✅ Opaque random tokens (256-bit entropy)
- ✅ Never store plaintext (only SHA-256 hash)
- ✅ 2-hour TTL with indexed expiry
- ✅ One-time use (invalidated after submission)
- ✅ Constant-time comparison to prevent timing attacks

### Answer Security
- ✅ Server-side validation only (never trust client)
- ✅ Never expose correct answers before submission
- ✅ Validate answer options belong to question
- ✅ Audit trail (timestamps, user_id)

### Network Security
- ✅ No internal IDs exposed (only opaque tokens)
- ✅ Generic error messages (don't leak attempt existence)
- ✅ Rate limiting on attempt creation
- ✅ HTTPS/TLS required

---

## Reconnection Flow Benefits

1. **Improved UX**: Users can recover from unexpected disconnects
2. **Answer Preservation**: Answers not lost on browser crash
3. **Same Exam Layout**: Reconnect with identical question order
4. **Clear Error Messaging**: Distinct handling for expired vs. already-submitted
5. **One-Time Prevention**: Token invalidation prevents double-submission

---

## Quick Reference

### Files Created/Modified

**New Files**:
- `src/entities/attempt_token_mapping.py`
- `src/migrations/m0003_create_attempt_token_mapping.py`
- `src/migrations/m0004_add_attempt_status_fields.py`
- `src/migrations/m0005_link_attempt_to_instance.py`
- `src/services/exam_attempt_service.py`
- `src/services/token_service.py`
- `src/services/answer_scoring_service.py`
- `src/services/core/exam_instance_service.py` (extend)
- `src/repos/user_test_attempt_repo.py` (extend)

**Frontend**:
- `src/types/exam.ts`
- `src/stores/exam-store.ts`
- `src/api/exam-api.ts`
- `src/pages/exam-page/index.tsx`
- `src/components/exam/exam-*` (multiple components)
- `src/hooks/useExamTimer.ts`

**Documentation**:
- `docs/plan/exam-taking-flow.md` (main plan, 1,627 lines)
- `docs/plan/exam-flow-diagram.md` (visual diagrams)
- `docs/plan/SUMMARY.md` (this file)

---

## Next Steps

1. **Review & Approve Plan** — Share with team for feedback
2. **Prioritize Tasks** — Start with migrations + token service
3. **Parallel Development** — Backend services + frontend types
4. **Integration Testing** — Test both paths (new + reuse instance)
5. **Security Audit** — Token generation, timing attacks, answer validation
6. **Staging Deployment** — Load testing + user acceptance testing

---

## Related Documents

- `exam-taking-suggested-flow.md` — Original design principles
- `exam-generation-flow.md` — How instances are generated
- `CLAUDE.md` — Architecture & conventions
- `entities/exam_*.py` — Schema definitions
- `repos/exam_*.py` — Data access layer

---

## Questions / Clarifications

- **Token Storage**: Use database (not Redis) for simpler deployment?
  - ✓ Recommended: PostgeSQL with indexed columns is sufficient
  
- **Difficulty Distribution**: How are percentages defined?
  - ✓ In `ExamTemplate.generation_config` as JSON rules
  
- **Auto-Save Performance**: Impact of 30s debounced saves?
  - ✓ Minimal: ~1-2 API calls/min at peak usage
  
- **Reconnection Window**: Why 2 hours?
  - ✓ Balances security (token expiry) vs. user experience
  - Configurable via `expires_in_minutes` parameter

---

## Sign-Off

This plan is comprehensive and ready for implementation. All critical design decisions are documented with rationale, code examples, and visual diagrams.

**Reviewed by**: Claude Code  
**Date**: 2026-05-13  
**Status**: ✅ Ready for Implementation
