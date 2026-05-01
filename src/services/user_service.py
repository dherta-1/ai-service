from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Tuple
from uuid import UUID

from src.entities.user import User
from src.repos.user_repo import UserRepository
from src.shared.base.base_service import BaseService


class UserService(BaseService):

    def __init__(self):
        super().__init__(UserRepository())

    # --- Query ---

    def get_by_email(self, email: str) -> Optional[User]:
        return self.repo.get_by_email(email)

    def list_users(self, page: int = 1, page_size: int = 20) -> Tuple[List[User], int]:
        return self.repo.get_all_paginated(page, page_size)

    # --- Mutation ---

    def set_password_hash(self, user_id: UUID, hashed: str) -> Optional[User]:
        return self.repo.update(user_id, password_hash=hashed)

    def mark_email_verified(self, user_id: UUID) -> Optional[User]:
        return self.repo.update(user_id, is_email_verified=True)

    def update_last_login(self, user_id: UUID) -> Optional[User]:
        return self.repo.update(user_id, last_login_at=datetime.utcnow())

    def update_user(self, user_id: UUID, **kwargs) -> Optional[User]:
        return self.repo.update(user_id, **kwargs)

    def delete_user(self, user_id: UUID) -> bool:
        return self.repo.delete(user_id)
