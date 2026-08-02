from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.gateways.providers import list_providers
from app.gateways.registry import create_gateway
from app.schemas.chat import ChatRequest, ChatResponse
from app.schemas.response import ApiResponse, ok
from app.security.jwt import get_current_subject
from app.services.chat_service import ChatService

router = APIRouter(prefix="/chat", tags=["chat"])


@router.get("/models", response_model=ApiResponse[list[str]])
async def models() -> ApiResponse[list[str]]:
    return ok(list_providers())


@router.post("/completions", response_model=ChatResponse)
async def chat_completion(
    payload: ChatRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ChatResponse:
    service = ChatService(gateway=create_gateway(payload.model), session=session)
    return await service.complete(payload)


@router.post("/secure-completions", response_model=ApiResponse[ChatResponse])
async def secure_chat_completion(
    payload: ChatRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_subject: Annotated[str, Depends(get_current_subject)],
) -> ApiResponse[ChatResponse]:
    payload.client_id = payload.client_id or current_subject
    service = ChatService(gateway=create_gateway(payload.model), session=session)
    return ok(await service.complete(payload))
