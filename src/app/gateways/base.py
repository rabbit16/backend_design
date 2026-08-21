from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from src.app.schemas.openai_chat import ChatCompletionChunk, ChatCompletionRequest, ChatCompletionResponse


class AIGateway(Protocol):
    """OpenAI Chat Completions 兼容网关。"""

    provider: str

    async def chat_completions(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        ...

    def chat_completions_stream(
        self, request: ChatCompletionRequest
    ) -> AsyncIterator[ChatCompletionChunk]:
        ...

    async def close(self) -> None:
        ...
