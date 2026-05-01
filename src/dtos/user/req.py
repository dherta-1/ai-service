from typing import Optional

from pydantic import BaseModel, Field


class UpdateUserRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    role: Optional[str] = Field(default=None, pattern="^(user|admin)$")
