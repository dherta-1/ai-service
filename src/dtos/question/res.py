from uuid import UUID
from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime


class QuestionResponse(BaseModel):
    """Response DTO for question"""

    id: UUID
    page: UUID
    question_text: str
    question_type: str
    difficulty: Optional[str] = None
    subject: Optional[str] = None
    topic: Optional[str] = None
    sub_questions: Optional[list] = None
    answers: Optional[list] = None
    correct_answer: Optional[str] = None
    image_list: Optional[list] = None
    # vector_embedding: Optional[list] = None
    status: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
