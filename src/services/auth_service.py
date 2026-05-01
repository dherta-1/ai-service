from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional, Tuple
from uuid import UUID, uuid4

import bcrypt
from fastapi import BackgroundTasks
from jose import JWTError, jwt

from src.entities.user import User
from src.lib.cachedb.redis import CacheClient
from src.services.user_service import UserService
from src.settings import Settings
from src.shared.constants.user import Role
from src.shared.response.exception_handler import (
    BadRequestException,
    ConflictException,
    ForbiddenException,
    UnauthorizedException,
)

logger = logging.getLogger(__name__)

_REFRESH_KEY_PREFIX = "auth:refresh"
_EMAIL_PURPOSE_VERIFY = "verify"
_EMAIL_PURPOSE_RESET = "reset"


class AuthService:

    def __init__(self, user_service: UserService, cache: CacheClient, settings: Settings):
        self._users = user_service
        self._cache = cache
        self._settings = settings

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _hash_password(self, plain: str) -> str:
        # Truncate to 72 bytes as per bcrypt specification
        plain_bytes = plain.encode('utf-8')[:72]
        return bcrypt.hashpw(plain_bytes, bcrypt.gensalt(rounds=12)).decode('utf-8')

    def _verify_password(self, plain: str, hashed: str) -> bool:
        # Truncate to 72 bytes as per bcrypt specification
        plain_bytes = plain.encode('utf-8')[:72]
        hashed_bytes = hashed.encode('utf-8')
        return bcrypt.checkpw(plain_bytes, hashed_bytes)

    def _create_access_token(self, user_id: str, role: str) -> str:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=self._settings.access_token_expire_minutes
        )
        payload = {
            "sub": user_id,
            "role": role,
            "type": "access",
            "jti": str(uuid4()),
            "exp": expire,
        }
        return jwt.encode(payload, self._settings.jwt_secret_key, algorithm=self._settings.jwt_algorithm)

    def _create_refresh_token(self, user_id: str) -> Tuple[str, str]:
        jti = str(uuid4())
        expire = datetime.now(timezone.utc) + timedelta(
            days=self._settings.refresh_token_expire_days
        )
        payload = {
            "sub": user_id,
            "type": "refresh",
            "jti": jti,
            "exp": expire,
        }
        token = jwt.encode(payload, self._settings.jwt_secret_key, algorithm=self._settings.jwt_algorithm)
        ttl = self._settings.refresh_token_expire_days * 86400
        self._cache.set(f"{_REFRESH_KEY_PREFIX}:{user_id}:{jti}", "1", ttl=ttl)
        return token, jti

    def _create_email_token(self, user_id: str, purpose: Literal["verify", "reset"]) -> str:
        ttl_hours = 24 if purpose == _EMAIL_PURPOSE_VERIFY else 1
        expire = datetime.now(timezone.utc) + timedelta(hours=ttl_hours)
        payload = {
            "sub": user_id,
            "purpose": purpose,
            "jti": str(uuid4()),
            "exp": expire,
        }
        return jwt.encode(payload, self._settings.jwt_secret_key, algorithm=self._settings.jwt_algorithm)

    def decode_token(self, token: str) -> dict:
        try:
            return jwt.decode(token, self._settings.jwt_secret_key, algorithms=[self._settings.jwt_algorithm])
        except JWTError as exc:
            raise UnauthorizedException("Invalid or expired token") from exc

    def _send_email_background(
        self,
        background_tasks: BackgroundTasks,
        to: str,
        subject: str,
        body_html: str,
    ) -> None:
        background_tasks.add_task(self._do_send_email, to, subject, body_html)

    def _do_send_email(self, to: str, subject: str, body_html: str) -> None:
        try:
            import smtplib
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText

            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"{self._settings.smtp_from_name} <{self._settings.smtp_from_email}>"
            msg["To"] = to
            msg.attach(MIMEText(body_html, "html"))

            with smtplib.SMTP(self._settings.smtp_host, self._settings.smtp_port) as server:
                server.starttls()
                if self._settings.smtp_username and self._settings.smtp_password:
                    server.login(self._settings.smtp_username, self._settings.smtp_password)
                server.sendmail(self._settings.smtp_from_email, to, msg.as_string())

            logger.info("Email sent to %s: %s", to, subject)
        except Exception as exc:
            logger.error("Failed to send email to %s: %s", to, exc)

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    async def register(self, name: str, email: str, password: str) -> User:
        existing = self._users.get_by_email(email)
        if existing:
            raise ConflictException("Email already registered")
        user = self._users.repo.create(
            name=name,
            email=email,
            password_hash=self._hash_password(password),
            role=Role.user.value,
            is_email_verified=False,
        )
        return user

    async def send_verification_email(self, user: User, background_tasks: BackgroundTasks) -> None:
        token = self._create_email_token(str(user.id), _EMAIL_PURPOSE_VERIFY)
        link = f"{self._settings.frontend_url}/verify-email?token={token}"
        body = f"""
        <p>Hi {user.name},</p>
        <p>Please verify your email by clicking the link below:</p>
        <p><a href="{link}">{link}</a></p>
        <p>This link expires in 24 hours.</p>
        """
        self._users.repo.update(user.id, email_verification_sent_at=datetime.utcnow())
        self._send_email_background(background_tasks, user.email, "Verify your email", body)

    async def verify_email(self, token: str) -> User:
        payload = self.decode_token(token)
        if payload.get("purpose") != _EMAIL_PURPOSE_VERIFY:
            raise BadRequestException("Invalid token purpose")
        user = self._users.get_by_id(UUID(payload["sub"]))
        if not user:
            raise UnauthorizedException("User not found")
        self._users.mark_email_verified(user.id)
        return user

    async def login(self, email: str, password: str) -> dict:
        user = self._users.get_by_email(email)
        if not user or not user.password_hash:
            raise UnauthorizedException("Invalid credentials")
        if not self._verify_password(password, user.password_hash):
            raise UnauthorizedException("Invalid credentials")
        if not user.is_email_verified:
            raise ForbiddenException("Email not verified. Please check your inbox.")

        access_token = self._create_access_token(str(user.id), user.role)
        refresh_token, _ = self._create_refresh_token(str(user.id))
        self._users.update_last_login(user.id)

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
        }

    async def refresh_tokens(self, refresh_token: str) -> dict:
        payload = self.decode_token(refresh_token)
        if payload.get("type") != "refresh":
            raise UnauthorizedException("Invalid token type")

        user_id = payload["sub"]
        jti = payload["jti"]
        redis_key = f"{_REFRESH_KEY_PREFIX}:{user_id}:{jti}"

        if not self._cache.exists(redis_key):
            raise UnauthorizedException("Refresh token reused or expired")

        self._cache.delete(redis_key)

        user = self._users.get_by_id(UUID(user_id))
        if not user:
            raise UnauthorizedException("User not found")

        access_token = self._create_access_token(str(user.id), user.role)
        new_refresh_token, _ = self._create_refresh_token(str(user.id))

        return {
            "access_token": access_token,
            "refresh_token": new_refresh_token,
            "token_type": "bearer",
        }

    async def logout(self, refresh_token: str) -> None:
        try:
            payload = self.decode_token(refresh_token)
            user_id = payload.get("sub")
            jti = payload.get("jti")
            if user_id and jti:
                self._cache.delete(f"{_REFRESH_KEY_PREFIX}:{user_id}:{jti}")
        except Exception:
            pass  # Logout is always successful from the client's perspective

    async def forgot_password(self, email: str, background_tasks: BackgroundTasks) -> None:
        user = self._users.get_by_email(email)
        if not user:
            return  # No user enumeration
        token = self._create_email_token(str(user.id), _EMAIL_PURPOSE_RESET)
        link = f"{self._settings.frontend_url}/reset-password?token={token}"
        body = f"""
        <p>Hi {user.name},</p>
        <p>Reset your password by clicking the link below:</p>
        <p><a href="{link}">{link}</a></p>
        <p>This link expires in 1 hour. If you did not request this, ignore this email.</p>
        """
        self._send_email_background(background_tasks, user.email, "Reset your password", body)

    async def reset_password(self, token: str, new_password: str) -> None:
        payload = self.decode_token(token)
        if payload.get("purpose") != _EMAIL_PURPOSE_RESET:
            raise BadRequestException("Invalid token purpose")
        user = self._users.get_by_id(UUID(payload["sub"]))
        if not user:
            raise UnauthorizedException("User not found")
        self._users.set_password_hash(user.id, self._hash_password(new_password))
