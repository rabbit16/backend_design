from typing import Protocol, AsyncIterator

from app.schemas.chat import ChatRequest, ChatResponse


class AIGateway(Protocol):
    provider: str

    async def complete(self, request: ChatRequest) -> ChatResponse:
        ...

    async def stream(self, request: ChatRequest) -> AsyncIterator[str]:
        ...

    async def close(self) -> None:
        ...
