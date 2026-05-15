from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Optional

from src.entities.attempt_token_mapping import AttemptTokenMapping
from src.repos.attempt_token_mapping_repo import AttemptTokenMappingRepository


class ExamTokenService:
    def __init__(self):
        self._repo = AttemptTokenMappingRepository()

    def generate_attempt_token(
        self, attempt_id: str, expires_in_minutes: int = 120
    ) -> str:
        token = secrets.token_urlsafe(32)
        token_hash = self._hash_token(token)
        AttemptTokenMapping.create_token_mapping(
            attempt_id=attempt_id,
            token_hash=token_hash,
            expires_in_minutes=expires_in_minutes,
        )
        return token

    def validate_attempt_token(
        self, token: str, allow_invalidated: bool = False
    ) -> Optional[AttemptTokenMapping]:
        token_hash = self._hash_token(token)
        mapping = self._repo.get_by_hash(token_hash)
        if not mapping:
            return None

        if not hmac.compare_digest(mapping.token_hash, token_hash):
            return None

        if mapping.is_expired():
            return None

        if mapping.is_invalidated and not allow_invalidated:
            return None

        return mapping

    def invalidate_token(self, token: str) -> bool:
        token_hash = self._hash_token(token)
        return self._repo.invalidate_by_hash(token_hash)

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()
