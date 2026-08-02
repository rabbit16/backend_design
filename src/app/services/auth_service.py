from __future__ import annotations

import re
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.db.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.auth import (
    LoginResponse,
    OkResponse,
    SendSmsResponse,
    TokenPair,
    UserProfile,
)
from app.security.jwt import create_token_pair, decode_token, revoke_session
from app.security.password import hash_password, verify_password
from app.services.sms_service import SmsService
from app.utils.ids import new_user_id

PHONE_PATTERN = re.compile(r"^1\d{10}$")
MIN_PASSWORD_LENGTH = 6


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

    async def send_sms(self, phone: str) -> SendSmsResponse:
        phone = _validate_phone(phone)
        expire_in = self.sms.send_code(phone)
        return SendSmsResponse(ok=True, expire_in=expire_in)

    async def login_sms(self, phone: str, code: str, password: str | None = None) -> LoginResponse:
        phone = _validate_phone(phone)
        self.sms.verify_code(phone, code.strip())

        user = await self.users.get_by_phone(phone)
        if user is None:
            user = User(id=new_user_id(), phone=phone, preferred_lang="zh")
            if password:
                user.password_hash = hash_password(_validate_password(password))
            await self.users.add(user)
        elif password:
            # 已有用户：验证码登录时可设置/更新密码
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

        # 旧会话作废，签发新会话
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
