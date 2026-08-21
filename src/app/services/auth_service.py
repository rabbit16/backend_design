from __future__ import annotations

import re
from datetime import UTC
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.exceptions import AppError
from src.app.db.models.user import User
from src.app.repositories.user_repository import UserRepository
from src.app.schemas.auth import (
    LoginResponse,
    OkResponse,
    SendSmsResponse,
    TokenPair,
    UserProfile,
)
from src.app.security.jwt import create_token_pair, decode_token, revoke_session
from src.app.security.password import hash_password, verify_password
from src.app.services.sms_service import SmsPurpose, SmsService
from src.app.utils.ids import new_user_id

PHONE_PATTERN = re.compile(r"^1\d{10}$")
MIN_PASSWORD_LENGTH = 6
Lang = Literal["zh", "en"]


def _validate_phone(phone: str) -> str:
    phone = phone.strip()
    if not PHONE_PATTERN.fullmatch(phone):
        raise AppError("手机号格式不正确", code="invalid_phone", status_code=400)
    return phone


def _validate_password(password: str) -> str:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise AppError(
            f"密码长度至少 {MIN_PASSWORD_LENGTH} 位",
            code="invalid_password",
            status_code=400,
        )
    return password


def _to_profile(user: User) -> UserProfile:
    created = user.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    else:
        created = created.astimezone(UTC)
    return UserProfile(
        id=user.id,
        phone=user.phone,
        display_name=user.display_name,
        preferred_lang=user.preferred_lang,  # type: ignore[arg-type]
        created_at=created.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


def _to_login_response(user: User) -> LoginResponse:
    access_token, refresh_token, expires_in = create_token_pair(user.id)
    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=expires_in,
        user=_to_profile(user),
    )


class AuthService:
    def __init__(self, session: AsyncSession, sms: SmsService | None = None) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.sms = sms or SmsService()

    async def send_sms(self, phone: str, purpose: SmsPurpose = "login") -> SendSmsResponse:
        phone = _validate_phone(phone)
        expire_in = self.sms.send_code(phone, purpose)
        return SendSmsResponse(ok=True, expire_in=expire_in)

    async def register(
        self,
        phone: str,
        code: str,
        password: str,
        display_name: str | None = None,
        preferred_lang: Lang = "zh",
    ) -> LoginResponse:
        phone = _validate_phone(phone)
        # 文档约定：注册校验失败用 401
        self.sms.verify_code(phone, code.strip(), purpose="register", status_code=401)

        existing = await self.users.get_by_phone(phone)
        if existing is not None and existing.deleted_at is None:
            raise AppError("手机号已注册", code="phone_already_registered", status_code=409)

        user = User(
            id=new_user_id(),
            phone=phone,
            password_hash=hash_password(_validate_password(password)),
            display_name=(display_name.strip() if display_name else None) or None,
            preferred_lang=preferred_lang,
            status="active",
        )
        await self.users.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return _to_login_response(user)

    async def login_sms(self, phone: str, code: str, password: str | None = None) -> LoginResponse:
        phone = _validate_phone(phone)
        self.sms.verify_code(phone, code.strip(), purpose="login")

        user = await self.users.get_by_phone(phone)
        if user is None:
            user = User(id=new_user_id(), phone=phone, preferred_lang="zh")
            if password:
                user.password_hash = hash_password(_validate_password(password))
            await self.users.add(user)
        elif password:
            user.password_hash = hash_password(_validate_password(password))

        await self.session.commit()
        await self.session.refresh(user)
        return _to_login_response(user)

    async def login_password(self, phone: str, password: str) -> LoginResponse:
        phone = _validate_phone(phone)
        user = await self.users.get_by_phone(phone)
        if user is None or not user.password_hash or not verify_password(password, user.password_hash):
            raise AppError("手机号或密码错误", code="invalid_credentials", status_code=401)
        return _to_login_response(user)

    async def change_password(
        self,
        user_id: str,
        new_password: str,
        old_password: str | None = None,
    ) -> OkResponse:
        user = await self.users.get_by_id(user_id)
        if user is None:
            raise AppError("用户不存在", code="user_not_found", status_code=404)

        new_password = _validate_password(new_password)
        if user.password_hash:
            if not old_password or not verify_password(old_password, user.password_hash):
                raise AppError("原密码错误", code="invalid_old_password", status_code=400)
        user.password_hash = hash_password(new_password)
        await self.session.commit()
        return OkResponse(ok=True)

    async def logout(self, session_id: str) -> OkResponse:
        revoke_session(session_id)
        return OkResponse(ok=True)

    async def refresh(self, refresh_token: str) -> TokenPair:
        payload = decode_token(refresh_token, expected_type="refresh")
        subject = payload.get("sub")
        if not isinstance(subject, str) or not subject:
            raise AppError("Invalid refresh token", code="invalid_token", status_code=401)

        old_sid = payload.get("sid")
        if isinstance(old_sid, str):
            revoke_session(old_sid)

        user = await self.users.get_by_id(subject)
        if user is None:
            raise AppError("用户不存在", code="user_not_found", status_code=401)

        access_token, new_refresh, expires_in = create_token_pair(user.id)
        return TokenPair(
            access_token=access_token,
            refresh_token=new_refresh,
            token_type="bearer",
            expires_in=expires_in,
        )

    async def get_me(self, user_id: str) -> UserProfile:
        user = await self.users.get_by_id(user_id)
        if user is None:
            raise AppError("用户不存在", code="user_not_found", status_code=404)
        return _to_profile(user)
