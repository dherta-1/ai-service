from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class AuditLogListQuery(BaseModel):
    page: int = 1
    page_size: int = 20
    actor_type: Optional[str] = None
    actor_id: Optional[UUID] = None
    entity_type: Optional[str] = None
    action_type: Optional[str] = None
