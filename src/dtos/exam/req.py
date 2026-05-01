from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class SectionConfig(BaseModel):
    name: str
    subject: str
    topic: str
    difficulty: str                         # "easy" | "medium" | "hard"
    question_type: Optional[str] = None     # filter by type; None = any
    top_k: int = Field(ge=1)
    random_level: str = "medium"            # "low" | "medium" | "high"
    custom_text: Optional[str] = None       # semantic hint for retrieval


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
