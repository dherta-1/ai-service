from pydantic import BaseModel, Field
from typing import Optional


class TopicListQuery(BaseModel):
    """Query parameters for topic listing"""
    query: Optional[str] = Field(None, description="Search query (searches name, code, name_vi)")
    subject_code: Optional[str] = Field(None, description="Filter by subject code")
    page: int = Field(1, ge=1, description="Page number (1-indexed)")
    page_size: int = Field(10, ge=1, le=100, description="Items per page")

    class Config:
        json_schema_extra = {
            "example": {
                "query": "algebra",
                "subject_code": "math",
                "page": 1,
                "page_size": 10
            }
        }
