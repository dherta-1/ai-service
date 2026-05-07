from uuid import UUID
from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime


class TaskResponse(BaseModel):
    """Response DTO for task"""

    id: UUID
    document_id: UUID
    status: str
    progress: float
    error_message: Optional[str] = None
    metadata: Optional[Any] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
