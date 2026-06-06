from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status, Request

from src.container import get_di_container
from src.dtos.user.req import UpdateUserRequest, ResetPasswordRequest
from src.dtos.user.res import UserResponse
from src.entities.user import User
from src.services.user_service import UserService
from src.shared.auth_deps import require_admin
from src.shared.response.exception_handler import NotFoundException
from src.shared.response.response_models import (
    create_paginated_response,
    create_response,
)
from src.shared.logger.audit_logger import log_audit
from src.shared.constants.audit_log import ActionType, ActorType, EntityType
from src.shared.helpers.dto_utils import to_dict

router = APIRouter()


def _get_user_service() -> UserService:
    return get_di_container().get("user_service")


@router.get("", dependencies=[Depends(require_admin)])
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    service: UserService = Depends(_get_user_service),
):
    users, total = service.list_users(page, page_size)
    return create_paginated_response(
        data=[UserResponse.model_validate(u).model_dump() for u in users],
        total=total,
        page=page,
        per_page=page_size,
        message="Users retrieved successfully",
    )


@router.get("/{user_id}", dependencies=[Depends(require_admin)])
async def get_user(
    user_id: UUID,
    service: UserService = Depends(_get_user_service),
    _current_user: User = Depends(require_admin),
):
    user = service.get_by_id(user_id)
    if not user:
        raise NotFoundException("User not found")
    return create_response(
        data=UserResponse.model_validate(user).model_dump(),
        message="User retrieved successfully",
    )


@router.put("/{user_id}", dependencies=[Depends(require_admin)])
async def update_user(
    user_id: UUID,
    body: UpdateUserRequest,
    service: UserService = Depends(_get_user_service),
    request: Request = None,
    _current_user: User = Depends(require_admin),
):
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise NotFoundException("No fields to update")

    before_user = service.get_by_id(user_id)
    user = service.update_user(user_id, **updates)
    if not user:
        raise NotFoundException("User not found")

    log_audit(
        actor_type=ActorType.admin,
        entity_type=EntityType.user,
        action_type=ActionType.UPDATE,
        actor_id=_current_user.id,
        entity_id=user_id,
        before_data={"email": before_user.email} if before_user else None,
        after_data={"email": user.email},
        request_ip=request.client.host if request else None,
    )

    return create_response(
        data=UserResponse.model_validate(user).model_dump(),
        message="User updated successfully",
    )


@router.post("/{user_id}/reset-password", dependencies=[Depends(require_admin)])
async def reset_user_password(
    user_id: UUID,
    body: ResetPasswordRequest,
    service: UserService = Depends(_get_user_service),
    request: Request = None,
    _current_user: User = Depends(require_admin),
):
    user = service.get_by_id(user_id)
    if not user:
        raise NotFoundException("User not found")

    service.reset_password(user_id, body.new_password)

    log_audit(
        actor_type=ActorType.admin,
        entity_type=EntityType.user,
        action_type=ActionType.UPDATE,
        actor_id=_current_user.id,
        entity_id=user_id,
        before_data={"email": user.email},
        after_data={"password_reset": True},
        request_ip=request.client.host if request else None,
    )

    return create_response(
        data={"id": str(user_id), "reset": True},
        message="Password reset successfully",
    )


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_user(
    user_id: UUID,
    service: UserService = Depends(_get_user_service),
    request: Request = None,
    _current_user: User = Depends(require_admin),
):
    user_to_delete = service.get_by_id(user_id)
    success = service.delete_user(user_id)
    if not success:
        raise NotFoundException("User not found")

    if user_to_delete:
        log_audit(
            actor_type=ActorType.admin,
            entity_type=EntityType.user,
            action_type=ActionType.DELETE,
            actor_id=_current_user.id,
            entity_id=user_id,
            before_data={"email": user_to_delete.email},
            after_data=None,
            request_ip=request.client.host if request else None,
        )
