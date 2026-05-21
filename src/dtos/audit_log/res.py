from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID
import json

from pydantic import BaseModel, model_validator


class AuditLogResponse(BaseModel):
    id: UUID
    actor_type: str
    actor_id: Optional[UUID] = None
    entity_type: str
    entity_id: Optional[UUID] = None
    action_type: str
    before_data: Optional[Dict[str, Any]] = None
    after_data: Optional[Dict[str, Any]] = None
    request_ip: Optional[str] = None
    client: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="before")
    @classmethod
    def parse_json_fields(cls, values):
        if hasattr(values, "__dict__"):
            # Peewee model instance — convert to dict-like
            data = {
                "id": values.id,
                "actor_type": values.actor_type,
                "actor_id": values.actor_id,
                "entity_type": values.entity_type,
                "entity_id": values.entity_id,
                "action_type": values.action_type,
                "before_data": values.before_data,
                "after_data": values.after_data,
                "request_ip": values.request_ip,
                "client": values.client,
                "created_at": values.created_at,
                "updated_at": values.updated_at,
            }
            values = data

        for field in ("before_data", "after_data"):
            v = values.get(field)
            if isinstance(v, str):
                try:
                    values[field] = json.loads(v)
                except Exception:
                    values[field] = None
        return values

    class Config:
        from_attributes = True
