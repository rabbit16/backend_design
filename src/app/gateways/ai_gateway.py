"""本地 Echo 网关：输出形状符合 OpenAI Chat Completions，便于单测/离线开发。"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator

from app.schemas.openai_chat import (
    ChatCompletionChoice,
    ChatCompletionChunk,
    ChatCompletionChunkChoice,
    ChatCompletionChunkDelta,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionUsage,
    ChatMessage,
)
from app.utils.ids import new_request_id


def _last_user_text(request: ChatCompletionRequest) -> str:
    for msg in reversed(request.messages):
        if msg.role == "user":
            text = msg.text.strip()
            if text:
                return text
            if isinstance(msg.content, list):
                return "[audio]"
    if request.messages:
        return request.messages[-1].text or "[audio]"
    return ""


class EchoAIGateway:
    provider = "echo"

    async def chat_completions(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        await asyncio.sleep(0)
        text = f"echo: {_last_user_text(request)}"
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
        text = f"echo: {_last_user_text(request)}"
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
        for piece in ["echo", ": ", _last_user_text(request)]:
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
        # 避免未使用变量告警：text 与完整回答一致
        _ = text

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
