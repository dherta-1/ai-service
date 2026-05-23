from __future__ import annotations

import json
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import Response

from src.container import get_di_container
from src.entities.user import User
from src.shared.auth_deps import get_current_user
from src.shared.response.exception_handler import (
    NotFoundException,
    BadRequestException,
    ConflictException,
    UnauthorizedException,
)
from src.shared.logger.audit_logger import log_audit
from src.shared.constants.audit_log import ActionType, ActorType, EntityType
from src.dtos.exam.req import (
    CreateManualExamRequest,
    GenerateBaseExamRequest,
    ReplaceQuestionRequest,
    SaveExamTemplateRequest,
    UpdateExamStatusRequest,
    UpdateManualExamRequest,
)
from src.dtos.exam_attempt.req import (
    CreateExamAttemptRequest,
    SaveAnswerRequest,
    SubmitExamRequest,
)
from src.services.exam_service import ExamService
from src.services.exam_attempt_service import ExamAttemptService
from src.services.core.base_exam_generation_service import BaseExamGenerationService
from src.services.core.exam_instance_export_service import ExamInstanceExportService
from src.services.core.exam_mutation_service import ExamMutationService
from src.shared.helpers.dto_utils import to_dict
from src.shared.response.response_models import (
    create_response,
    create_paginated_response,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def get_exam_service() -> ExamService:
    return get_di_container().resolve(ExamService)


def get_base_service() -> BaseExamGenerationService:
    return get_di_container().resolve(BaseExamGenerationService)


def get_export_service() -> ExamInstanceExportService:
    return get_di_container().resolve(ExamInstanceExportService)


def get_mutation_service() -> ExamMutationService:
    return get_di_container().resolve(ExamMutationService)


def get_attempt_service() -> ExamAttemptService:
    return get_di_container().resolve(ExamAttemptService)


# ------------------------------------------------------------------
# Route Organization Guide:
# 1. Templates (CRUD)
# 2. Base Exam Generation
# 3. Manual Exam Instances (CRUD)
# 4. Exam Instance Details & Operations (nested routes with specific paths first)
# 5. Exam Attempts (CRUD)
# 6. Standalone Instances List (most general, last)
# ------------------------------------------------------------------

# ------------------------------------------------------------------
# Templates (CRUD)
# ------------------------------------------------------------------


@router.post("/templates")
async def save_template(
    body: SaveExamTemplateRequest,
    current_user: User = Depends(get_current_user),
    service: ExamService = Depends(get_exam_service),
    request: Request = None,
):
    """Create or update an exam template with optional default section configs."""
    try:
        is_update = body.template_id is not None
        old_template = service.get_template(body.template_id) if is_update else None

        template = service.save_template(
            name=body.name,
            subject=body.subject,
            generation_config=body.generation_config,
            template_id=body.template_id,
            created_by_id=current_user.id,
        )

        log_audit(
            actor_type=ActorType.user,
            entity_type=EntityType.exam_template,
            action_type=ActionType.UPDATE if is_update else ActionType.CREATE,
            actor_id=current_user.id,
            entity_id=template.id,
            before_data=(
                {"name": old_template.name, "subject": old_template.subject}
                if old_template
                else None
            ),
            after_data={"name": template.name, "subject": template.subject},
            request_ip=request.client.host if request else None,
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
    current_user: User = Depends(get_current_user),
    service: ExamService = Depends(get_exam_service),
):
    """List exam templates, optionally filtered by subject.

    - Admin: returns all templates
    - Non-admin: returns only their own templates
    """
    user_id = None if current_user.role == "admin" else current_user.id
    templates = service.list_templates(subject=subject, user_id=user_id)
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
    current_user: User = Depends(get_current_user),
    service: ExamService = Depends(get_exam_service),
):
    """Get a single exam template by ID.

    - Admin: can get any template
    - Non-admin: can only get their own templates
    """
    template = service.get_template(template_id)
    if not template:
        raise NotFoundException("Template not found")

    if current_user.role != "admin" and template.created_by_id != current_user.id:
        raise NotFoundException("Template not found")

    data = to_dict(template)
    if template.generation_config:
        try:
            data["generation_config"] = json.loads(template.generation_config)
        except (ValueError, TypeError):
            data["generation_config"] = None
    return create_response(data=data, message="Template retrieved successfully")


@router.get("/templates/{template_id}/instances")
async def list_instances_by_template(
    template_id: UUID,
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    service: ExamService = Depends(get_exam_service),
):
    """List exam instances for a template with pagination.

    - Admin: returns all instances from template
    - Non-admin: returns only their own instances from template
    """
    template = service.get_template(template_id)
    if not template:
        raise NotFoundException("Template not found")

    if current_user.role != "admin" and template.created_by_id != current_user.id:
        raise NotFoundException("Template not found")

    instances, total = service.get_instances_by_template_paginated(
        template_id=template_id,
        page=page,
        per_page=per_page,
    )

    data = []
    for instance in instances:
        instance_data = service.build_exam_response_data(instance)
        instance_data.pop("_total_questions", None)
        data.append(instance_data)

    return create_paginated_response(
        data=data,
        total=total,
        page=page,
        per_page=per_page,
        message=f"Retrieved {len(data)} exam instances from template",
    )


@router.post("/templates/{template_id}/attempts")
async def create_exam_attempt(
    template_id: UUID,
    body: CreateExamAttemptRequest,
    current_user: User = Depends(get_current_user),
    service: ExamAttemptService = Depends(get_attempt_service),
):
    """Create an exam attempt from a template (new or random existing instance)."""
    try:
        payload = service.start_attempt(
            template_id=template_id,
            user=current_user,
            use_existing_instance=body.use_existing_instance or False,
        )
        return create_response(data=payload, message="Exam attempt created")
    except ValueError as exc:
        raise BadRequestException(str(exc))


# ------------------------------------------------------------------
# Base Exam Generation
# ------------------------------------------------------------------


@router.post("/generate-base")
async def generate_base_exam(
    body: GenerateBaseExamRequest,
    current_user: User = Depends(get_current_user),
    base_service: BaseExamGenerationService = Depends(get_base_service),
    exam_service: ExamService = Depends(get_exam_service),
):
    """Generate a base exam instance from section configs.

    - template_id given → regenerate (sections override template defaults)
    - template_id null  → one-off exam (subject + sections required)
    """
    try:
        exam = base_service.generate_base_exam(
            sections=body.sections,
            template_id=body.template_id,
            subject=body.subject,
            created_by_id=current_user.id,
        )
        logger.info(f"Generated exam {exam.id}")
        exam_data = exam_service.build_exam_response_data(exam)
        logger.info(f"Exam data sections: {len(exam_data.get('sections', []))}")
        for sec in exam_data.get("sections", []):
            logger.info(
                f"  Section {sec['name']}: {len(sec.get('questions', []))} questions"
            )
        total_questions = exam_data.pop("_total_questions", 0)
        return create_response(
            data={"exam_instance": exam_data, "total_questions": total_questions},
            message="Base exam generated successfully",
        )
    except ValueError as exc:
        raise BadRequestException(str(exc))


# ------------------------------------------------------------------
# Exam Attempts (CRUD)
# ------------------------------------------------------------------


@router.get("/attempts")
async def list_my_attempts(
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    service: ExamAttemptService = Depends(get_attempt_service),
):
    """List the current user's exam attempts with template info and pagination."""
    data, total = service.list_user_attempts(
        user=current_user, page=page, per_page=per_page
    )
    return create_paginated_response(
        data=data,
        total=total,
        page=page,
        per_page=per_page,
        message="Attempts retrieved successfully",
    )


@router.get("/attempts/current")
async def get_current_attempt(
    current_user: User = Depends(get_current_user),
    service: ExamAttemptService = Depends(get_attempt_service),
    attempt_token: str = Header(..., alias="X-Attempt-Token"),
):
    """Get current exam attempt by attempt token."""
    try:
        payload = service.get_current_attempt(attempt_token, current_user)
        return create_response(data=payload, message="Attempt retrieved successfully")
    except ValueError as exc:
        message = str(exc)
        if "token" in message:
            raise UnauthorizedException(message)
        if "submitted" in message:
            raise ConflictException(message)
        if "not found" in message:
            raise NotFoundException(message)
        raise BadRequestException(message)


@router.get("/attempts/{attempt_id}")
async def get_attempt_detail(
    attempt_id: UUID,
    current_user: User = Depends(get_current_user),
    service: ExamAttemptService = Depends(get_attempt_service),
):
    """Get detailed answer history for a submitted exam attempt."""
    try:
        data = service.get_attempt_detail(attempt_id, current_user)
        return create_response(data=data, message="Attempt detail retrieved")
    except ValueError as exc:
        message = str(exc)
        if "not found" in message:
            raise NotFoundException(message)
        raise BadRequestException(message)


@router.post("/attempts/{attempt_token}/save-answer")
async def save_attempt_answer(
    attempt_token: str,
    body: SaveAnswerRequest,
    current_user: User = Depends(get_current_user),
    service: ExamAttemptService = Depends(get_attempt_service),
):
    """Save a single answer during an exam attempt (auto-save)."""
    try:
        service.save_answer(
            token=attempt_token,
            user=current_user,
            question_token=body.question_token,
            selected_option_token=body.selected_option_token,
        )
        return Response(status_code=204)
    except ValueError as exc:
        message = str(exc)
        if "token" in message:
            raise UnauthorizedException(message)
        if "submitted" in message:
            raise ConflictException(message)
        if "not found" in message:
            raise NotFoundException(message)
        raise BadRequestException(message)


@router.post("/attempts/{attempt_token}/submit")
async def submit_exam_attempt(
    attempt_token: str,
    body: SubmitExamRequest,
    current_user: User = Depends(get_current_user),
    service: ExamAttemptService = Depends(get_attempt_service),
):
    """Submit an exam attempt and score answers."""
    try:
        payload = service.submit_attempt(attempt_token, current_user, body.answers)
        return create_response(data=payload, message="Exam submitted successfully")
    except ValueError as exc:
        message = str(exc)
        if "token" in message:
            raise UnauthorizedException(message)
        if "submitted" in message:
            raise ConflictException(message)
        if "not found" in message:
            raise NotFoundException(message)
        raise BadRequestException(message)


@router.get("/attempts/{attempt_token}/result")
async def get_exam_result(
    attempt_token: str,
    current_user: User = Depends(get_current_user),
    service: ExamAttemptService = Depends(get_attempt_service),
):
    """Get exam result details for a submitted attempt."""
    try:
        payload = service.get_result(attempt_token, current_user)
        return create_response(
            data=payload, message="Exam result retrieved successfully"
        )
    except ValueError as exc:
        message = str(exc)
        if "token" in message:
            raise UnauthorizedException(message)
        if "submitted" in message:
            raise ConflictException(message)
        if "not found" in message:
            raise NotFoundException(message)
        raise BadRequestException(message)


# ------------------------------------------------------------------
# Manual Exam Instance Mutation
# ------------------------------------------------------------------


# ------------------------------------------------------------------
# Exam instances
# ------------------------------------------------------------------


@router.get("/instances")
async def list_standalone_instances(
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    service: ExamService = Depends(get_exam_service),
):
    """List standalone exam instances (not created from a template).

    Standalone exams have exam_template_id = None.

    - Admin: returns all standalone instances
    - Non-admin: returns only their own standalone instances
    """
    instances, total = service.get_standalone_instances_paginated(
        user_id=None if current_user.role == "admin" else current_user.id,
        page=page,
        per_page=per_page,
    )

    data = []
    for instance in instances:
        instance_data = service.build_exam_response_data(instance)
        instance_data.pop("_total_questions", None)
        data.append(instance_data)

    return create_paginated_response(
        data=data,
        total=total,
        page=page,
        per_page=per_page,
        message=f"Retrieved {len(data)} standalone exam instances",
    )


@router.post("/instances/manual")
async def create_manual_exam(
    body: CreateManualExamRequest,
    current_user: User = Depends(get_current_user),
    mutation_service: ExamMutationService = Depends(get_mutation_service),
    exam_service: ExamService = Depends(get_exam_service),
    request: Request = None,
):
    """Create a manual exam instance from explicit question lists (no template)."""
    try:
        exam = mutation_service.create_manual_exam(body, created_by_id=current_user.id)
        exam_data = exam_service.build_exam_response_data(exam)
        exam_data.pop("_total_questions", None)

        log_audit(
            actor_type=(
                ActorType.admin if current_user.role == "admin" else ActorType.user
            ),
            entity_type=EntityType.exam_instance,
            action_type=ActionType.CREATE,
            actor_id=current_user.id,
            entity_id=exam.id,
            after_data={"exam_test_code": exam.exam_test_code},
            request_ip=request.client.host if request else None,
        )

        return create_response(
            data=exam_data, message="Manual exam created successfully"
        )
    except ValueError as exc:
        raise BadRequestException(str(exc))


@router.get("/instances/{exam_id}")
async def get_exam_instance(
    exam_id: UUID,
    current_user: User = Depends(get_current_user),
    service: ExamService = Depends(get_exam_service),
):
    """Get a full exam instance with all sections and questions.

    - Admin: can get any exam
    - Non-admin: can only get their own exams
    """
    exam = service.get_exam_instance(exam_id)
    if not exam:
        raise NotFoundException("Exam instance not found")

    if current_user.role != "admin" and exam.created_by_id != current_user.id:
        raise NotFoundException("Exam instance not found")

    exam_data = service.build_exam_response_data(exam)
    exam_data.pop("_total_questions", None)
    return create_response(
        data=exam_data, message="Exam instance retrieved successfully"
    )


@router.patch("/instances/{exam_id}/manual")
async def update_manual_exam(
    exam_id: UUID,
    body: UpdateManualExamRequest,
    current_user: User = Depends(get_current_user),
    mutation_service: ExamMutationService = Depends(get_mutation_service),
    exam_service: ExamService = Depends(get_exam_service),
    request: Request = None,
):
    """Replace sections/questions of an existing exam instance (manual or generated)."""
    try:
        existing = exam_service.get_exam_instance(exam_id)
        if not existing:
            raise NotFoundException("Exam instance not found")
        if current_user.role != "admin" and existing.created_by_id != current_user.id:
            raise NotFoundException("Exam instance not found")

        exam = mutation_service.update_manual_exam(exam_id, body)
        exam_data = exam_service.build_exam_response_data(exam)
        exam_data.pop("_total_questions", None)

        log_audit(
            actor_type=(
                ActorType.admin if current_user.role == "admin" else ActorType.user
            ),
            entity_type=EntityType.exam_instance,
            action_type=ActionType.UPDATE,
            actor_id=current_user.id,
            entity_id=exam_id,
            after_data={"exam_test_code": exam.exam_test_code},
            request_ip=request.client.host if request else None,
        )

        return create_response(
            data=exam_data, message="Manual exam updated successfully"
        )
    except (NotFoundException, BadRequestException):
        raise
    except ValueError as exc:
        raise BadRequestException(str(exc))


@router.get("/instances/{exam_id}/versions")
async def get_exam_versions(
    exam_id: UUID,
    current_user: User = Depends(get_current_user),
    service: ExamService = Depends(get_exam_service),
):
    """List all versions generated from a base exam.

    - Admin: can get versions from any exam
    - Non-admin: can only get versions from their own exams
    """
    exam = service.get_exam_instance(exam_id)
    if not exam:
        raise NotFoundException("Exam instance not found")

    if current_user.role != "admin" and exam.created_by_id != current_user.id:
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


@router.post("/instances/{instance_id}/attempts")
async def create_exam_attempt_from_instance(
    instance_id: UUID,
    current_user: User = Depends(get_current_user),
    service: ExamAttemptService = Depends(get_attempt_service),
):
    """Create an exam attempt directly from a specific exam instance."""
    try:
        payload = service.start_attempt_from_instance(
            instance_id=instance_id,
            user=current_user,
        )
        return create_response(data=payload, message="Exam attempt created")
    except ValueError as exc:
        raise BadRequestException(str(exc))


@router.patch("/instances/{exam_id}/status")
async def update_exam_status(
    exam_id: UUID,
    body: UpdateExamStatusRequest,
    current_user: User = Depends(get_current_user),
    service: ExamService = Depends(get_exam_service),
    request: Request = None,
):
    """Update exam instance status. 0=pending, 1=accepted, 2=rejected.

    - Admin: can update any exam
    - Non-admin: can only update their own exams
    """
    try:
        exam = service.get_exam_instance(exam_id)
        if not exam:
            raise ValueError(f"Exam instance {exam_id} not found")

        if current_user.role != "admin" and exam.created_by_id != current_user.id:
            raise ValueError(f"Exam instance {exam_id} not found")

        old_status = exam.status
        exam = service.update_exam_status(exam_id, body.status)

        log_audit(
            actor_type=(
                ActorType.admin if current_user.role == "admin" else ActorType.user
            ),
            entity_type=EntityType.exam_instance,
            action_type=ActionType.UPDATE,
            actor_id=current_user.id,
            entity_id=exam_id,
            before_data={"status": old_status},
            after_data={"status": exam.status},
            request_ip=request.client.host if request else None,
        )

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
    current_user: User = Depends(get_current_user),
    service: ExamService = Depends(get_exam_service),
    request: Request = None,
):
    """Replace a question variant in an exam with another from the same group.

    - Admin: can replace questions in any exam
    - Non-admin: can only replace questions in their own exams
    """
    try:
        exam = service.get_exam_instance(exam_id)
        if not exam:
            raise ValueError(f"Exam instance {exam_id} not found")

        if current_user.role != "admin" and exam.created_by_id != current_user.id:
            raise ValueError(f"Exam instance {exam_id} not found")

        qet = service.replace_question(
            exam_instance_id=exam_id,
            qet_id=body.question_exam_test_id,
            new_question_id=body.new_question_id,
        )

        log_audit(
            actor_type=(
                ActorType.admin if current_user.role == "admin" else ActorType.user
            ),
            entity_type=EntityType.exam_instance,
            action_type=ActionType.REPLACE,
            actor_id=current_user.id,
            entity_id=exam_id,
            before_data={"question_exam_test_id": str(body.question_exam_test_id)},
            after_data={
                "question_exam_test_id": str(qet.id),
                "new_question_id": str(body.new_question_id),
            },
            request_ip=request.client.host if request else None,
        )

        return create_response(
            data={
                "question_exam_test_id": str(qet.id),
                "question_id": qet.question_id,
                "answer_order": (
                    json.loads(qet.answer_order) if qet.answer_order else None
                ),
            },
            message="Question replaced successfully",
        )
    except ValueError as exc:
        raise BadRequestException(str(exc))


# ------------------------------------------------------------------
# Export
# ------------------------------------------------------------------


@router.get("/instances/{exam_id}/export")
async def export_exam_instance(
    exam_id: UUID,
    school_name: str = Query(
        default="TRƯỜNG ĐẠI HỌC", description="School / institution name for header"
    ),
    subject_label: str = Query(default="", description="Subject display name"),
    duration_minutes: int = Query(default=90, description="Exam duration in minutes"),
    include_answer_key: bool = Query(
        default=True, description="Append answer key page"
    ),
    force_regenerate: bool = Query(
        default=False, description="Deprecated - always performs full export"
    ),
    current_user: User = Depends(get_current_user),
    exam_service: ExamService = Depends(get_exam_service),
    export_service: ExamInstanceExportService = Depends(get_export_service),
):
    """Export an exam instance as a downloadable PDF with full regeneration.

    Always performs a fresh PDF build. If the exam was previously exported,
    the old PDF and its metadata are deleted before creating the new one.

    Streams the PDF directly.

    - Admin: can export any exam
    - Non-admin: can only export their own exams
    """
    exam = exam_service.get_exam_instance(exam_id)
    if not exam:
        raise NotFoundException("Exam instance not found")

    if current_user.role != "admin" and exam.created_by_id != current_user.id:
        raise NotFoundException("Exam instance not found")

    try:
        pdf_bytes, file_id = await export_service.export(
            exam_id=exam_id,
            school_name=school_name,
            subject_label=subject_label,
            duration_minutes=duration_minutes,
            include_answer_key=include_answer_key,
            force_regenerate=force_regenerate,
        )
        exam_code = exam.exam_test_code or str(exam_id)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{exam_code}.pdf"',
                "X-File-Id": file_id,
            },
        )
    except ValueError as exc:
        raise BadRequestException(str(exc))


@router.get("/instances/{exam_id}/export/url")
async def get_exam_export_url(
    exam_id: UUID,
    expires_in: int = Query(
        default=3600, description="Presigned URL expiry in seconds"
    ),
    current_user: User = Depends(get_current_user),
    exam_service: ExamService = Depends(get_exam_service),
    export_service: ExamInstanceExportService = Depends(get_export_service),
):
    """Get a presigned download URL for an already-exported exam PDF.

    Returns 404 if the exam has not been exported yet (call /export first).
    """
    exam = exam_service.get_exam_instance(exam_id)
    if not exam:
        raise NotFoundException("Exam instance not found")

    if current_user.role != "admin" and exam.created_by_id != current_user.id:
        raise NotFoundException("Exam instance not found")

    url = export_service.get_download_url(exam_id=exam_id, expires_in=expires_in)
    if not url:
        raise NotFoundException("Exam has not been exported yet. Call /export first.")

    return create_response(
        data={"presigned_url": url, "expires_in": expires_in},
        message="Export URL retrieved successfully",
    )
