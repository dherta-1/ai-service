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

## 6. Scoped Logic Refactoring

### Repository changes

Add `get_all_paginated_scoped(page, page_size, user_id=None)` to:

- **`src/repos/document_repo.py`** — filter `Document.uploaded_by == user_id`
- **`src/repos/exam_template_repo.py`** — filter `ExamTemplate.created_by == user_id`
- **`src/repos/exam_instance_repo.py`** — filter `ExamInstance.created_by == user_id`
- **`src/repos/question_group_repo.py`** — filter `QuestionGroup.from_user == user_id`

Pattern:
```python
def get_all_paginated_scoped(self, page, page_size, user_id=None):
    offset = (page - 1) * page_size
    query = Entity.select()
    if user_id is not None:
        query = query.where(Entity.owner_field == user_id)
    return list(query.offset(offset).limit(page_size)), query.count()
```

### Service changes

Update `get_all_paginated` in each service:
```python
def get_all_paginated(self, page=1, page_size=10, user_id=None, is_admin=False):
    scoped_user_id = None if is_admin else user_id
    return self.repo.get_all_paginated_scoped(page, page_size, user_id=scoped_user_id)
```

Update creation methods to store the caller's identity:
- `document_service.upload_and_create_metadata(...)` → pass `uploaded_by=user_id`
- `base_exam_generation_service.save_template(...)` → pass `created_by=user_id`
- `base_exam_generation_service._create_exam_instance(...)` → pass `created_by=user_id`

### Route changes

Inject `get_optional_user` into list and create endpoints:

```python
# Example: document_route.py list_documents
async def list_documents(
    ...,
    current_user: Optional[User] = Depends(get_optional_user),
):
    user_id = current_user.id if current_user else None
    is_admin = (current_user.role == "admin") if current_user else False
    documents, total = service.get_all_paginated(page, page_size, user_id=user_id, is_admin=is_admin)
```

Apply same pattern to:
- `src/routes/document_route.py` — `list_documents`, `upload_document`
- `src/routes/exam_route.py` — `list_templates`, `save_template`, `generate_base_exam`

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

Phase 11 — Scoped Queries
  MODIFY  src/repos/document_repo.py
  MODIFY  src/repos/exam_template_repo.py
  MODIFY  src/repos/exam_instance_repo.py
  MODIFY  src/repos/question_group_repo.py
  MODIFY  src/services/document_service.py
  MODIFY  src/services/core/base_exam_generation_service.py
  MODIFY  src/routes/document_route.py
  MODIFY  src/routes/exam_route.py
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
