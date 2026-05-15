# Exam Taking Flow - Implementation Plan

Complete implementation plan for exam taking feature with support for instance reuse, disconnection recovery, and opaque token security.

## 📋 Documents

### 1. **SUMMARY.md** ← START HERE
Quick reference with key decisions, implementation breakdown, timeline, and next steps.
- 2-page executive summary
- Perfect for team briefings
- Links to detailed sections

### 2. **exam-taking-flow.md**
Comprehensive 40-page technical specification covering:

**Architecture**:
- Entity relationships with new AttemptTokenMapping schema
- Complete data flow diagrams

**Phase 1: Backend API Layer**
- 5 REST endpoints with full request/response schemas
- Detailed process flow for each endpoint
- Database operations for new and reuse paths

**Phase 2: Backend Services**
- ExamAttemptService (create, get, submit, result)
- ExamInstanceService (new + reuse + filtering)
- ExamTokenService (256-bit tokens, SHA-256 hashing)
- AnswerScoringService (answer validation)
- Repository extensions

**Phase 3: Frontend Implementation**
- TypeScript types with branded token types
- Zustand store with lifecycle support
- API client
- 5 React components
- Custom hooks
- localStorage persistence

**Phase 4-7: Migrations, Tests, Security, Timeline**
- 3 database migrations
- Testing strategy (backend + frontend)
- Security audit checklist
- 23-31 day implementation timeline

**Key Decisions Summary**
- AttemptTokenMapping schema explained
- Exam flow with instance reuse (Path A + Path B)
- Complete lifecycle & reconnection support

### 3. **exam-flow-diagram.md**
Visual ASCII diagrams for quick understanding:

1. **Complete Exam Attempt Lifecycle** — Full state machine from start to result
2. **Reconnection Flow** — 3 scenarios (< 2h, > 2h, already submitted)
3. **Question Type Filtering** — 3-layer filtering strategy
4. **Token Lifecycle** — 2-hour TTL and invalidation
5. **Answer Tracking Options** — 3 approaches (auto-save, submit-only, hybrid)

Each diagram includes:
- State transitions
- Data flow
- API endpoints
- Storage/persistence
- Error handling

---

## 🎯 Key Features

### ✅ 1. AttemptTokenMapping Schema
- 256-bit random opaque tokens
- SHA-256 hash storage (never plaintext)
- 2-hour TTL with indexed expiry
- One-time use flag for double-submission prevention
- Constant-time validation

### ✅ 2. Instance Reuse
- **Path A**: Create new instance (default)
  - Random selection per template rules
  - Shuffle questions & answers
  - Immutable snapshot
  
- **Path B**: Reuse existing instance (optional)
  - No re-randomization
  - Same layout for retakes/practice
  - Validate only eligible question types

### ✅ 3. Reconnection Support
- **Scenario A**: Disconnect < 2 hours → Reconnect with same token
  - SAME questions, ANSWERS preserved, can continue
  
- **Scenario B**: Disconnect > 2 hours → Token expired
  - Start new attempt, old answers in DB
  
- **Scenario C**: Already submitted → Cannot retake
  - Show result page, clear token

---

## 🔒 Security Highlights

| Feature | Implementation |
|---------|-----------------|
| Token Generation | 256-bit cryptographic random (secrets.token_urlsafe) |
| Token Storage | SHA-256 hash only (never plaintext) |
| Token Expiry | 2-hour TTL with indexed cleanup |
| Token Validation | Constant-time comparison (prevents timing attacks) |
| One-Time Use | Invalidated after submission |
| Answer Security | Server-side validation only |
| No ID Exposure | Frontend only receives opaque tokens |
| Error Messages | Generic (don't leak attempt existence) |
| Rate Limiting | 10 attempts/user/day |

---

## 📊 Implementation Timeline

| Phase | Task | Days | Status |
|-------|------|------|--------|
| 1 | Database migrations | 1-2 | 📝 Planned |
| 2 | Token service | 2-3 | 📝 Planned |
| 3 | Exam services | 3-4 | 📝 Planned |
| 4 | Answer scoring | 2-3 | 📝 Planned |
| 5 | API endpoints | 3-4 | 📝 Planned |
| 6 | Frontend store | 2-3 | 📝 Planned |
| 7 | Frontend components | 4-5 | 📝 Planned |
| 8 | Integration tests | 3-4 | 📝 Planned |
| 9 | Refinement & audit | 2-3 | 📝 Planned |
| **Total** | | **23-31 days** | |

---

## 📁 Files to Create/Modify

### Backend (Python)
```
src/
├── entities/
│   └── attempt_token_mapping.py (NEW)
├── services/
│   ├── exam_attempt_service.py (NEW)
│   ├── token_service.py (NEW)
│   ├── answer_scoring_service.py (NEW)
│   └── core/exam_instance_service.py (EXTEND)
├── repos/
│   ├── user_test_attempt_repo.py (EXTEND)
│   └── exam_instance_repo.py (EXTEND)
├── handlers/
│   └── exam_attempt_handler.py (NEW)
└── migrations/
    ├── m0003_create_attempt_token_mapping.py (NEW)
    ├── m0004_add_attempt_status_fields.py (NEW)
    └── m0005_link_attempt_to_instance.py (NEW)
```

### Frontend (TypeScript/React)
```
src/
├── types/
│   └── exam.ts (NEW)
├── api/
│   └── exam-api.ts (NEW)
├── stores/
│   └── exam-store.ts (NEW)
├── hooks/
│   └── useExamTimer.ts (NEW)
├── pages/
│   ├── exam-page/index.tsx (NEW)
│   └── exam-result-page/index.tsx (NEW)
└── components/exam/
    ├── exam-header.tsx (NEW)
    ├── exam-question-panel.tsx (NEW)
    ├── exam-sidebar.tsx (NEW)
    ├── option-button.tsx (NEW)
    └── result-item.tsx (NEW)
```

---

## 🚀 Quick Start

1. **Read SUMMARY.md** (5 min)
   - Overview of all 3 key features
   - Implementation breakdown
   - Timeline & effort

2. **Review exam-taking-flow.md** (30 min)
   - Focus on sections 1.1 (API flow) and 2.2 (services)
   - Check AttemptTokenMapping schema
   - Understand instance reuse paths

3. **Check exam-flow-diagram.md** (10 min)
   - Visual confirmation of flows
   - Quick reference for state machines

4. **Start with Phase 1-2** (Backend first)
   - Migrations (easy foundation)
   - Token service (enables everything else)
   - Exam services (business logic)

5. **Then Phase 3** (Frontend)
   - Types and store (state management)
   - Components (UI)
   - Integration tests

---

## 🔧 API Endpoints Summary

### Create Exam Attempt
```
POST /api/v1/exam-templates/{template_id}/attempts
Body: { use_existing_instance?, existing_instance_id? }
Returns: { attempt_token, questions, expires_at, ... }
```

### List Reusable Instances
```
GET /api/v1/exam-templates/{template_id}/instances?reusable_only=true
Returns: { instances: [...], count: N }
```

### Get Current Attempt
```
GET /api/v1/exam-attempts/current
Header: X-Attempt-Token
Returns: { attempt_token, questions, status, ... }
```

### Save Answer (Optional)
```
POST /api/v1/exam-attempts/{attempt_token}/save-answer
Body: { question_token, selected_option_token }
Returns: 204 No Content
```

### Submit Exam
```
POST /api/v1/exam-attempts/{attempt_token}/submit
Body: { answers: [{ question_token, selected_option_token }, ...] }
Returns: { score, correct_count, submitted_at, ... }
```

### Get Result
```
GET /api/v1/exam-attempts/{attempt_token}/result
Header: X-Attempt-Token
Returns: { score, correct_count, details: [...] }
```

---

## 📋 Checklist

**Entities & Migrations**
- [ ] Create AttemptTokenMapping entity
- [ ] Create 3 migrations (token, status, linking)
- [ ] Run migrations in dev/staging

**Backend Services**
- [ ] Implement ExamTokenService
- [ ] Implement ExamInstanceService (with reuse)
- [ ] Implement ExamAttemptService
- [ ] Implement AnswerScoringService
- [ ] Extend repositories

**Backend API**
- [ ] Implement all 6 endpoints
- [ ] Add request/response validation
- [ ] Add error handling
- [ ] Add rate limiting

**Frontend Types & State**
- [ ] Create exam.ts types (with branded tokens)
- [ ] Create exam-store.ts (Zustand)
- [ ] Implement localStorage persistence
- [ ] Implement auto-restore on page load

**Frontend Components**
- [ ] Create 5+ components
- [ ] Implement timer countdown
- [ ] Implement answer selection
- [ ] Implement progress sidebar
- [ ] Implement result display

**Testing**
- [ ] Backend unit tests (services)
- [ ] Backend integration tests (flows)
- [ ] Backend E2E tests (reconnection)
- [ ] Frontend unit tests (store)
- [ ] Frontend component tests

**Security & Deployment**
- [ ] Security audit (token generation, timing attacks)
- [ ] Load testing
- [ ] Staging deployment
- [ ] User acceptance testing
- [ ] Production deployment

---

## 🤝 Related Documentation

- **exam-taking-suggested-flow.md** — Original design principles & security guidelines
- **exam-generation-flow.md** — How exam instances are created
- **CLAUDE.md** — Project architecture & conventions
- **entities/** — All database schema definitions
- **repos/** — Repository implementations

---

## ❓ FAQ

**Q: Why not reuse tokens?**  
A: One-time tokens prevent accidental double-submission and are more secure. Users can retry with new token.

**Q: Why 2-hour TTL?**  
A: Balances security (prevents old tokens) and UX (typical exam length < 2h). Configurable.

**Q: What if instance has mixed question types?**  
A: Rejected during reuse validation. Only 100% eligible instances accepted.

**Q: How do answers survive disconnects?**  
A: Stored in localStorage on FE + optional auto-save to backend. Even if browser crashes, answers in DB.

**Q: Can user retry after submission?**  
A: No. Token invalidated after first submission. Must start new attempt with new token.

---

## 📞 Support

For questions or clarifications, refer to:
1. **SUMMARY.md** — High-level overview
2. **exam-taking-flow.md** — Detailed specifications
3. **exam-flow-diagram.md** — Visual reference
4. **CLAUDE.md** — Architecture guidelines

Last Updated: **2026-05-13**  
Status: ✅ **Ready for Implementation**
