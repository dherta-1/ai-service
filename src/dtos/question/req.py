from uuid import UUID
from pydantic import BaseModel
from typing import Optional, List


class AnswerInput(BaseModel):
    value: str
    is_correct: bool
    explaination: Optional[str] = None


class SubQuestionInput(BaseModel):
    sub_question_order: int
    question_text: str
    question_type: str
    answers: Optional[List[AnswerInput]] = None
    image_list: Optional[List[str]] = None


class CreateQuestionRequest(BaseModel):
    question_text: str
    question_type: str
    difficulty: str
    subject: str
    topic: str
    answers: Optional[List[AnswerInput]] = None
    sub_questions: Optional[List[SubQuestionInput]] = None
    image_list: Optional[List[str]] = None
    page_id: Optional[UUID] = None


class UpdateQuestionRequest(BaseModel):
    question_text: Optional[str] = None
    question_type: Optional[str] = None
    difficulty: Optional[str] = None
    subject: Optional[str] = None
    topic: Optional[str] = None
    answers: Optional[List[AnswerInput]] = None
    sub_questions: Optional[List[SubQuestionInput]] = None
    image_list: Optional[List[str]] = None
    reassign_group: bool = True


class AcceptAnswerRequest(BaseModel):
    """User-accepted (possibly edited) generated answer payload."""
    answer: Optional[dict] = None
