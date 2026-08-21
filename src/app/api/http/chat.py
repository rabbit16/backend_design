from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.config import get_settings
from src.app.db.session import get_session
from src.app.gateways.base import AIGateway
from src.app.gateways.providers import list_providers
from src.app.gateways.registry import create_gateway, get_gateway
from src.app.schemas.chat import ChatRequest, ChatResponse
from src.app.schemas.response import ApiResponse, ok
from src.app.security.jwt import get_current_subject
from src.app.services.chat_service import ChatService

router = APIRouter(prefix="/chat", tags=["chat"])

_PROVIDER_NAMES = frozenset(
    {"echo", "reverse-echo", "reverse_echo", "openai", "openai-compatible", "openai_compatible"}
)


def _prepare(payload: ChatRequest, default_gateway: AIGateway) -> tuple[ChatRequest, AIGateway]:
    """解析 model：provider 名 → 切网关；否则当作上游模型 id，复用默认网关。"""
    settings = get_settings()
    raw = (payload.model or "").strip()
    name = raw.lower()
    default_provider = settings.ai_gateway_provider.strip().lower()

    if name in _PROVIDER_NAMES:
        if name in {"openai", "openai-compatible", "openai_compatible"}:
            gateway = default_gateway if default_provider.startswith("openai") else create_gateway("openai")
            model = settings.openai_model
        elif name == default_provider or name.replace("_", "-") == default_provider.replace("_", "-"):
            gateway = default_gateway
            model = name
        else:
            gateway = create_gateway(name)
            model = name
        return payload.model_copy(update={"model": model}), gateway

    model = raw or settings.openai_model
    return payload.model_copy(update={"model": model}), default_gateway


@router.get("/models", response_model=ApiResponse[list[str]])
async def models() -> ApiResponse[list[str]]:
    return ok(list_providers())


@router.post("/completions", response_model=ChatResponse)
async def chat_completion(
    payload: ChatRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    gateway: Annotated[AIGateway, Depends(get_gateway)],
) -> ChatResponse:
    prepared, gw = _prepare(payload, gateway)
    return await ChatService(gateway=gw, session=session).complete(prepared)


@router.post("/secure-completions", response_model=ApiResponse[ChatResponse])
async def secure_chat_completion(
    payload: ChatRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    gateway: Annotated[AIGateway, Depends(get_gateway)],
    current_subject: Annotated[str, Depends(get_current_subject)],
) -> ApiResponse[ChatResponse]:
    payload.client_id = payload.client_id or current_subject
    prepared, gw = _prepare(payload, gateway)
    return ok(await ChatService(gateway=gw, session=session).complete(prepared))
