import asyncio
from collections.abc import AsyncIterator

from app.schemas.chat import ChatRequest, ChatResponse
from app.utils.ids import new_request_id


class EchoAIGateway:
    provider = "echo"

    async def complete(self, request: ChatRequest) -> ChatResponse:
        await asyncio.sleep(0)
        return ChatResponse(
            id=new_request_id(),
            provider=self.provider,
            message=f"echo: {request.message}",
        )

    async def stream(self, request: ChatRequest) -> AsyncIterator[str]:
        for token in ["echo", ": ", request.message]:
            await asyncio.sleep(0)
            yield token

    async def close(self) -> None:
        return None
