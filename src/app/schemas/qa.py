from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

Lang = Literal["zh", "en"]


class TextAskRequest(BaseModel):
    """适老化文字问答：无需传 session_id，服务端托管上下文。"""

    question: str = Field(min_length=1, max_length=4000)
    lang: Lang = "zh"
    # 可选：强制开新上下文（例如用户点「新问题」）
    new_context: bool = False


class QaMessageOut(BaseModel):
    id: str
    turn_index: int
    role: Literal["user", "assistant", "system"]
    content: str
    input_mode: str | None = None
    created_at: str


class TextAskResponse(BaseModel):
    context_id: str
    lang: Lang
    question_text: str
    answer_text: str
    turn_index_user: int
    turn_index_assistant: int
    context_continued: bool
    created_at: str


class OkResponse(BaseModel):
    ok: bool = True


class ClearContextResponse(OkResponse):
    context_id: str | None = None
