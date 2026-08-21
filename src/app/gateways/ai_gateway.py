"""本地 Echo 网关：输出形状符合 OpenAI Chat Completions，便于单测/离线开发。"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from datetime import date

from src.app.schemas.openai_chat import (
    ChatCompletionChoice,
    ChatCompletionChunk,
    ChatCompletionChunkChoice,
    ChatCompletionChunkDelta,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionUsage,
    ChatMessage,
    ImageUrlContentPart,
)
from src.app.utils.ids import new_request_id


def _last_user_text(request: ChatCompletionRequest) -> str:
    for msg in reversed(request.messages):
        if msg.role == "user":
            text = msg.text.strip()
            if text:
                return text
            if isinstance(msg.content, list):
                return "[image]" if _message_has_image(msg) else "[audio]"
    if request.messages:
        return request.messages[-1].text or "[audio]"
    return ""


def _message_has_image(msg: ChatMessage) -> bool:
    if not isinstance(msg.content, list):
        return False
    for part in msg.content:
        if isinstance(part, ImageUrlContentPart) or getattr(part, "type", None) == "image_url":
            return True
        if isinstance(part, dict) and part.get("type") == "image_url":
            return True
    return False


def _has_image(request: ChatCompletionRequest) -> bool:
    return any(_message_has_image(msg) for msg in request.messages)


def _ocr_stub_content() -> str:
    today = date.today().isoformat()
    visit_no = f"MZ{today.replace('-', '')}0018"
    return json.dumps(
        {
            "diagnosis": "支气管炎倾向，建议复查",
            "medicine": "按医嘱服用止咳药，注意饮水",
            "visit_date": today,
            "visit_no": visit_no,
            "document_type": "visit",
            "raw_ocr_text": (
                f"诊断：支气管炎倾向，建议复查\n用药：按医嘱服用止咳药，注意饮水\n"
                f"就诊日期：{today}\n就诊号：{visit_no}"
            ),
        },
        ensure_ascii=False,
    )


def _echo_text(request: ChatCompletionRequest) -> str:
    if _has_image(request):
        return _ocr_stub_content()
    return f"echo: {_last_user_text(request)}"


class EchoAIGateway:
    provider = "echo"

    async def chat_completions(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        await asyncio.sleep(0)
        text = _echo_text(request)
        return ChatCompletionResponse(
            id=f"chatcmpl-{new_request_id()}",
            created=int(time.time()),
            model=request.model or "echo",
            choices=[
                ChatCompletionChoice(
                    index=0,
                    message=ChatMessage(role="assistant", content=text),
                    finish_reason="stop",
                )
            ],
            usage=ChatCompletionUsage(
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
            ),
            provider=self.provider,
        )

    async def chat_completions_stream(
        self, request: ChatCompletionRequest
    ) -> AsyncIterator[ChatCompletionChunk]:
        text = _echo_text(request)
        chunk_id = f"chatcmpl-{new_request_id()}"
        created = int(time.time())
        model = request.model or "echo"

        # 首包带 role，后续只推 content（贴近 OpenAI 流式习惯）
        yield ChatCompletionChunk(
            id=chunk_id,
            created=created,
            model=model,
            choices=[
                ChatCompletionChunkChoice(
                    index=0,
                    delta=ChatCompletionChunkDelta(role="assistant", content=""),
                    finish_reason=None,
                )
            ],
            provider=self.provider,
        )
        pieces = [text] if _has_image(request) else ["echo", ": ", _last_user_text(request)]
        for piece in pieces:
            await asyncio.sleep(0)
            yield ChatCompletionChunk(
                id=chunk_id,
                created=created,
                model=model,
                choices=[
                    ChatCompletionChunkChoice(
                        index=0,
                        delta=ChatCompletionChunkDelta(content=piece),
                        finish_reason=None,
                    )
                ],
                provider=self.provider,
            )
        yield ChatCompletionChunk(
            id=chunk_id,
            created=created,
            model=model,
            choices=[
                ChatCompletionChunkChoice(
                    index=0,
                    delta=ChatCompletionChunkDelta(),
                    finish_reason="stop",
                )
            ],
            provider=self.provider,
        )

    async def close(self) -> None:
        return None


class ReverseEchoAIGateway(EchoAIGateway):
    provider = "reverse-echo"

    async def chat_completions(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        user_text = _last_user_text(request)
        text = f"reverse-echo: {user_text[::-1]}"
        await asyncio.sleep(0)
        return ChatCompletionResponse(
            id=f"chatcmpl-{new_request_id()}",
            created=int(time.time()),
            model=request.model or "reverse-echo",
            choices=[
                ChatCompletionChoice(
                    index=0,
                    message=ChatMessage(role="assistant", content=text),
                    finish_reason="stop",
                )
            ],
            provider=self.provider,
        )

    async def chat_completions_stream(
        self, request: ChatCompletionRequest
    ) -> AsyncIterator[ChatCompletionChunk]:
        user_text = _last_user_text(request)
        pieces = ["reverse-echo", ": ", user_text[::-1]]
        chunk_id = f"chatcmpl-{new_request_id()}"
        created = int(time.time())
        model = request.model or "reverse-echo"
        yield ChatCompletionChunk(
            id=chunk_id,
            created=created,
            model=model,
            choices=[
                ChatCompletionChunkChoice(
                    index=0,
                    delta=ChatCompletionChunkDelta(role="assistant", content=""),
                    finish_reason=None,
                )
            ],
            provider=self.provider,
        )
        for piece in pieces:
            await asyncio.sleep(0)
            yield ChatCompletionChunk(
                id=chunk_id,
                created=created,
                model=model,
                choices=[
                    ChatCompletionChunkChoice(
                        index=0,
                        delta=ChatCompletionChunkDelta(content=piece),
                        finish_reason=None,
                    )
                ],
                provider=self.provider,
            )
        yield ChatCompletionChunk(
            id=chunk_id,
            created=created,
            model=model,
            choices=[
                ChatCompletionChunkChoice(
                    index=0,
                    delta=ChatCompletionChunkDelta(),
                    finish_reason="stop",
                )
            ],
            provider=self.provider,
        )
