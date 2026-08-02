from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.qa import ClearContextResponse, TextAskRequest
from app.security.jwt import get_current_subject
from app.services.qa_service import QaService, format_sse

router = APIRouter(prefix="/qa", tags=["qa"])


def _qa_service(session: Annotated[AsyncSession, Depends(get_session)]) -> QaService:
    return QaService(session)


@router.post("/ask")
async def ask_text(
    payload: TextAskRequest,
    service: Annotated[QaService, Depends(_qa_service)],
    user_id: Annotated[str, Depends(get_current_subject)],
) -> StreamingResponse:
    """适老化文字问答（SSE 流式）。

    事件顺序：
    - meta：上下文信息
    - token：回答增量（可多次）
    - done：完整结果（已落库）
    - error：失败
    """

    async def event_stream() -> AsyncIterator[str]:
        async for event in service.ask_text_stream(
            user_id=user_id,
            question=payload.question,
            lang=payload.lang,
            new_context=payload.new_context,
        ):
            yield format_sse(event)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/context/clear", response_model=ClearContextResponse)
async def clear_context(
    service: Annotated[QaService, Depends(_qa_service)],
    user_id: Annotated[str, Depends(get_current_subject)],
) -> ClearContextResponse:
    """主动结束当前上下文（下次提问会开新会话）。"""
    old = await service.clear_context(user_id)
    return ClearContextResponse(ok=True, context_id=old)
