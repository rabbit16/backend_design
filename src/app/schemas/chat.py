from pydantic import BaseModel, Field

from app.schemas.openai_chat import ChatCompletionRequest, ChatMessage


class ChatRequest(BaseModel):
    """兼容旧脚手架的简化请求；内部会转成 OpenAI messages。"""

    message: str = Field(min_length=1, max_length=32_000)
    client_id: str | None = Field(default=None, max_length=128)
    # 空：使用应用默认网关 + OPENAI_MODEL；也可填 provider 名或具体模型 id
    model: str = Field(default="", max_length=128)
    stream: bool = False
    system_prompt: str | None = Field(default=None, max_length=8_000)

    def to_openai(self) -> ChatCompletionRequest:
        settings_model = self.model
        messages: list[ChatMessage] = []
        if self.system_prompt:
            messages.append(ChatMessage(role="system", content=self.system_prompt))
        messages.append(ChatMessage(role="user", content=self.message))
        return ChatCompletionRequest(
            model=settings_model or "gpt-4o-mini",
            messages=messages,
            stream=self.stream,
            user=self.client_id,
        )


class ChatResponse(BaseModel):
    id: str
    provider: str
    message: str


class WebSocketChatMessage(BaseModel):
    message: str = Field(min_length=1, max_length=32_000)
