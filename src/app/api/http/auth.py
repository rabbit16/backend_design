from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.db.session import get_session
from src.app.schemas.auth import (
    ChangePasswordRequest,
    LoginResponse,
    OkResponse,
    PasswordLoginRequest,
    RefreshTokenRequest,
    RegisterRequest,
    SendSmsRequest,
    SendSmsResponse,
    SmsLoginRequest,
    TokenPair,
)
from src.app.security.jwt import get_current_session_id, get_current_subject
from src.app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


def _auth_service(session: Annotated[AsyncSession, Depends(get_session)]) -> AuthService:
    return AuthService(session)


@router.post("/sms/send", response_model=SendSmsResponse)
async def send_sms(
    payload: SendSmsRequest,
    service: Annotated[AuthService, Depends(_auth_service)],
) -> SendSmsResponse:
    return await service.send_sms(payload.phone, payload.purpose)


@router.post("/register", response_model=LoginResponse)
async def register(
    payload: RegisterRequest,
    service: Annotated[AuthService, Depends(_auth_service)],
) -> LoginResponse:
    return await service.register(
        phone=payload.phone,
        code=payload.code,
        password=payload.password,
        display_name=payload.display_name,
        preferred_lang=payload.preferred_lang,
    )


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
