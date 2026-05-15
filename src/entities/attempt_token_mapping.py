from __future__ import annotations

from datetime import datetime, timedelta

from peewee import BooleanField, CharField, DateTimeField

from src.shared.base.base_entity import BaseEntity


class AttemptTokenMapping(BaseEntity):
    token_hash = CharField(max_length=255, unique=True, index=True)
    attempt_id = CharField(max_length=255, index=True)
    expires_at = DateTimeField(index=True)
    is_invalidated = BooleanField(default=False)

    class Meta:
        table_name = "attempt_token_mappings"

    @classmethod
    def create_token_mapping(
        cls,
        attempt_id: str,
        token_hash: str,
        expires_in_minutes: int = 120,
    ) -> AttemptTokenMapping:
        return cls.create(
            attempt_id=attempt_id,
            token_hash=token_hash,
            expires_at=datetime.utcnow() + timedelta(minutes=expires_in_minutes),
        )

    def is_expired(self) -> bool:
        return datetime.utcnow() > self.expires_at

    def is_valid(self) -> bool:
        return not self.is_invalidated and not self.is_expired()
