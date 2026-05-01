from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, status

from src.container import get_di_container
from src.dtos.auth.req import (
    ForgotPasswordRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    VerifyEmailRequest,
)
from src.dtos.auth.res import UserMeResponse
from src.services.auth_service import AuthService
from src.shared.auth_deps import get_current_user
from src.shared.response.response_models import create_response

router = APIRouter()


def _get_auth_service() -> AuthService:
    return get_di_container().get("auth_service")


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    background_tasks: BackgroundTasks,
    service: AuthService = Depends(_get_auth_service),
):
    user = await service.register(body.name, body.email, body.password)
    await service.send_verification_email(user, background_tasks)
    return create_response(
        data={"id": str(user.id), "email": user.email},
        message="Registration successful. Please verify your email.",
    )


@router.post("/login")
async def login(
    body: LoginRequest,
    service: AuthService = Depends(_get_auth_service),
):
    tokens = await service.login(body.email, body.password)
    return create_response(data=tokens, message="Login successful")


@router.post("/refresh")
async def refresh(
    body: RefreshRequest,
    service: AuthService = Depends(_get_auth_service),
):
    tokens = await service.refresh_tokens(body.refresh_token)
    return create_response(data=tokens, message="Tokens refreshed")


@router.post("/verify-email")
async def verify_email(
    body: VerifyEmailRequest,
    service: AuthService = Depends(_get_auth_service),
):
    await service.verify_email(body.token)
    return create_response(message="Email verified successfully")


@router.post("/forgot-password")
async def forgot_password(
    body: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    service: AuthService = Depends(_get_auth_service),
):
    await service.forgot_password(body.email, background_tasks)
    return create_response(message="If that email exists, a reset link has been sent.")


@router.post("/reset-password")
async def reset_password(
    body: ResetPasswordRequest,
    service: AuthService = Depends(_get_auth_service),
):
    await service.reset_password(body.token, body.new_password)
    return create_response(message="Password reset successfully")


@router.post("/logout")
async def logout(
    body: RefreshRequest,
    service: AuthService = Depends(_get_auth_service),
):
    await service.logout(body.refresh_token)
    return create_response(message="Logged out successfully")


@router.get("/me")
async def get_me(current_user=Depends(get_current_user)):
    data = UserMeResponse.model_validate(current_user).model_dump()
    return create_response(data=data, message="Current user retrieved")
