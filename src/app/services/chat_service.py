from sqlalchemy.ext.asyncio import AsyncSession

from app.gateways.base import AIGateway
from app.repositories.chat_message_repository import ChatMessageRepository
from app.schemas.chat import ChatRequest, ChatResponse


class ChatService:
    def __init__(self, gateway: AIGateway, session: AsyncSession | None = None) -> None:
        self.gateway = gateway
        self.session = session

    async def complete(self, request: ChatRequest) -> ChatResponse:
        response = await self.gateway.complete(request)
        if self.session and request.client_id:
            repo = ChatMessageRepository(self.session)
            await repo.add(client_id=request.client_id, role="user", content=request.message)
            await repo.add(client_id=request.client_id, role="assistant", content=response.message)
            await self.session.commit()
        return response
