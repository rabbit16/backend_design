from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginResponse,
    OkResponse,
    PasswordLoginRequest,
    RefreshTokenRequest,
    SendSmsRequest,
    SendSmsResponse,
    SmsLoginRequest,
    TokenPair,
)
from app.security.jwt import get_current_session_id, get_current_subject
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


def _auth_service(session: Annotated[AsyncSession, Depends(get_session)]) -> AuthService:
    return AuthService(session)


@router.post("/sms/send", response_model=SendSmsResponse)
async def send_sms(
    payload: SendSmsRequest,
    service: Annotated[AuthService, Depends(_auth_service)],
) -> SendSmsResponse:
    return await service.send_sms(payload.phone)


@router.post("/login/sms", response_model=LoginResponse)
async def login_sms(
    payload: SmsLoginRequest,
    service: Annotated[AuthService, Depends(_auth_service)],
) -> LoginResponse:
    return await service.login_sms(payload.phone, payload.code, payload.password)


@router.post("/login/password", response_model=LoginResponse)
async def login_password(
    payload: PasswordLoginRequest,
    service: Annotated[AuthService, Depends(_auth_service)],
) -> LoginResponse:
    return await service.login_password(payload.phone, payload.password)


@router.post("/password", response_model=OkResponse)
async def change_password(
    payload: ChangePasswordRequest,
    service: Annotated[AuthService, Depends(_auth_service)],
    user_id: Annotated[str, Depends(get_current_subject)],
) -> OkResponse:
    return await service.change_password(user_id, payload.new_password, payload.old_password)


@router.post("/logout", response_model=OkResponse)
async def logout(
    service: Annotated[AuthService, Depends(_auth_service)],
    session_id: Annotated[str, Depends(get_current_session_id)],
) -> OkResponse:
    return await service.logout(session_id)


@router.post("/token/refresh", response_model=TokenPair)
async def refresh_token(
    payload: RefreshTokenRequest,
    service: Annotated[AuthService, Depends(_auth_service)],
) -> TokenPair:
    return await service.refresh(payload.refresh_token)
