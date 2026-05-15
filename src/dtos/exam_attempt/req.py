from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class CreateExamAttemptRequest(BaseModel):
    use_existing_instance: bool = False
    existing_instance_id: Optional[UUID] = None


class SaveAnswerRequest(BaseModel):
    question_token: str = Field(..., min_length=1)
    selected_option_token: Optional[str] = None


class SubmittedAnswer(BaseModel):
    question_token: str = Field(..., min_length=1)
    selected_option_token: Optional[str] = None


class SubmitExamRequest(BaseModel):
    answers: List[SubmittedAnswer]
