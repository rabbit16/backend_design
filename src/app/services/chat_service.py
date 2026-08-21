from sqlalchemy.ext.asyncio import AsyncSession

from src.app.gateways.base import AIGateway
from src.app.repositories.chat_message_repository import ChatMessageRepository
from src.app.schemas.chat import ChatRequest, ChatResponse


class ChatService:
    def __init__(self, gateway: AIGateway, session: AsyncSession | None = None) -> None:
        self.gateway = gateway
        self.session = session

    async def complete(self, request: ChatRequest) -> ChatResponse:
        completion = await self.gateway.chat_completions(request.to_openai())
        response = ChatResponse(
            id=completion.id,
            provider=completion.provider or getattr(self.gateway, "provider", "unknown"),
            message=completion.content,
        )
        if self.session and request.client_id:
            repo = ChatMessageRepository(self.session)
            await repo.add(client_id=request.client_id, role="user", content=request.message)
            await repo.add(client_id=request.client_id, role="assistant", content=response.message)
            await self.session.commit()
        return response
