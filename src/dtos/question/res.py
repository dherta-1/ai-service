from uuid import UUID
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class AnswerResponse(BaseModel):
    id: UUID
    value: str
    is_correct: bool
    explaination: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SubQuestionResponse(BaseModel):
    id: UUID
    question_text: str
    question_type: str
    sub_question_order: Optional[int] = None
    answers: Optional[List[AnswerResponse]] = None
    status: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class QuestionResponse(BaseModel):
    id: UUID
    page_id: Optional[UUID] = None
    parent_question_id: Optional[UUID] = None
    questions_group_id: Optional[UUID] = None
    question_text: str
    question_type: str
    difficulty: Optional[str] = None
    subject: Optional[str] = None
    topic: Optional[str] = None
    image_list: Optional[list] = None
    sub_question_order: Optional[int] = None
    variant_existence_count: int = 1
    status: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class QuestionListResponse(BaseModel):
    id: UUID
    page_id: Optional[UUID] = None
    parent_question_id: Optional[UUID] = None
    questions_group_id: Optional[UUID] = None
    question_text: str
    question_type: str
    difficulty: Optional[str] = None
    subject: Optional[str] = None
    topic: Optional[str] = None
    image_list: Optional[list] = None
    sub_question_order: Optional[int] = None
    variant_existence_count: int = 1
    status: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class QuestionDetailResponse(QuestionResponse):
    answers: Optional[List[AnswerResponse]] = None
    sub_questions: Optional[List[SubQuestionResponse]] = None


class TaskProgressResponse(BaseModel):
    id: UUID
    name: Optional[str] = None
    status: str
    progress: float
    total_pages: Optional[int] = None
    processed_pages: int = 0
    logs: Optional[list] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
