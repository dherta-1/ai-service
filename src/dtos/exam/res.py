from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel

from src.dtos.exam.req import SectionConfig


class ExamTemplateResponse(BaseModel):
    id: UUID
    name: str
    subject: str
    generation_config: Optional[List[SectionConfig]] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AnswerInExamResponse(BaseModel):
    id: UUID
    value: str
    is_correct: bool

    class Config:
        from_attributes = True


class QuestionInExamResponse(BaseModel):
    question_exam_test_id: UUID
    question_id: UUID
    question_group_id: UUID
    order_count: int
    answer_order: Optional[List[int]] = None  # shuffled answer index list

    question_text: str
    question_type: str
    difficulty: Optional[str] = None
    image_list: Optional[list] = None
    answers: List[AnswerInExamResponse]
    sub_questions: Optional[List[QuestionInExamResponse]] = None

    class Config:
        from_attributes = True


QuestionInExamResponse.model_rebuild()


class ExamSectionResponse(BaseModel):
    id: UUID
    name: str
    order_index: int
    questions: List[QuestionInExamResponse]

    class Config:
        from_attributes = True


class ExamInstanceResponse(BaseModel):
    id: UUID
    exam_test_code: str
    is_base: bool
    is_exported: bool
    status: int
    template_id: Optional[UUID] = None
    parent_exam_instance_id: Optional[UUID] = None
    sections: List[ExamSectionResponse]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class GenerateBaseExamResponse(BaseModel):
    exam_instance: ExamInstanceResponse
    total_questions: int


class GenerateVersionsResponse(BaseModel):
    versions: List[ExamInstanceResponse]
    total_versions: int
