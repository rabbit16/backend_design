from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.chat_message import ChatMessage


class ChatMessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, *, client_id: str, role: str, content: str) -> ChatMessage:
        message = ChatMessage(client_id=client_id, role=role, content=content)
        self.session.add(message)
        await self.session.flush()
        return message
