# Auth + User Module Implementation Plan

## 1. Overview

This plan adds a complete authentication and user management system to the existing FastAPI microservice. The existing `User` entity, empty stub files (`auth_service.py`, `user_service.py`, `auth_route.py`, `user_route.py`, `auth_deps.py`), and migration baseline (through `m0007`) are already present. The work involves:

- Completing the `User` entity with a `password_hash` field and fixing the `is_email_verified` type.
- Implementing `AuthService` with JWT issuance/validation, bcrypt password hashing, email verification, and password reset flows.
- Implementing `UserService` and `UserRepository` for admin CRUD.
- Filling in `auth_deps.py` with FastAPI dependency functions.
- Adding FK columns (`uploaded_by`, `created_by`, `from_user`) to four entities via migrations `m0008`–`m0010`.
- Refactoring service list/paginated methods to accept `user_id` + `is_admin` scope parameters.
- Wiring everything into `app.py`.

---

## 2. Key Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Password hashing | `passlib[bcrypt]` (`CryptContext`) | Standard, well-maintained |
| JWT library | `python-jose[cryptography]` | Supports HS256/RS256 |
| Access token TTL | 15 minutes | Short-lived for security |
| Refresh token TTL | 7 days | Stored in Redis, enables server-side invalidation |
| Refresh token storage | Redis with TTL | Key pattern: `auth:refresh:{user_id}:{jti}` |
| Email verification token | Signed JWT, 24h TTL | Stateless, no extra DB column needed |
| Password reset token | Signed JWT, 1h TTL | Same rationale |
| Email sending | `fastapi-mail` (SMTP) via `BackgroundTasks` | Non-blocking |
| Role enum | `user` and `admin` only | Simplified from student/teacher/admin |
| JWT config keys | `JWT_SECRET_KEY`, `JWT_ALGORITHM` env vars | Added to `Settings` |

---

## 3. Build Order (Phases)

### Phase 1 — Foundation: Settings, Constants, Entity Update

**`src/settings.py`** — ADD fields:
```python
# JWT
jwt_secret_key: str = Field(default="change-me-in-production", env="JWT_SECRET_KEY")
jwt_algorithm: str = Field(default="HS256", env="JWT_ALGORITHM")
access_token_expire_minutes: int = Field(default=15, env="ACCESS_TOKEN_EXPIRE_MINUTES")
refresh_token_expire_days: int = Field(default=7, env="REFRESH_TOKEN_EXPIRE_DAYS")

# Email / SMTP
smtp_host: str = Field(default="smtp.gmail.com", env="SMTP_HOST")
smtp_port: int = Field(default=587, env="SMTP_PORT")
smtp_username: Optional[str] = Field(default=None, env="SMTP_USERNAME")
smtp_password: Optional[str] = Field(default=None, env="SMTP_PASSWORD")
smtp_from_email: str = Field(default="noreply@example.com", env="SMTP_FROM_EMAIL")
smtp_from_name: str = Field(default="AI Service", env="SMTP_FROM_NAME")
frontend_url: str = Field(default="http://localhost:3000", env="FRONTEND_URL")
```

**`src/shared/constants/user.py`** — REPLACE `Role` enum:
```python
from enum import Enum

class Role(str, Enum):
    user = "user"
    admin = "admin"
```

**`src/entities/user.py`** — UPDATE to:
```python
from peewee import CharField, DateTimeField, BooleanField
from src.shared.constants.user import Role
from src.shared.base.base_entity import BaseEntity

class User(BaseEntity):
    name = CharField(max_length=255)
    email = CharField(max_length=255, unique=True)
    password_hash = CharField(max_length=255, null=True)
    role = CharField(max_length=50, default=Role.user.value)
    is_email_verified = BooleanField(default=False)
    email_verification_sent_at = DateTimeField(null=True)
    last_login_at = DateTimeField(null=True)

    class Meta:
        table_name = "users"
```
Note: `reset_password_token` is dropped — new flow uses stateless JWT tokens.

---

### Phase 2 — User Repository and User Service

**`src/repos/user_repo.py`** — CREATE:
```python
from typing import Optional, List, Tuple
from src.entities.user import User
from src.shared.base.base_repo import BaseRepo

class UserRepository(BaseRepo[User]):
    def __init__(self):
        super().__init__(User)

    def get_by_email(self, email: str) -> Optional[User]:
        return User.get_or_none(User.email == email)

    def get_all_paginated(self, page: int, page_size: int) -> Tuple[List[User], int]:
        offset = (page - 1) * page_size
        query = User.select()
        return list(query.offset(offset).limit(page_size)), query.count()
```

**`src/services/user_service.py`** — IMPLEMENT with methods:
- `list_users(page, page_size) -> (List[User], int)`
- `get_by_id(user_id: UUID) -> Optional[User]`
- `get_by_email(email: str) -> Optional[User]`
- `update_user(user_id: UUID, **kwargs) -> User`
- `delete_user(user_id: UUID) -> bool`
- `set_password_hash(user_id: UUID, hashed: str) -> User`
- `mark_email_verified(user_id: UUID) -> User`
- `update_last_login(user_id: UUID) -> User`

---

### Phase 3 — Auth Service

**`src/services/auth_service.py`** — IMPLEMENT

Constructor:
```python
def __init__(self, user_service: UserService, cache: CacheClient, settings: Settings):
```

Private helpers:
- `_hash_password(plain: str) -> str` — bcrypt via `CryptContext`
- `_verify_password(plain: str, hashed: str) -> bool`
- `_create_access_token(user_id: str, role: str) -> str` — payload: `{sub, role, type="access", jti, exp}`
- `_create_refresh_token(user_id: str) -> tuple[str, str]` — returns `(token, jti)`, stores in Redis `auth:refresh:{user_id}:{jti}` with TTL
- `_create_email_token(user_id: str, purpose: Literal["verify","reset"]) -> str` — verify=24h, reset=1h
- `_decode_token(token: str) -> dict` — raises `UnauthorizedException` on invalid/expired
- `_send_email(to, subject, body_html, background_tasks)` — via `fastapi-mail`

Public methods:
```python
async def register(self, name: str, email: str, password: str) -> User
    # Raises ConflictException if email taken

async def send_verification_email(self, user: User, background_tasks: BackgroundTasks) -> None
    # Link: {frontend_url}/verify-email?token={token}

async def verify_email(self, token: str) -> User
    # Decodes token (purpose="verify"), sets is_email_verified=True

async def login(self, email: str, password: str) -> dict
    # Returns {access_token, refresh_token, token_type: "bearer"}
    # Raises ForbiddenException if is_email_verified is False

async def refresh_tokens(self, refresh_token: str) -> dict
    # Validates jti in Redis, rotates token pair
    # Raises UnauthorizedException on reuse (token already deleted)

async def logout(self, refresh_token: str) -> None
    # Deletes refresh token from Redis

async def forgot_password(self, email: str, background_tasks: BackgroundTasks) -> None
    # Always returns success (no user enumeration)
    # Link: {frontend_url}/reset-password?token={token}

async def reset_password(self, token: str, new_password: str) -> None
    # Decodes token (purpose="reset"), updates password_hash
```

---

### Phase 4 — Auth Dependencies

**`src/shared/auth_deps.py`** — IMPLEMENT:

```python
from fastapi import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional

security = HTTPBearer(auto_error=False)

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> User:
    # Validate Bearer token, decode JWT (type="access"), fetch user
    # Raises UnauthorizedException if missing/invalid

async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    # Raises ForbiddenException if role != "admin"

async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[User]:
    # Returns None if no/invalid token; returns User if valid
```

---

### Phase 5 — DTOs

**`src/dtos/auth/req.py`**:
```python
class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class RefreshRequest(BaseModel):
    refresh_token: str

class VerifyEmailRequest(BaseModel):
    token: str

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)
```

**`src/dtos/auth/res.py`**:
```python
class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
```

**`src/dtos/user/req.py`**:
```python
class UpdateUserRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    role: Optional[str] = Field(default=None, pattern="^(user|admin)$")
```

**`src/dtos/user/res.py`**:
```python
class UserResponse(BaseModel):
    id: UUID
    name: str
    email: str
    role: str
    is_email_verified: bool
    last_login_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
```

---

### Phase 6 — Auth Route

**`src/routes/auth_route.py`** — IMPLEMENT:

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/auth/register` | None | Register, send verification email |
| POST | `/auth/login` | None | Login, return token pair |
| POST | `/auth/refresh` | None | Rotate refresh token |
| POST | `/auth/verify-email` | None | Confirm email with token |
| POST | `/auth/forgot-password` | None | Send reset email |
| POST | `/auth/reset-password` | None | Reset password with token |
| POST | `/auth/logout` | None | Invalidate refresh token |
| GET | `/auth/me` | `get_current_user` | Get current user profile |

---

### Phase 7 — User Route (Admin Only)

**`src/routes/user_route.py`** — IMPLEMENT:

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/users` | `require_admin` | List all users (paginated) |
| GET | `/users/{user_id}` | `require_admin` | Get user by ID |
| PUT | `/users/{user_id}` | `require_admin` | Update name/role |
| DELETE | `/users/{user_id}` | `require_admin` | Delete user |

---

### Phase 8 — Wire Into app.py

**`src/app.py`** — MODIFY:
1. Add `User` to `bind_models_to_database()` models list (currently missing — pre-existing bug)
2. Register in DI container after registering `cache`:
   ```python
   user_service = UserService()
   container.register_singleton("user_service", user_service)
   auth_service = AuthService(user_service=user_service, cache=cache, settings=settings)
   container.register_singleton("auth_service", auth_service)
   ```
3. Mount routes:
   ```python
   app.include_router(auth_router, prefix="/auth", tags=["auth"])
   app.include_router(user_router, prefix="/users", tags=["users"])
   ```

---

## 4. Data Migration Plan

### m0008 — Update users table schema

File: `src/lib/db/migrations/m0008_update_users_schema.py`

```sql
-- up()
ALTER TABLE users
  ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255),
  ADD COLUMN IF NOT EXISTS email_verification_sent_at TIMESTAMP,
  ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMP;

ALTER TABLE users
  ALTER COLUMN is_email_verified TYPE BOOLEAN
  USING (is_email_verified = 'true');

ALTER TABLE users
  ALTER COLUMN is_email_verified SET DEFAULT FALSE;

ALTER TABLE users
  DROP COLUMN IF EXISTS reset_password_token;

-- down()
ALTER TABLE users
  ADD COLUMN IF NOT EXISTS reset_password_token VARCHAR(50);

ALTER TABLE users
  ALTER COLUMN is_email_verified TYPE VARCHAR(5)
  USING (CASE WHEN is_email_verified THEN 'true' ELSE 'false' END);

ALTER TABLE users
  DROP COLUMN IF EXISTS password_hash,
  DROP COLUMN IF EXISTS email_verification_sent_at,
  DROP COLUMN IF EXISTS last_login_at;
```

### m0009 — Migrate role values

File: `src/lib/db/migrations/m0009_migrate_role_values.py`

```sql
-- up()
UPDATE users SET role = 'user' WHERE role IN ('student', 'teacher');

-- down()
UPDATE users SET role = 'student' WHERE role = 'user';
```

### m0010 — Add user FK columns to entities

File: `src/lib/db/migrations/m0010_add_user_fk_columns.py`

```sql
-- up()
ALTER TABLE documents
  ADD COLUMN IF NOT EXISTS uploaded_by_id UUID REFERENCES users(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS documents_uploaded_by_id_idx ON documents(uploaded_by_id);

ALTER TABLE exam_templates
  ADD COLUMN IF NOT EXISTS created_by_id UUID REFERENCES users(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS exam_templates_created_by_id_idx ON exam_templates(created_by_id);

ALTER TABLE exam_instances
  ADD COLUMN IF NOT EXISTS created_by_id UUID REFERENCES users(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS exam_instances_created_by_id_idx ON exam_instances(created_by_id);

ALTER TABLE questions_groups
  ADD COLUMN IF NOT EXISTS from_user_id UUID REFERENCES users(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS questions_groups_from_user_id_idx ON questions_groups(from_user_id);

-- down()
ALTER TABLE documents DROP COLUMN IF EXISTS uploaded_by_id;
ALTER TABLE exam_templates DROP COLUMN IF EXISTS created_by_id;
ALTER TABLE exam_instances DROP COLUMN IF EXISTS created_by_id;
ALTER TABLE questions_groups DROP COLUMN IF EXISTS from_user_id;
```

---

## 5. Entity FK Field Updates (after migrations)

**`src/entities/document.py`** — ADD:
```python
from src.entities.user import User
uploaded_by = ForeignKeyField(User, column_name="uploaded_by_id", backref="documents", null=True, index=True)
```

**`src/entities/exam_template.py`** — ADD:
```python
from src.entities.user import User
created_by = ForeignKeyField(User, column_name="created_by_id", backref="exam_templates", null=True, index=True)
```

**`src/entities/exam_instance.py`** — ADD:
```python
from src.entities.user import User
created_by = ForeignKeyField(User, column_name="created_by_id", backref="exam_instances", null=True, index=True)
```

**`src/entities/question_group.py`** — ADD:
```python
from src.entities.user import User
from_user = ForeignKeyField(User, column_name="from_user_id", backref="question_groups", null=True, index=True)
```

---

## 6. Scoped Logic Refactoring (Comprehensive User Data Isolation)

### Overview of Scope Changes

All mutable and retrieval operations must be scoped by the current user's identity:
- **Non-admin users**: can only see/modify their own documents, templates, exams, and question groups created during their document processing
- **Admin users**: can see/modify all data
- **Public/unauthenticated endpoints**: only allowed for auth routes

### Repository changes

Add `get_all_paginated_scoped(page, page_size, user_id=None)` and `find_by_metadata_scoped(...)` to:

**`src/repos/document_repo.py`**:
```python
def get_all_paginated_scoped(self, page, page_size, user_id=None):
    offset = (page - 1) * page_size
    query = Document.select()
    if user_id is not None:
        query = query.where(Document.uploaded_by == user_id)
    return list(query.offset(offset).limit(page_size)), query.count()

def get_by_id_scoped(self, doc_id: UUID, user_id=None) -> Optional[Document]:
    query = Document.select().where(Document.id == doc_id)
    if user_id is not None:
        query = query.where(Document.uploaded_by == user_id)
    return query.get_or_none()
```

**`src/repos/exam_template_repo.py`**:
```python
def get_all_paginated_scoped(self, page, page_size, user_id=None):
    offset = (page - 1) * page_size
    query = ExamTemplate.select()
    if user_id is not None:
        query = query.where(ExamTemplate.created_by == user_id)
    return list(query.offset(offset).limit(page_size)), query.count()

def get_by_id_scoped(self, template_id: UUID, user_id=None) -> Optional[ExamTemplate]:
    query = ExamTemplate.select().where(ExamTemplate.id == template_id)
    if user_id is not None:
        query = query.where(ExamTemplate.created_by == user_id)
    return query.get_or_none()
```

**`src/repos/exam_instance_repo.py`**:
```python
def get_all_paginated_scoped(self, page, page_size, user_id=None):
    offset = (page - 1) * page_size
    query = ExamInstance.select()
    if user_id is not None:
        query = query.where(ExamInstance.created_by == user_id)
    return list(query.offset(offset).limit(page_size)), query.count()

def get_by_id_scoped(self, exam_id: UUID, user_id=None) -> Optional[ExamInstance]:
    query = ExamInstance.select().where(ExamInstance.id == exam_id)
    if user_id is not None:
        query = query.where(ExamInstance.created_by == user_id)
    return query.get_or_none()

def get_versions_of_scoped(self, base_exam_id: UUID, user_id=None) -> List[ExamInstance]:
    query = ExamInstance.select().where(ExamInstance.parent_exam_instance == base_exam_id)
    if user_id is not None:
        # Versions inherit scope from base exam's created_by
        base = ExamInstance.get_or_none(ExamInstance.id == base_exam_id)
        if not base or (user_id is not None and base.created_by != user_id):
            return []
    return list(query)
```

**`src/repos/question_group_repo.py`**:
```python
def find_by_metadata_scoped(self, subject: str, topic: str, difficulty: str, user_id=None) -> List[QuestionGroup]:
    query = QuestionGroup.select().where(
        (QuestionGroup.subject == subject) &
        (QuestionGroup.topic == topic) &
        (QuestionGroup.difficulty == difficulty)
    )
    if user_id is not None:
        query = query.where(QuestionGroup.from_user == user_id)
    return list(query)

def get_or_create_scoped(self, subject: str, topic: str, difficulty: str, vector_embedding=None, user_id=None) -> QuestionGroup:
    # For non-admin users, only reuse question groups created by the same user
    if user_id is not None:
        group = self.find_by_metadata_scoped(subject, topic, difficulty, user_id=user_id)
        if group and vector_embedding:
            # Find best match by cosine similarity
            best_match = max(group, key=lambda g: cosine_sim(g.vector_embedding, vector_embedding))
            if cosine_sim(best_match.vector_embedding, vector_embedding) >= 0.75:
                return best_match
        # No match found; create new group for this user
        return self.create(subject=subject, topic=topic, difficulty=difficulty,
                          vector_embedding=vector_embedding, from_user=user_id)
    else:
        # Admin/global scope — can reuse any group across users
        return super().get_or_create(subject=subject, topic=topic, difficulty=difficulty)
```

### Service changes

**`src/services/document_service.py`**:
```python
async def upload_and_create_metadata(self, file: UploadFile, s3_prefix: str = "documents", user_id=None) -> Document:
    # ... existing upload logic ...
    document = self.repo.create(
        file_id=file_id,
        name=file.filename,
        s3_path=s3_path,
        uploaded_by=user_id  # NEW: store uploader
    )
    return document

def get_all_paginated(self, page=1, page_size=10, user_id=None, is_admin=False):
    scoped_user_id = None if is_admin else user_id
    return self.repo.get_all_paginated_scoped(page, page_size, user_id=scoped_user_id)

def get_by_id(self, doc_id: UUID, user_id=None, is_admin=False) -> Optional[Document]:
    scoped_user_id = None if is_admin else user_id
    return self.repo.get_by_id_scoped(doc_id, user_id=scoped_user_id)
```

**`src/services/core/document_extraction_service.py`**:
- No change needed — operates on documents owned by the current extraction task

**`src/services/core/question_extraction_service.py`**:
- Pass `user_id` from document context to `question_grouping_pipeline.process()` payload
- Update pipeline inputs: `{"..., "user_id": user_id_from_document}"` 

**`src/services/core/base_exam_generation_service.py`**:
```python
def save_template(self, name: str, subject: str, generation_config=None, template_id=None, user_id=None) -> ExamTemplate:
    if template_id:
        template = self._template_repo.get_by_id_scoped(template_id, user_id=user_id)
        if not template:
            raise NotFoundException("Template not found")
        # ... update existing ...
    else:
        return self._template_repo.create(
            name=name,
            subject=subject,
            generation_config=config_json,
            created_by=user_id  # NEW: store creator
        )

def generate_base_exam(self, sections, template_id=None, subject=None, user_id=None) -> ExamInstance:
    # Load template (scoped to user if not admin)
    if template_id:
        template = self._template_repo.get_by_id_scoped(template_id, user_id=user_id)
        if not template:
            raise NotFoundException("Template not found")
    
    # ... generate exam ...
    exam = self._create_exam_instance(
        template_id=template_id,
        sections=final_sections,
        is_base=True,
        created_by=user_id  # NEW: store creator
    )
    return exam

def _create_exam_instance(self, ..., created_by=None) -> ExamInstance:
    exam = self._instance_repo.create(
        ...,
        created_by=created_by  # NEW: persist creator
    )
    # ... rest of logic ...

def _retrieve_candidate_groups(self, section: SectionConfig, user_id=None) -> List[QuestionGroup]:
    # CRITICAL: Filter question groups by user_id (scoped questions only)
    candidates = self._group_repo.find_by_metadata_scoped(
        section.subject, section.topic, section.difficulty,
        user_id=user_id  # SCOPED: only user's question groups
    )
    
    if not candidates:
        # Try fallback difficulties, still scoped
        for fallback_diff in _DIFFICULTY_FALLBACKS.get(section.difficulty, []):
            candidates = self._group_repo.find_by_metadata_scoped(
                section.subject, section.topic, fallback_diff,
                user_id=user_id  # SCOPED
            )
            if candidates:
                break
    
    # ... rest of filtering logic ...
```

**`src/services/core/variant_exam_generation_service.py`**:
```python
def generate_versions(self, base_exam_id: UUID, num_versions: int, user_id=None) -> List[ExamInstance]:
    # Load base exam (scoped to user if not admin)
    base = self._instance_repo.get_by_id_scoped(base_exam_id, user_id=user_id)
    if not base:
        raise NotFoundException("Exam not found")
    if base.status != ExamInstanceStatus.ACCEPTED:
        raise BadRequestException("Base exam must be in ACCEPTED status")
    
    # ... generate versions ...
```

**`src/pipelines/question_grouping.py`**:
```python
async def process(self, payload: dict) -> dict:
    # Extract user_id from payload (passed from question_extraction_service)
    user_id = payload.get("user_id")
    
    questions = payload.get("questions", [])
    threshold = payload.get("similarity_threshold", 0.75)
    
    grouped_questions = []
    for question in questions:
        # Use get_or_create_scoped to respect user boundaries
        group = self._group_repo.get_or_create_scoped(
            subject=question["subject"],
            topic=question["topic"],
            difficulty=question["difficulty"],
            vector_embedding=question.get("vector"),
            user_id=user_id  # CRITICAL: scope group creation to user
        )
        grouped_questions.append({
            **question,
            "group_id": str(group.id)
        })
    
    return {"grouped_questions": grouped_questions}
```

**`src/services/core/question_extraction_service.py`**:
```python
async def process_page(self, page_id: UUID, document_id: UUID) -> TaskProgress:
    # Fetch document to get user_id (uploader)
    document = self._document_repo.get_by_id(document_id)
    user_id = document.uploaded_by if document else None
    
    # Pass user_id to grouping pipeline
    grouping_payload = {
        ...,
        "user_id": user_id  # NEW: pass to pipeline
    }
    grouped_questions = await self._grouping_pipeline.process(grouping_payload)
    
    # ... rest of pipeline chain ...
```

### Route changes

**`src/routes/document_route.py`**:
```python
@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    s3_prefix: str = Form(default="documents"),
    current_user: User = Depends(get_current_user),  # REQUIRE auth
    service: DocumentService = Depends(get_document_service),
):
    # ... validation ...
    document = await service.upload_and_create_metadata(
        file=file,
        s3_prefix=s3_prefix,
        user_id=current_user.id  # PERSIST uploader
    )

@router.get("")
async def list_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    current_user: Optional[User] = Depends(get_optional_user),
    service: DocumentService = Depends(get_document_service),
):
    user_id = current_user.id if current_user else None
    is_admin = (current_user.role == "admin") if current_user else False
    documents, total = service.get_all_paginated(
        page, page_size,
        user_id=user_id,
        is_admin=is_admin
    )

@router.get("/{document_id}")
async def get_document(
    document_id: UUID,
    current_user: Optional[User] = Depends(get_optional_user),
    service: DocumentService = Depends(get_document_service),
):
    user_id = current_user.id if current_user else None
    is_admin = (current_user.role == "admin") if current_user else False
    document = service.get_by_id(document_id, user_id=user_id, is_admin=is_admin)
    if not document:
        raise NotFoundException("Document not found or access denied")

@router.get("/{document_id}/questions")
async def get_document_questions(
    document_id: UUID,
    current_user: Optional[User] = Depends(get_optional_user),
    ...,
):
    # Verify user owns the document or is admin
    document = doc_service.get_by_id(document_id, user_id=current_user.id if current_user else None, is_admin=...)
    if not document:
        raise NotFoundException("Document not found")
```

**`src/routes/exam_route.py`**:
```python
@router.post("/templates")
async def save_template(
    body: SaveExamTemplateRequest,
    current_user: User = Depends(get_current_user),  # REQUIRE auth
    service: BaseExamGenerationService = Depends(get_base_service),
):
    template = service.save_template(
        ...,
        user_id=current_user.id  # PERSIST creator
    )

@router.get("/templates")
async def list_templates(
    subject: Optional[str] = Query(None),
    current_user: Optional[User] = Depends(get_optional_user),
    service: BaseExamGenerationService = Depends(get_base_service),
):
    user_id = current_user.id if current_user else None
    is_admin = (current_user.role == "admin") if current_user else False
    templates = service.list_templates(subject=subject, user_id=user_id, is_admin=is_admin)

@router.post("/generate-base")
async def generate_base_exam(
    body: GenerateBaseExamRequest,
    current_user: User = Depends(get_current_user),  # REQUIRE auth
    service: BaseExamGenerationService = Depends(get_base_service),
):
    exam = service.generate_base_exam(
        ...,
        user_id=current_user.id  # PERSIST creator, limit group scope
    )

@router.post("/generate-versions")
async def generate_versions(
    body: GenerateVersionsRequest,
    current_user: User = Depends(get_current_user),  # REQUIRE auth
    service: VariantExamGenerationService = Depends(get_variant_service),
):
    versions = service.generate_versions(
        ...,
        user_id=current_user.id  # Verify user owns base exam
    )
```

**`src/routes/page_route.py`**:
```python
@router.get("/document/{document_id}")
async def get_pages_by_document(
    document_id: UUID,
    current_user: Optional[User] = Depends(get_optional_user),
    doc_service: DocumentService = Depends(get_document_service),
):
    # Verify user owns document or is admin
    document = doc_service.get_by_id(
        document_id,
        user_id=current_user.id if current_user else None,
        is_admin=(current_user.role == "admin") if current_user else False
    )
    if not document:
        raise NotFoundException("Document not found or access denied")
    
    pages = page_service.get_by_document(document_id)

@router.get("/{page_id}")
async def get_page(
    page_id: UUID,
    current_user: Optional[User] = Depends(get_optional_user),
    page_service: PageService = Depends(get_page_service),
):
    page = page_service.get_by_id(page_id)
    if not page:
        raise NotFoundException("Page not found")
    
    # Verify user owns the page's document
    document = doc_service.get_by_id(
        page.document_id,
        user_id=current_user.id if current_user else None,
        is_admin=(current_user.role == "admin") if current_user else False
    )
    if not document:
        raise NotFoundException("Access denied")
```

---

## 7. Full File Checklist (Ordered)

```
Phase 1 — Foundation
  MODIFY  src/settings.py
  MODIFY  src/shared/constants/user.py
  MODIFY  src/entities/user.py

Phase 2 — User Repository & Service
  CREATE  src/repos/user_repo.py
  IMPLEMENT src/services/user_service.py

Phase 3 — Auth Service
  IMPLEMENT src/services/auth_service.py

Phase 4 — Auth Dependencies
  IMPLEMENT src/shared/auth_deps.py

Phase 5 — DTOs
  CREATE  src/dtos/auth/__init__.py
  CREATE  src/dtos/auth/req.py
  CREATE  src/dtos/auth/res.py
  CREATE  src/dtos/user/__init__.py
  CREATE  src/dtos/user/req.py
  CREATE  src/dtos/user/res.py

Phase 6 — Auth Route
  IMPLEMENT src/routes/auth_route.py

Phase 7 — User Route
  IMPLEMENT src/routes/user_route.py

Phase 8 — Wire DI + App
  MODIFY  src/app.py

Phase 9 — Migrations
  CREATE  src/lib/db/migrations/m0008_update_users_schema.py
  CREATE  src/lib/db/migrations/m0009_migrate_role_values.py
  CREATE  src/lib/db/migrations/m0010_add_user_fk_columns.py

Phase 10 — Entity FK Updates
  MODIFY  src/entities/document.py
  MODIFY  src/entities/exam_template.py
  MODIFY  src/entities/exam_instance.py
  MODIFY  src/entities/question_group.py

Phase 11 — Scoped Queries and User Data Isolation
  MODIFY  src/repos/document_repo.py                (add get_all_paginated_scoped, get_by_id_scoped)
  MODIFY  src/repos/exam_template_repo.py          (add get_all_paginated_scoped, get_by_id_scoped)
  MODIFY  src/repos/exam_instance_repo.py          (add get_all_paginated_scoped, get_by_id_scoped, get_versions_of_scoped)
  MODIFY  src/repos/question_group_repo.py         (add find_by_metadata_scoped, get_or_create_scoped)
  MODIFY  src/services/document_service.py         (pass user_id to repo.create, add scoped methods)
  MODIFY  src/services/core/document_extraction_service.py   (no direct changes; pipelines receive user_id via payload)
  MODIFY  src/services/core/question_extraction_service.py   (fetch user_id from document, pass to grouping_pipeline)
  MODIFY  src/services/core/base_exam_generation_service.py  (add user_id to save_template, generate_base_exam, _create_exam_instance, _retrieve_candidate_groups)
  MODIFY  src/services/core/variant_exam_generation_service.py (add user_id to generate_versions)
  MODIFY  src/pipelines/question_grouping.py       (add user_id to payload, use get_or_create_scoped)
  MODIFY  src/routes/document_route.py             (require auth for upload, inject get_optional_user on list/get, pass user_id to service)
  MODIFY  src/routes/exam_route.py                 (require auth for template save/generation, pass user_id to service)
  MODIFY  src/routes/page_route.py                 (inject get_optional_user, verify document ownership before exposing pages)
```

---

## 8. Dependencies to Add

```toml
# pyproject.toml
passlib = {extras = ["bcrypt"], version = ">=1.7.4"}
python-jose = {extras = ["cryptography"], version = ">=3.3.0"}
fastapi-mail = ">=1.4.1"
pydantic = {extras = ["email"], version = ">=2.0"}
```

---

## 9. Environment Variables to Add (.env)

```env
JWT_SECRET_KEY=your-very-long-random-secret-here
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7

SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_FROM_EMAIL=noreply@yourapp.com
SMTP_FROM_NAME=AI Service
FRONTEND_URL=http://localhost:3000
```

---

## 10. Implementation Notes

1. **`User` missing from `bind_models_to_database()` in `app.py`**: Add it — auth queries will fail at runtime without it.

2. **`is_email_verified` type change**: After `m0008`, the column becomes native `BOOLEAN`. Search for any existing `== "true"` comparisons and update to `is True`.

3. **Email verification enforcement on login**: Raise `ForbiddenException("Email not verified. Please check your inbox.")` if `is_email_verified is False`.

4. **Refresh token rotation**: On every `/refresh`, delete the old Redis key before issuing new tokens. If the key is already gone, raise `UnauthorizedException("Refresh token reused or expired")` — detects replay attacks.

5. **No user enumeration on forgot-password**: Always return identical success message regardless of whether the email exists.

6. **FK field serialization in `to_dict`**: Peewee FK fields accessed as `obj.fk_field` trigger a lazy JOIN. Use the `_id` suffixed attribute (e.g., `uploaded_by_id`) for raw UUID access. Declare `column_name` in all `ForeignKeyField` calls to control the DB column name explicitly.

7. **Circular import prevention**: `User` entity must not import from service or repo layers. The import chain `auth_service → user_service → user_repo → user entity` is safe.

---

## 11. User Data Scoping Architecture

### Core Principle

All data is scoped to the user who created/owns it. Non-admin users can only access their own data; admins can access all data. The scoping applies across all layers: repository, service, route.

### Scoping Rules by Entity

| Entity | Owner Field | Creation Point | Non-Admin Access |
|--------|-------------|-----------------|------------------|
| Document | `uploaded_by` | `upload_document` route | Only if uploader matches current user |
| ExamTemplate | `created_by` | `save_template` route | Only if creator matches current user |
| ExamInstance | `created_by` | `generate_base_exam` route | Only if creator matches current user; versions inherit base's scope |
| QuestionGroup | `from_user` | `question_grouping_pipeline` | Only user's groups can be picked for that user's exams (no cross-user reuse) |
| Page | Derived from Document | Document extraction | Access via document ownership check |

### Scoping Pattern (Repository → Service → Route)

**1. Repository layer** — add `*_scoped` methods:
```python
def get_by_id_scoped(self, id: UUID, user_id=None) -> Optional[Entity]:
    query = Entity.select().where(Entity.id == id)
    if user_id is not None:
        query = query.where(Entity.owner_field == user_id)
    return query.get_or_none()

def get_all_paginated_scoped(self, page, page_size, user_id=None):
    query = Entity.select()
    if user_id is not None:
        query = query.where(Entity.owner_field == user_id)
    return list(query.offset(...).limit(...)), query.count()
```

**2. Service layer** — call scoped repos, pass `user_id` on creation:
```python
def create_entity(..., user_id=None) -> Entity:
    return self.repo.create(..., owner_field=user_id)

def get_entity(entity_id, user_id=None, is_admin=False) -> Optional[Entity]:
    scoped_user_id = None if is_admin else user_id
    return self.repo.get_by_id_scoped(entity_id, user_id=scoped_user_id)
```

**3. Route layer** — extract user from token, pass to service:
```python
async def get_entity(
    entity_id: UUID,
    current_user: Optional[User] = Depends(get_optional_user),
):
    user_id = current_user.id if current_user else None
    is_admin = (current_user.role == "admin") if current_user else False
    entity = service.get_entity(entity_id, user_id=user_id, is_admin=is_admin)
    if not entity:
        raise NotFoundException("Entity not found or access denied")
```

### Mutation-Only Routes (Require Authentication)

The following routes MUST have `Depends(get_current_user)` (not optional):
- POST `/documents/upload`
- POST `/templates` (save exam template)
- POST `/generate-base` (exam generation)
- POST `/generate-versions` (version generation)
- PATCH `/instances/{id}/status` (exam status update)
- PATCH `/instances/{id}/replace-question` (question replacement in exam)

Non-mutation routes can use `get_optional_user` to allow read-only access for unauthenticated users (at your discretion).

### Critical Implementation Detail: Question Group Scoping

**Issue**: Question groups are typically global — multiple users' questions can belong to the same group if semantically similar. With per-user scoping, question groups become user-isolated.

**Solution**: 
- Non-admin users: `QuestionGroup.from_user` must match current user. Group creation during document extraction sets `from_user = document.uploaded_by`.
- When exam generation picks candidate groups for exam building, only groups with matching `from_user` (or `NULL` for pre-existing shared groups) are considered.
- Admin users: can pick from any group across all users.

**Implementation** in `base_exam_generation_service._retrieve_candidate_groups()`:
```python
def _retrieve_candidate_groups(self, section: SectionConfig, user_id=None):
    # Scoped query: only user's question groups
    candidates = self._group_repo.find_by_metadata_scoped(
        section.subject, section.topic, section.difficulty,
        user_id=user_id  # CRITICAL: limit to user's groups
    )
```

### Document Extraction Pipeline (User Context)

The document extraction pipeline must propagate the document uploader's identity (user_id) through the question extraction → grouping → persistence chain:

1. **document_route.upload_document** → pass `uploaded_by=current_user.id` to `document_service`
2. **question_extraction_service.process_page** → fetch document, extract `user_id = document.uploaded_by`
3. **question_grouping_pipeline.process** → receive `user_id` in payload, use `get_or_create_scoped(user_id=user_id)`
4. **question_persistence_pipeline** → no direct changes; groups are already scoped by grouping pipeline

### Access Denial Pattern

Always use `NotFoundException` (404) instead of `ForbiddenException` (403) when denying access due to ownership. This prevents user enumeration:
```python
# Correct
document = service.get_document(doc_id, user_id=current_user.id)
if not document:
    raise NotFoundException("Document not found")  # Could mean "doesn't exist" OR "not yours"

# Avoid
if not current_user_owns(document):
    raise ForbiddenException("You don't have permission")  # User enumeration risk
```

### Admin Bypass

Pass `is_admin=True` to any scoped repo method to bypass ownership checks:
```python
# Non-admin: only sees their own
document = repo.get_by_id_scoped(doc_id, user_id=user_id)

# Admin: sees all (pass None to user_id when is_admin=True)
document = repo.get_by_id_scoped(doc_id, user_id=None) if is_admin else ...
```

Pattern in services:
```python
def get_document(self, doc_id, user_id=None, is_admin=False):
    scoped_user_id = None if is_admin else user_id
    return self.repo.get_by_id_scoped(doc_id, user_id=scoped_user_id)
```
