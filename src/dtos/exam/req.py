from __future__ import annotations

from typing import List, Optional, Union
from uuid import UUID

from pydantic import BaseModel, Field, model_validator, field_validator


class SectionConfig(BaseModel):
    name: str
    subject: str
    topic: Union[str, List[str]]                  # single topic or list of topics
    difficulty: str                         # "easy" | "medium" | "hard"
    question_type: Optional[Union[str, List[str]]] = None  # single type, list of types, or None = any
    top_k: int = Field(ge=1)
    random_level: str = "medium"            # "low" | "medium" | "high"
    custom_text: Optional[str] = None       # semantic hint for retrieval
    skip_group_filtering: bool = False      # if True, pick questions directly instead of grouping

    @field_validator("topic", mode="before")
    @classmethod
    def normalize_topic(cls, v):
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            return v
        raise ValueError("topic must be a string or list of strings")

    @field_validator("question_type", mode="before")
    @classmethod
    def normalize_question_type(cls, v):
        if v is None:
            return None
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            return v
        raise ValueError("question_type must be a string, list of strings, or null")


class SaveExamTemplateRequest(BaseModel):
    name: str
    subject: str
    generation_config: Optional[List[SectionConfig]] = None  # default section configs
    template_id: Optional[UUID] = None      # if given, update existing template


class GenerateBaseExamRequest(BaseModel):
    """Generate a base exam.

    Mode 1 — regenerate from template:
        template_id = <uuid>, sections = [] (uses template config) or non-empty (overrides)

    Mode 2 — one-off (no template):
        template_id = null, sections = [...], subject = <str>
    """
    template_id: Optional[UUID] = None
    sections: Optional[List[SectionConfig]] = None
    subject: Optional[str] = None           # required when template_id is null

    @model_validator(mode="after")
    def _validate(self) -> GenerateBaseExamRequest:
        # If template_id is provided, other fields are optional (will use template config)
        if self.template_id is not None:
            return self

        # If no template_id, must have both subject and sections
        if not self.subject:
            raise ValueError("subject is required when template_id is not provided")
        if not self.sections:
            raise ValueError("sections must be provided when template_id is not provided")
        return self


class GenerateVersionsRequest(BaseModel):
    base_exam_id: UUID
    num_versions: int = Field(default=4, ge=1, le=10)


class UpdateExamStatusRequest(BaseModel):
    status: int = Field(ge=0, le=2)         # 0=pending, 1=accepted, 2=rejected


class ReplaceQuestionRequest(BaseModel):
    question_exam_test_id: UUID
    new_question_id: UUID                   # must be in same question_group
