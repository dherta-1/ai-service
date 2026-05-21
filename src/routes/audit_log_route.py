from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from src.container import get_di_container
from src.dtos.audit_log.res import AuditLogResponse
from src.services.audit_log_service import AuditLogService
from src.shared.auth_deps import require_admin
from src.shared.response.response_models import create_paginated_response

router = APIRouter()


def _get_audit_log_service() -> AuditLogService:
    return get_di_container().get("audit_log_service")


@router.get("", dependencies=[Depends(require_admin)])
async def list_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    actor_type: Optional[str] = Query(None),
    actor_id: Optional[UUID] = Query(None),
    entity_type: Optional[str] = Query(None),
    action_type: Optional[str] = Query(None),
    service: AuditLogService = Depends(_get_audit_log_service),
):
    logs, total = service.list_logs(
        page=page,
        page_size=page_size,
        actor_type=actor_type,
        actor_id=actor_id,
        entity_type=entity_type,
        action_type=action_type,
    )
    return create_paginated_response(
        data=[AuditLogResponse.model_validate(log).model_dump() for log in logs],
        total=total,
        page=page,
        per_page=page_size,
        message="Audit logs retrieved successfully",
    )
