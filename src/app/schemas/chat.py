from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=32_000)
    client_id: str | None = Field(default=None, max_length=128)
    model: str = Field(default="echo", max_length=128)
    stream: bool = False


class ChatResponse(BaseModel):
    id: str
    provider: str
    message: str


class WebSocketChatMessage(BaseModel):
    message: str = Field(min_length=1, max_length=32_000)
