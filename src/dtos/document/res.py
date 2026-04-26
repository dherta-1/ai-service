from uuid import UUID
from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime


class DocumentResponse(BaseModel):
    """Response DTO for document"""

    id: UUID
    name: str
    file_id: str
    status: str
    progress: float
    metadata: Optional[Any] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
