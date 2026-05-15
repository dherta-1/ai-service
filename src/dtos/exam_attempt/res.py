from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class ExamOptionResponse(BaseModel):
    option_token: str
    content: str


class ExamQuestionResponse(BaseModel):
    question_no: int
    question_token: str
    question_text: str
    question_type: str
    image_list: Optional[list] = None
    options: List[ExamOptionResponse]


class ExamAttemptResponse(BaseModel):
    attempt_token: str
    expires_at: datetime
    started_at: datetime
    total_questions: int
    questions: List[ExamQuestionResponse]


class CurrentAttemptResponse(BaseModel):
    attempt_token: str
    status: str
    started_at: datetime
    expires_at: datetime
    time_elapsed_ms: int
    total_questions: int
    answered_count: int
    questions: List[ExamQuestionResponse]


class SubmitAttemptResponse(BaseModel):
    status: str
    submitted_at: datetime
    score: float
    total_questions: int
    correct_count: int
    result_available: bool


class AttemptResultDetail(BaseModel):
    question_id: str
    question_no: int
    selected_answer_id: Optional[str] = None
    is_correct: bool


class AttemptResultResponse(BaseModel):
    score: Optional[float]
    total_questions: int
    correct_count: int
    submitted_at: Optional[datetime] = None
    review_available: bool
    details: List[AttemptResultDetail]
