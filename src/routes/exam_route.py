from __future__ import annotations

import json
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from src.container import get_di_container
from src.shared.response.exception_handler import NotFoundException, BadRequestException
from src.dtos.exam.req import (
    GenerateBaseExamRequest,
    GenerateVersionsRequest,
    ReplaceQuestionRequest,
    SaveExamTemplateRequest,
    UpdateExamStatusRequest,
)
from src.services.core.base_exam_generation_service import BaseExamGenerationService
from src.services.core.variant_exam_generation_service import VariantExamGenerationService
from src.shared.helpers.dto_utils import to_dict
from src.shared.response.response_models import create_response, create_paginated_response

logger = logging.getLogger(__name__)
router = APIRouter()


def get_base_service() -> BaseExamGenerationService:
    return get_di_container().resolve(BaseExamGenerationService)


def get_variant_service() -> VariantExamGenerationService:
    return get_di_container().resolve(VariantExamGenerationService)


# ------------------------------------------------------------------
# Templates
# ------------------------------------------------------------------

@router.post("/templates")
async def save_template(
    body: SaveExamTemplateRequest,
    service: BaseExamGenerationService = Depends(get_base_service),
):
    """Create or update an exam template with optional default section configs."""
    try:
        template = service.save_template(
            name=body.name,
            subject=body.subject,
            generation_config=body.generation_config,
            template_id=body.template_id,
        )
        data = to_dict(template)
        if template.generation_config:
            try:
                data["generation_config"] = json.loads(template.generation_config)
            except (ValueError, TypeError):
                data["generation_config"] = None
        return create_response(data=data, message="Template saved successfully")
    except ValueError as exc:
        raise BadRequestException(str(exc))


@router.get("/templates")
async def list_templates(
    subject: Optional[str] = Query(None),
    service: BaseExamGenerationService = Depends(get_base_service),
):
    """List all exam templates, optionally filtered by subject."""
    templates = service.list_templates(subject=subject)
    data = []
    for t in templates:
        d = to_dict(t)
        if t.generation_config:
            try:
                d["generation_config"] = json.loads(t.generation_config)
            except (ValueError, TypeError):
                d["generation_config"] = None
        data.append(d)
    return create_paginated_response(
        data=data,
        total=len(data),
        message="Templates retrieved successfully",
    )


@router.get("/templates/{template_id}")
async def get_template(
    template_id: UUID,
    service: BaseExamGenerationService = Depends(get_base_service),
):
    """Get a single exam template by ID."""
    template = service.get_template(template_id)
    if not template:
        raise NotFoundException("Template not found")
    data = to_dict(template)
    if template.generation_config:
        try:
            data["generation_config"] = json.loads(template.generation_config)
        except (ValueError, TypeError):
            data["generation_config"] = None
    return create_response(data=data, message="Template retrieved successfully")


# ------------------------------------------------------------------
# Base exam generation
# ------------------------------------------------------------------

@router.post("/generate-base")
async def generate_base_exam(
    body: GenerateBaseExamRequest,
    service: BaseExamGenerationService = Depends(get_base_service),
):
    """Generate a base exam instance from section configs.

    - template_id given → regenerate (sections override template defaults)
    - template_id null  → one-off exam (subject + sections required)
    """
    try:
        exam = service.generate_base_exam(
            sections=body.sections,
            template_id=body.template_id,
            subject=body.subject,
        )
        exam_data = service.build_exam_response_data(exam)
        total_questions = exam_data.pop("_total_questions", 0)
        return create_response(
            data={"exam_instance": exam_data, "total_questions": total_questions},
            message="Base exam generated successfully",
        )
    except ValueError as exc:
        raise BadRequestException(str(exc))


# ------------------------------------------------------------------
# Exam instances
# ------------------------------------------------------------------

@router.get("/instances/{exam_id}")
async def get_exam_instance(
    exam_id: UUID,
    service: BaseExamGenerationService = Depends(get_base_service),
):
    """Get a full exam instance with all sections and questions."""
    exam = service.get_exam_instance(exam_id)
    if not exam:
        raise NotFoundException("Exam instance not found")
    exam_data = service.build_exam_response_data(exam)
    exam_data.pop("_total_questions", None)
    return create_response(data=exam_data, message="Exam instance retrieved successfully")


@router.get("/instances/{exam_id}/versions")
async def get_exam_versions(
    exam_id: UUID,
    service: BaseExamGenerationService = Depends(get_base_service),
):
    """List all versions generated from a base exam."""
    exam = service.get_exam_instance(exam_id)
    if not exam:
        raise NotFoundException("Exam instance not found")

    versions = service.get_exam_versions(exam_id)
    data = []
    for v in versions:
        v_data = service.build_exam_response_data(v)
        v_data.pop("_total_questions", None)
        data.append(v_data)

    return create_paginated_response(
        data=data,
        total=len(data),
        message="Exam versions retrieved successfully",
    )


@router.patch("/instances/{exam_id}/status")
async def update_exam_status(
    exam_id: UUID,
    body: UpdateExamStatusRequest,
    service: BaseExamGenerationService = Depends(get_base_service),
):
    """Update exam instance status. 0=pending, 1=accepted, 2=rejected."""
    try:
        exam = service.update_exam_status(exam_id, body.status)
        return create_response(
            data={"id": str(exam_id), "status": exam.status},
            message="Exam status updated successfully",
        )
    except ValueError as exc:
        raise BadRequestException(str(exc))


@router.patch("/instances/{exam_id}/replace-question")
async def replace_question(
    exam_id: UUID,
    body: ReplaceQuestionRequest,
    service: BaseExamGenerationService = Depends(get_base_service),
):
    """Replace a question variant in an exam with another from the same group."""
    try:
        qet = service.replace_question(
            exam_instance_id=exam_id,
            qet_id=body.question_exam_test_id,
            new_question_id=body.new_question_id,
        )
        return create_response(
            data={
                "question_exam_test_id": str(qet.id),
                "question_id": qet.question_id,
                "answer_order": json.loads(qet.answer_order) if qet.answer_order else None,
            },
            message="Question replaced successfully",
        )
    except ValueError as exc:
        raise BadRequestException(str(exc))


# ------------------------------------------------------------------
# Version generation
# ------------------------------------------------------------------

@router.post("/generate-versions")
async def generate_versions(
    body: GenerateVersionsRequest,
    service: VariantExamGenerationService = Depends(get_variant_service),
    base_service: BaseExamGenerationService = Depends(get_base_service),
):
    """Generate N version exams from an accepted base exam."""
    try:
        versions = service.generate_versions(
            base_exam_id=body.base_exam_id,
            num_versions=body.num_versions,
        )
        versions_data = []
        for v in versions:
            v_data = base_service.build_exam_response_data(v)
            v_data.pop("_total_questions", None)
            versions_data.append(v_data)

        return create_response(
            data={"versions": versions_data, "total_versions": len(versions_data)},
            message=f"{len(versions_data)} exam versions generated successfully",
        )
    except ValueError as exc:
        raise BadRequestException(str(exc))
