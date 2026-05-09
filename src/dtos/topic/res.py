from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID
from datetime import datetime


class TopicResponse(BaseModel):
    """Topic response DTO"""
    id: UUID = Field(description="Topic unique identifier")
    code: str = Field(description="Unique topic code (e.g., 'algebra', 'calculus')")
    name: str = Field(description="Topic name in English")
    name_vi: Optional[str] = Field(None, description="Topic name in Vietnamese")
    subject_code: Optional[str] = Field(None, description="Parent subject code")
    description: Optional[str] = Field(None, description="Topic description")
    created_at: datetime = Field(description="Creation timestamp")
    updated_at: datetime = Field(description="Last update timestamp")

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440001",
                "code": "algebra",
                "name": "Algebra",
                "name_vi": "Đại số",
                "subject_code": "math",
                "description": "Algebra fundamentals",
                "created_at": "2026-05-08T10:00:00",
                "updated_at": "2026-05-08T10:00:00"
            }
        }
