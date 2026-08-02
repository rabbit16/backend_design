"""OpenAI Chat Completions 兼容协议（便于切换任意兼容模型）。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

ChatRole = Literal["system", "user", "assistant", "tool"]


class ChatMessage(BaseModel):
    role: ChatRole
    content: str = Field(min_length=0, max_length=128_000)
    name: str | None = None


class ChatCompletionRequest(BaseModel):
    model: str = Field(default="gpt-4o-mini", max_length=128)
    messages: list[ChatMessage] = Field(min_length=1)
    stream: bool = False
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0, le=1)
    max_tokens: int | None = Field(default=None, ge=1, le=128_000)
    presence_penalty: float | None = Field(default=None, ge=-2, le=2)
    frequency_penalty: float | None = Field(default=None, ge=-2, le=2)
    user: str | None = Field(default=None, max_length=128)
    # 透传给上游的额外字段（如 response_format、tools）
    extra: dict[str, Any] = Field(default_factory=dict)


class ChatCompletionChoice(BaseModel):
    index: int = 0
    message: ChatMessage
    finish_reason: str | None = "stop"


class ChatCompletionUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionResponse(BaseModel):
    id: str
    object: Literal["chat.completion"] = "chat.completion"
    created: int
    model: str
    choices: list[ChatCompletionChoice]
    usage: ChatCompletionUsage | None = None
    provider: str | None = None

    @property
    def content(self) -> str:
        if not self.choices:
            return ""
        return self.choices[0].message.content


class ChatCompletionChunkDelta(BaseModel):
    role: ChatRole | None = None
    content: str | None = None


class ChatCompletionChunkChoice(BaseModel):
    index: int = 0
    delta: ChatCompletionChunkDelta
    finish_reason: str | None = None


class ChatCompletionChunk(BaseModel):
    id: str
    object: Literal["chat.completion.chunk"] = "chat.completion.chunk"
    created: int
    model: str
    choices: list[ChatCompletionChunkChoice]
    provider: str | None = None

    @property
    def delta_content(self) -> str:
        if not self.choices:
            return ""
        return self.choices[0].delta.content or ""
