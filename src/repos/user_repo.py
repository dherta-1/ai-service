from __future__ import annotations

from typing import List, Optional, Tuple
from uuid import UUID

from src.entities.user import User
from src.shared.base.base_repo import BaseRepo


class UserRepository(BaseRepo[User]):

    def __init__(self):
        super().__init__(User)

    def get_by_email(self, email: str) -> Optional[User]:
        return User.get_or_none(User.email == email)

    def get_all_paginated(self, page: int = 1, page_size: int = 20) -> Tuple[List[User], int]:
        offset = (page - 1) * page_size
        query = User.select()
        return list(query.offset(offset).limit(page_size)), query.count()
