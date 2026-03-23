from pydantic import BaseModel, Field
from typing import Optional


class ProjectMetadataReqDTO(BaseModel):
    """Request DTO for creating/updating ProjectMetadata"""

    name: str = Field(..., min_length=1, max_length=255, description="Project name")
    description: Optional[str] = Field(None, description="Project description")
    version: str = Field(default="1.0.0", max_length=50, description="Project version")
