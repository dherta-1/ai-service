from __future__ import annotations

from typing import Optional

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.container import get_di_container
from src.entities.user import User
from src.services.auth_service import AuthService
from src.services.user_service import UserService
from src.shared.constants.user import Role
from src.shared.response.exception_handler import ForbiddenException, UnauthorizedException

_bearer = HTTPBearer(auto_error=False)


def _get_auth_service() -> AuthService:
    return get_di_container().get("auth_service")


def _get_user_service() -> UserService:
    return get_di_container().get("user_service")


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    auth_service: AuthService = Depends(_get_auth_service),
    user_service: UserService = Depends(_get_user_service),
) -> User:
    if not credentials:
        raise UnauthorizedException("Missing authentication token")
    payload = auth_service.decode_token(credentials.credentials)
    if payload.get("type") != "access":
        raise UnauthorizedException("Invalid token type")
    from uuid import UUID
    user = user_service.get_by_id(UUID(payload["sub"]))
    if not user:
        raise UnauthorizedException("User not found")
    return user


async def require_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    if current_user.role != Role.admin.value:
        raise ForbiddenException("Admin access required")
    return current_user


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    auth_service: AuthService = Depends(_get_auth_service),
    user_service: UserService = Depends(_get_user_service),
) -> Optional[User]:
    if not credentials:
        return None
    try:
        payload = auth_service.decode_token(credentials.credentials)
        if payload.get("type") != "access":
            return None
        from uuid import UUID
        return user_service.get_by_id(UUID(payload["sub"]))
    except Exception:
        return None
