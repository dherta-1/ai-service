from uuid import UUID
from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime


class PageResponse(BaseModel):
    """Response DTO for page"""

    id: UUID
    document: UUID
    page_number: int
    content: Optional[str] = None
    validated_content: Optional[str] = None
    overlap_content: Optional[str] = None
    page_image_id: Optional[UUID] = None
    image_list: Optional[list] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
