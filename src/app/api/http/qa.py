from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.qa import ClearContextResponse, TextAskRequest, TextAskResponse
from app.security.jwt import get_current_subject
from app.services.qa_service import QaService

router = APIRouter(prefix="/qa", tags=["qa"])


def _qa_service(session: Annotated[AsyncSession, Depends(get_session)]) -> QaService:
    return QaService(session)


@router.post("/ask", response_model=TextAskResponse)
async def ask_text(
    payload: TextAskRequest,
    service: Annotated[QaService, Depends(_qa_service)],
    user_id: Annotated[str, Depends(get_current_subject)],
) -> TextAskResponse:
    """适老化文字问答：服务端用 Redis 托管上下文，前端无需传 session_id。"""
    return await service.ask_text(
        user_id=user_id,
        question=payload.question,
        lang=payload.lang,
        new_context=payload.new_context,
    )


@router.post("/context/clear", response_model=ClearContextResponse)
async def clear_context(
    service: Annotated[QaService, Depends(_qa_service)],
    user_id: Annotated[str, Depends(get_current_subject)],
) -> ClearContextResponse:
    """主动结束当前上下文（下次提问会开新会话）。"""
    old = await service.clear_context(user_id)
    return ClearContextResponse(ok=True, context_id=old)
