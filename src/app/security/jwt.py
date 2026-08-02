from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import uuid4

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings
from app.core.exceptions import AppError

bearer_scheme = HTTPBearer(auto_error=False)

TokenType = Literal["access", "refresh"]

# 登出后按会话 sid 失效（进程内；生产可换 Redis）
_revoked_sessions: set[str] = set()


def clear_revoked_sessions() -> None:
    _revoked_sessions.clear()


def revoke_session(session_id: str) -> None:
    _revoked_sessions.add(session_id)


def is_session_revoked(session_id: str) -> bool:
    return session_id in _revoked_sessions


def _encode(payload: dict[str, Any]) -> str:
    settings = get_settings()
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_token_pair(subject: str) -> tuple[str, str, int]:
    """返回 (access_token, refresh_token, expires_in_seconds)。"""
    settings = get_settings()
    now = datetime.now(UTC)
    session_id = uuid4().hex
    access_expire = timedelta(minutes=settings.jwt_access_token_expire_minutes)
    refresh_expire = timedelta(days=settings.jwt_refresh_token_expire_days)
    expires_in = int(access_expire.total_seconds())

    access_token = _encode(
        {
            "sub": subject,
            "typ": "access",
            "sid": session_id,
            "jti": uuid4().hex,
            "iat": now,
            "exp": now + access_expire,
        }
    )
    refresh_token = _encode(
        {
            "sub": subject,
            "typ": "refresh",
            "sid": session_id,
            "jti": uuid4().hex,
            "iat": now,
            "exp": now + refresh_expire,
        }
    )
    return access_token, refresh_token, expires_in


def create_access_token(subject: str, claims: dict[str, Any] | None = None) -> str:
    """兼容旧脚手架调用；新登录流程请用 create_token_pair。"""
    settings = get_settings()
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "typ": "access",
        "sid": uuid4().hex,
        "jti": uuid4().hex,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_access_token_expire_minutes),
    }
    if claims:
        payload.update(claims)
    return _encode(payload)


def decode_token(token: str, *, expected_type: TokenType | None = None) -> dict[str, Any]:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise AppError(
            "Invalid or expired token",
            code="invalid_token",
            status_code=401,
        ) from exc

    token_type = payload.get("typ")
    if expected_type is not None and token_type != expected_type:
        raise AppError("Invalid token type", code="invalid_token", status_code=401)

    session_id = payload.get("sid")
    if isinstance(session_id, str) and is_session_revoked(session_id):
        raise AppError("Token has been revoked", code="token_revoked", status_code=401)

    return payload


def decode_access_token(token: str) -> dict[str, Any]:
    return decode_token(token, expected_type="access")


async def get_current_subject(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> str:
    if credentials is None:
        raise AppError("Missing token", code="unauthorized", status_code=401)
    payload = decode_access_token(credentials.credentials)
    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject:
        raise AppError("Invalid token subject", code="invalid_token", status_code=401)
    return subject


async def get_current_session_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> str:
    if credentials is None:
        raise AppError("Missing token", code="unauthorized", status_code=401)
    payload = decode_access_token(credentials.credentials)
    session_id = payload.get("sid")
    if not isinstance(session_id, str) or not session_id:
        raise AppError("Invalid token session", code="invalid_token", status_code=401)
    return session_id
