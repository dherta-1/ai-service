from __future__ import annotations

from typing import Optional

from src.entities.attempt_token_mapping import AttemptTokenMapping
from src.shared.base.base_repo import BaseRepo


class AttemptTokenMappingRepository(BaseRepo[AttemptTokenMapping]):
    def __init__(self):
        super().__init__(AttemptTokenMapping)

    def get_by_hash(self, token_hash: str) -> Optional[AttemptTokenMapping]:
        return self.filter_one(token_hash=token_hash)

    def invalidate_by_hash(self, token_hash: str) -> bool:
        rows = (
            AttemptTokenMapping.update(is_invalidated=True)
            .where(AttemptTokenMapping.token_hash == token_hash)
            .execute()
        )
        return rows > 0
