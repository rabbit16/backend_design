from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.exceptions import AppError
from src.app.db.session import get_session
from src.app.gateways.base import AIGateway
from src.app.gateways.registry import get_gateway
from src.app.schemas.openai_chat import AudioFormat
from src.app.schemas.qa import AudioAskJsonRequest, ClearContextResponse, TextAskRequest
from src.app.security.jwt import get_current_subject
from src.app.services.qa_service import (
    DEFAULT_AUDIO_PROMPT,
    QaService,
    format_sse,
    guess_audio_format,
)

router = APIRouter(prefix="/qa", tags=["qa"])

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def _qa_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    gateway: Annotated[AIGateway, Depends(get_gateway)],
) -> QaService:
    return QaService(session, gateway=gateway, owns_gateway=False)


def _sse(stream: AsyncIterator[dict]) -> StreamingResponse:
    async def event_stream() -> AsyncIterator[str]:
        async for event in stream:
            yield format_sse(event)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@router.post("/ask")
async def ask_text(
    payload: TextAskRequest,
    service: Annotated[QaService, Depends(_qa_service)],
    user_id: Annotated[str, Depends(get_current_subject)],
) -> StreamingResponse:
    """适老化文字问答（SSE 流式，OpenAI SDK）。

    事件：meta → token* → done | error
    """
    return _sse(
        service.ask_text_stream(
            user_id=user_id,
            question=payload.question,
            lang=payload.lang,
            new_context=payload.new_context,
        )
    )


@router.post("/ask/audio")
async def ask_audio_multipart(
    service: Annotated[QaService, Depends(_qa_service)],
    user_id: Annotated[str, Depends(get_current_subject)],
    file: Annotated[UploadFile, File(description="wav/mp3 音频")],
    lang: Annotated[str, Form()] = "zh",
    new_context: Annotated[bool, Form()] = False,
    prompt: Annotated[str, Form()] = DEFAULT_AUDIO_PROMPT,
    audio_format: Annotated[str | None, Form()] = None,
) -> StreamingResponse:
    """语音输入 → 文本流式输出（multipart 上传音频）。

    内部按 OpenAI `input_audio` + `modalities=["text"]` 调用音频模型。
    """
    data = await file.read()
    fmt: AudioFormat
    if audio_format in {"wav", "mp3"}:
        fmt = audio_format  # type: ignore[assignment]
    else:
        fmt = guess_audio_format(file.filename, file.content_type)

    if lang not in {"zh", "en"}:
        raise AppError("lang 仅支持 zh/en", code="invalid_lang", status_code=400)

    return _sse(
        service.ask_audio_stream(
            user_id,
            audio_bytes=data,
            audio_format=fmt,
            prompt=prompt,
            lang=lang,  # type: ignore[arg-type]
            new_context=new_context,
        )
    )


@router.post("/ask/audio/json")
async def ask_audio_json(
    payload: AudioAskJsonRequest,
    service: Annotated[QaService, Depends(_qa_service)],
    user_id: Annotated[str, Depends(get_current_subject)],
) -> StreamingResponse:
    """语音输入 → 文本流式输出（JSON base64，对齐 OpenAI 示例）。"""
    try:
        import base64

        audio_bytes = base64.b64decode(payload.audio_base64, validate=False)
    except Exception as exc:  # noqa: BLE001
        raise AppError("audio_base64 无效", code="invalid_audio_base64", status_code=400) from exc

    return _sse(
        service.ask_audio_stream(
            user_id,
            audio_bytes=audio_bytes,
            audio_format=payload.audio_format,
            prompt=payload.prompt,
            lang=payload.lang,
            new_context=payload.new_context,
        )
    )


@router.post("/context/clear", response_model=ClearContextResponse)
async def clear_context(
    service: Annotated[QaService, Depends(_qa_service)],
    user_id: Annotated[str, Depends(get_current_subject)],
) -> ClearContextResponse:
    """主动结束当前上下文（下次提问会开新会话）。"""
    old = await service.clear_context(user_id)
    return ClearContextResponse(ok=True, context_id=old)
