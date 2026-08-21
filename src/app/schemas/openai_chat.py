"""OpenAI Chat Completions 兼容协议（文本 + 多模态音频/图像）。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ChatRole = Literal["system", "user", "assistant", "tool"]
AudioFormat = Literal["wav", "mp3"]
ImageDetail = Literal["auto", "low", "high"]


class InputAudio(BaseModel):
    data: str = Field(min_length=1, description="base64 音频")
    format: AudioFormat = "wav"


class ImageUrl(BaseModel):
    """OpenAI vision `image_url` 对象。url 可为 https 或 data:image/...;base64,..."""

    url: str = Field(min_length=1)
    detail: ImageDetail | None = None


class TextContentPart(BaseModel):
    type: Literal["text"] = "text"
    text: str = Field(min_length=0, max_length=128_000)


class InputAudioContentPart(BaseModel):
    type: Literal["input_audio"] = "input_audio"
    input_audio: InputAudio


class ImageUrlContentPart(BaseModel):
    type: Literal["image_url"] = "image_url"
    image_url: ImageUrl


ContentPart = TextContentPart | InputAudioContentPart | ImageUrlContentPart


def _parts_to_text(parts: list[Any]) -> str:
    texts: list[str] = []
    for item in parts:
        if isinstance(item, TextContentPart):
            texts.append(item.text)
        elif isinstance(item, dict) and item.get("type") == "text":
            texts.append(str(item.get("text") or ""))
        elif isinstance(item, str):
            texts.append(item)
    return "".join(texts)


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    role: ChatRole
    content: str | list[ContentPart] = Field(default="")
    name: str | None = None

    @field_validator("content", mode="before")
    @classmethod
    def _coerce_content(cls, value: Any) -> str | list[Any]:
        if value is None:
            return ""
        if isinstance(value, list):
            return value
        return str(value)

    @property
    def text(self) -> str:
        if isinstance(self.content, str):
            return self.content
        return _parts_to_text(list(self.content))

    def to_openai_param(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"role": self.role}
        if self.name:
            payload["name"] = self.name
        if isinstance(self.content, str):
            payload["content"] = self.content
        else:
            payload["content"] = [part.model_dump(exclude_none=True) for part in self.content]
        return payload


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
    # 音频模型输出模态；语音提问默认只要文本流
    modalities: list[Literal["text", "audio"]] | None = None
    audio: dict[str, Any] | None = None
    # OpenAI response_format，如 {"type": "json_object"} 或 json_schema
    response_format: dict[str, Any] | None = None
    # 透传给上游的额外字段
    extra: dict[str, Any] = Field(default_factory=dict)


class ChatCompletionChoice(BaseModel):
    model_config = ConfigDict(extra="ignore")

    index: int = 0
    message: ChatMessage
    finish_reason: str | None = "stop"


class ChatCompletionUsage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    object: str = "chat.completion"
    created: int = 0
    model: str = ""
    choices: list[ChatCompletionChoice]
    usage: ChatCompletionUsage | None = None
    provider: str | None = None

    @property
    def content(self) -> str:
        if not self.choices:
            return ""
        return self.choices[0].message.text


class ChatCompletionChunkDelta(BaseModel):
    model_config = ConfigDict(extra="ignore")

    role: str | None = None
    content: str | None = None

    @field_validator("content", mode="before")
    @classmethod
    def _coerce_delta_content(cls, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, list):
            return _parts_to_text(value)
        return str(value)


class ChatCompletionChunkChoice(BaseModel):
    model_config = ConfigDict(extra="ignore")

    index: int = 0
    delta: ChatCompletionChunkDelta = Field(default_factory=ChatCompletionChunkDelta)
    finish_reason: str | None = None


class ChatCompletionChunk(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = ""
    object: str = "chat.completion.chunk"
    created: int = 0
    model: str = ""
    choices: list[ChatCompletionChunkChoice] = Field(default_factory=list)
    provider: str | None = None

    @property
    def delta_content(self) -> str:
        if not self.choices:
            return ""
        return self.choices[0].delta.content or ""
