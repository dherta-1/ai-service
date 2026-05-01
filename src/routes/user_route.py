from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from src.container import get_di_container
from src.dtos.user.req import UpdateUserRequest
from src.dtos.user.res import UserResponse
from src.services.user_service import UserService
from src.shared.auth_deps import require_admin
from src.shared.response.exception_handler import NotFoundException
from src.shared.response.response_models import create_paginated_response, create_response

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
):
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise NotFoundException("No fields to update")
    user = service.update_user(user_id, **updates)
    if not user:
        raise NotFoundException("User not found")
    return create_response(
        data=UserResponse.model_validate(user).model_dump(),
        message="User updated successfully",
    )


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_admin)])
async def delete_user(
    user_id: UUID,
    service: UserService = Depends(_get_user_service),
):
    success = service.delete_user(user_id)
    if not success:
        raise NotFoundException("User not found")
