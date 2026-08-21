from __future__ import annotations

import base64
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.app.core.config import get_settings
from src.app.core.exceptions import AppError
from src.app.db.models.qa import QaMessage, QaSession
from src.app.gateways.base import AIGateway
from src.app.gateways.registry import create_gateway
from src.app.schemas.openai_chat import (
    AudioFormat,
    ChatCompletionRequest,
    ChatMessage,
    InputAudio,
    InputAudioContentPart,
    TextContentPart,
)
from src.app.schemas.qa import TextAskResponse
from src.app.services.context_store import QaContextStore
from src.app.utils.ids import new_uuid

SENIOR_SYSTEM_PROMPT = (
    "你是适老化语音问答助手。请用简短、清楚、口语化的中文回答老人的问题，"
    "避免生僻词和过长段落；涉及医疗时提醒仅供参考、不能替代医生诊断。"
)

DEFAULT_AUDIO_PROMPT = "请用简短、清楚、口语化的中文回答录音里的问题。"
MAX_AUDIO_BYTES = 25 * 1024 * 1024


def _fmt_utc(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    else:
        dt = dt.astimezone(UTC)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _truncate_title(question: str, limit: int = 40) -> str:
    text = question.strip().replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _history_messages(history: list[QaMessage]) -> list[ChatMessage]:
    settings = get_settings()
    recent = history[-settings.qa_context_history_limit :]
    messages: list[ChatMessage] = [ChatMessage(role="system", content=SENIOR_SYSTEM_PROMPT)]
    for msg in recent:
        if msg.role == "user":
            messages.append(ChatMessage(role="user", content=msg.content))
        elif msg.role == "assistant":
            messages.append(ChatMessage(role="assistant", content=msg.content))
    return messages


class QaService:
    def __init__(
        self,
        session: AsyncSession,
        context_store: QaContextStore | None = None,
        gateway: AIGateway | None = None,
        *,
        owns_gateway: bool = False,
    ) -> None:
        self.session = session
        self.context_store = context_store or QaContextStore()
        self.gateway = gateway
        self.owns_gateway = owns_gateway

    async def _load_active_session(self, user_id: str, session_id: str) -> QaSession | None:
        result = await self.session.execute(
            select(QaSession)
            .where(
                QaSession.id == session_id,
                QaSession.user_id == user_id,
                QaSession.deleted_at.is_(None),
                QaSession.status == "active",
            )
            .options(selectinload(QaSession.messages))
        )
        return result.scalar_one_or_none()

    async def _create_session(self, user_id: str, lang: str, title: str) -> QaSession:
        qa = QaSession(
            id=new_uuid(),
            user_id=user_id,
            lang=lang,
            title=title,
            status="active",
            message_count=0,
        )
        self.session.add(qa)
        await self.session.flush()
        return qa

    async def _resolve_session(
        self,
        user_id: str,
        question_label: str,
        lang: str,
        *,
        new_context: bool,
    ) -> tuple[QaSession, list[QaMessage], bool, int]:
        continued = False
        qa: QaSession | None = None

        if new_context:
            await self.context_store.clear(user_id)
        else:
            cached_id = await self.context_store.get(user_id)
            if cached_id:
                qa = await self._load_active_session(user_id, cached_id)
                continued = qa is not None
                if qa is None:
                    await self.context_store.clear(user_id)

        if qa is None:
            qa = await self._create_session(user_id, lang, _truncate_title(question_label))
            await self.context_store.set(user_id, qa.id)
            continued = False
            history: list[QaMessage] = []
        else:
            history = list(qa.messages)

        next_turn = (history[-1].turn_index + 1) if history else 1
        return qa, history, continued, next_turn

    def _build_text_request(
        self,
        history: list[QaMessage],
        question: str,
        user_id: str,
        *,
        stream: bool,
    ) -> ChatCompletionRequest:
        settings = get_settings()
        messages = _history_messages(history)
        messages.append(ChatMessage(role="user", content=question))
        return ChatCompletionRequest(
            model=settings.openai_model,
            messages=messages,
            stream=stream,
            temperature=settings.openai_temperature,
            max_tokens=settings.openai_max_tokens,
            user=user_id,
        )

    def _build_audio_request(
        self,
        history: list[QaMessage],
        *,
        audio_base64: str,
        audio_format: AudioFormat,
        prompt: str,
        user_id: str,
        stream: bool,
    ) -> ChatCompletionRequest:
        settings = get_settings()
        messages = _history_messages(history)
        messages.append(
            ChatMessage(
                role="user",
                content=[
                    TextContentPart(text=prompt or DEFAULT_AUDIO_PROMPT),
                    InputAudioContentPart(
                        input_audio=InputAudio(data=audio_base64, format=audio_format)
                    ),
                ],
            )
        )
        return ChatCompletionRequest(
            model=settings.openai_audio_model,
            messages=messages,
            stream=stream,
            # 只要文本流式输出（不要返回音频）
            modalities=["text"],
            temperature=settings.openai_temperature,
            max_tokens=settings.openai_max_tokens,
            user=user_id,
        )

    async def ask_text_stream(
        self,
        user_id: str,
        question: str,
        lang: str = "zh",
        *,
        new_context: bool = False,
    ) -> AsyncIterator[dict[str, Any]]:
        """文字问答 SSE：meta → token* → done。"""
        question = question.strip()
        if not question:
            raise AppError("问题不能为空", code="empty_question", status_code=400)

        # 先解析会话拿 history，再组 OpenAI messages
        qa, history, continued, next_turn = await self._resolve_session(
            user_id, question, lang, new_context=new_context
        )
        await self.session.commit()
        req = self._build_text_request(history, question, user_id, stream=True)

        yield {
            "type": "meta",
            "context_id": qa.id,
            "lang": qa.lang,
            "question_text": question,
            "context_continued": continued,
            "turn_index_user": next_turn,
            "turn_index_assistant": next_turn + 1,
            "input_mode": "text",
        }

        gateway = self.gateway or create_gateway()
        owns = self.owns_gateway or self.gateway is None
        chunks: list[str] = []
        try:
            async for chunk in gateway.chat_completions_stream(req):
                delta = chunk.delta_content
                if not delta:
                    continue
                chunks.append(delta)
                yield {"type": "token", "delta": delta}
        except AppError as exc:
            yield {"type": "error", "code": exc.code, "message": exc.message}
            return
        except Exception as exc:  # noqa: BLE001
            yield {
                "type": "error",
                "code": "qa_stream_failed",
                "message": str(exc) or "生成回答失败",
            }
            return
        finally:
            if owns:
                await gateway.close()

        answer = "".join(chunks).strip() or "我暂时没有想好怎么回答，请您再说一遍。"
        now = datetime.now(UTC)
        user_msg = QaMessage(
            id=new_uuid(),
            session_id=qa.id,
            user_id=user_id,
            turn_index=next_turn,
            role="user",
            content=question,
            input_mode="text",
        )
        assistant_msg = QaMessage(
            id=new_uuid(),
            session_id=qa.id,
            user_id=user_id,
            turn_index=next_turn + 1,
            role="assistant",
            content=answer,
            input_mode=None,
        )
        self.session.add_all([user_msg, assistant_msg])
        result = await self.session.execute(select(QaSession).where(QaSession.id == qa.id))
        qa_row = result.scalar_one()
        qa_row.message_count = next_turn + 1
        qa_row.last_message_at = now
        if not qa_row.title:
            qa_row.title = _truncate_title(question)
        await self.session.commit()

        yield {
            "type": "done",
            "context_id": qa_row.id,
            "lang": qa_row.lang,
            "question_text": question,
            "answer_text": answer,
            "turn_index_user": user_msg.turn_index,
            "turn_index_assistant": assistant_msg.turn_index,
            "context_continued": continued,
            "input_mode": "text",
            "created_at": _fmt_utc(now),
        }

    async def ask_audio_stream(
        self,
        user_id: str,
        *,
        audio_bytes: bytes,
        audio_format: AudioFormat = "wav",
        prompt: str = DEFAULT_AUDIO_PROMPT,
        lang: str = "zh",
        new_context: bool = False,
    ) -> AsyncIterator[dict[str, Any]]:
        """语音输入 → 文本流式输出（OpenAI input_audio + modalities=text）。"""
        if not audio_bytes:
            raise AppError("音频不能为空", code="empty_audio", status_code=400)
        if len(audio_bytes) > MAX_AUDIO_BYTES:
            raise AppError("音频过大（上限 25MB）", code="audio_too_large", status_code=400)

        prompt = (prompt or DEFAULT_AUDIO_PROMPT).strip() or DEFAULT_AUDIO_PROMPT
        question_label = f"（语音）{prompt}" if prompt != DEFAULT_AUDIO_PROMPT else "（语音提问）"
        encoded = base64.b64encode(audio_bytes).decode("ascii")

        qa, history, continued, next_turn = await self._resolve_session(
            user_id, question_label, lang, new_context=new_context
        )
        await self.session.commit()
        req = self._build_audio_request(
            history,
            audio_base64=encoded,
            audio_format=audio_format,
            prompt=prompt,
            user_id=user_id,
            stream=True,
        )

        yield {
            "type": "meta",
            "context_id": qa.id,
            "lang": qa.lang,
            "question_text": question_label,
            "context_continued": continued,
            "turn_index_user": next_turn,
            "turn_index_assistant": next_turn + 1,
            "input_mode": "voice",
            "audio_format": audio_format,
        }

        gateway = self.gateway or create_gateway()
        owns = self.owns_gateway or self.gateway is None
        chunks: list[str] = []
        try:
            async for chunk in gateway.chat_completions_stream(req):
                delta = chunk.delta_content
                if not delta:
                    continue
                chunks.append(delta)
                yield {"type": "token", "delta": delta}
        except AppError as exc:
            yield {"type": "error", "code": exc.code, "message": exc.message}
            return
        except Exception as exc:  # noqa: BLE001
            yield {
                "type": "error",
                "code": "qa_stream_failed",
                "message": str(exc) or "生成回答失败",
            }
            return
        finally:
            if owns:
                await gateway.close()

        answer = "".join(chunks).strip() or "我暂时没有听清，请您再说一遍。"
        now = datetime.now(UTC)
        user_msg = QaMessage(
            id=new_uuid(),
            session_id=qa.id,
            user_id=user_id,
            turn_index=next_turn,
            role="user",
            content=question_label,
            input_mode="voice",
        )
        assistant_msg = QaMessage(
            id=new_uuid(),
            session_id=qa.id,
            user_id=user_id,
            turn_index=next_turn + 1,
            role="assistant",
            content=answer,
            input_mode=None,
        )
        self.session.add_all([user_msg, assistant_msg])
        result = await self.session.execute(select(QaSession).where(QaSession.id == qa.id))
        qa_row = result.scalar_one()
        qa_row.message_count = next_turn + 1
        qa_row.last_message_at = now
        if not qa_row.title:
            qa_row.title = _truncate_title(question_label)
        await self.session.commit()

        yield {
            "type": "done",
            "context_id": qa_row.id,
            "lang": qa_row.lang,
            "question_text": question_label,
            "answer_text": answer,
            "turn_index_user": user_msg.turn_index,
            "turn_index_assistant": assistant_msg.turn_index,
            "context_continued": continued,
            "input_mode": "voice",
            "created_at": _fmt_utc(now),
        }

    async def ask_text(
        self,
        user_id: str,
        question: str,
        lang: str = "zh",
        *,
        new_context: bool = False,
    ) -> TextAskResponse:
        done: dict[str, Any] | None = None
        async for event in self.ask_text_stream(
            user_id, question, lang, new_context=new_context
        ):
            if event.get("type") == "error":
                raise AppError(
                    event.get("message") or "生成回答失败",
                    code=event.get("code") or "qa_stream_failed",
                    status_code=500,
                )
            if event.get("type") == "done":
                done = event
        if done is None:
            raise AppError("未收到完整回答", code="qa_incomplete", status_code=500)
        return TextAskResponse(
            context_id=done["context_id"],
            lang=done["lang"],
            question_text=done["question_text"],
            answer_text=done["answer_text"],
            turn_index_user=done["turn_index_user"],
            turn_index_assistant=done["turn_index_assistant"],
            context_continued=done["context_continued"],
            created_at=done["created_at"],
        )

    async def clear_context(self, user_id: str) -> str | None:
        old = await self.context_store.get(user_id)
        if old:
            qa = await self._load_active_session(user_id, old)
            if qa is not None:
                qa.status = "closed"
                await self.session.commit()
        await self.context_store.clear(user_id)
        return old


def format_sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def guess_audio_format(filename: str | None, content_type: str | None) -> AudioFormat:
    name = (filename or "").lower()
    ctype = (content_type or "").lower()
    if name.endswith(".mp3") or "mpeg" in ctype or "mp3" in ctype:
        return "mp3"
    return "wav"
