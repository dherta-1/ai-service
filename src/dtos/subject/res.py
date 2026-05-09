from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID
from datetime import datetime


class SubjectResponse(BaseModel):
    """Subject response DTO"""
    id: UUID = Field(description="Subject unique identifier")
    code: str = Field(description="Unique subject code (e.g., 'math', 'physics')")
    name: str = Field(description="Subject name in English")
    name_vi: Optional[str] = Field(None, description="Subject name in Vietnamese")
    description: Optional[str] = Field(None, description="Subject description")
    created_at: datetime = Field(description="Creation timestamp")
    updated_at: datetime = Field(description="Last update timestamp")

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "code": "math",
                "name": "Mathematics",
                "name_vi": "Toán học",
                "description": "General mathematics",
                "created_at": "2026-05-08T10:00:00",
                "updated_at": "2026-05-08T10:00:00"
            }
        }
