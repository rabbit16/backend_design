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
from src.app.services.qa_intake import (
    IntakeReply,
    count_user_turns,
    history_chat_messages,
    iterate_intake_stream,
    render_intake_prompts,
)
from src.app.utils.ids import new_uuid

DEFAULT_AUDIO_PROMPT = "请听录音里老人说的话，按问诊规则继续追问或给出初步判断。"
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
        lang: str,
        stream: bool,
    ) -> ChatCompletionRequest:
        settings = get_settings()
        user_turn = count_user_turns(history) + 1
        system_prompt, user_prompt = render_intake_prompts(
            question=question, user_turn=user_turn, lang=lang
        )
        messages = history_chat_messages(history, system_prompt)
        messages.append(ChatMessage(role="user", content=user_prompt))
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
        lang: str,
        stream: bool,
    ) -> ChatCompletionRequest:
        settings = get_settings()
        user_turn = count_user_turns(history) + 1
        system_prompt, _ = render_intake_prompts(
            question=prompt or DEFAULT_AUDIO_PROMPT,
            user_turn=user_turn,
            lang=lang,
        )
        messages = history_chat_messages(history, system_prompt)
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

    def _intake_meta(
        self,
        qa: QaSession,
        *,
        question_text: str,
        continued: bool,
        next_turn: int,
        input_mode: str,
        intake_round: int,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "type": "meta",
            "context_id": qa.id,
            "lang": qa.lang,
            "question_text": question_text,
            "context_continued": continued,
            "turn_index_user": next_turn,
            "turn_index_assistant": next_turn + 1,
            "input_mode": input_mode,
            "intake_round": intake_round,
        }
        if extra:
            payload.update(extra)
        return payload

    def _intake_done(
        self,
        qa_row: QaSession,
        *,
        question: str,
        answer: str,
        user_msg: QaMessage,
        assistant_msg: QaMessage,
        continued: bool,
        input_mode: str,
        reply: IntakeReply,
        now: datetime,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "type": "done",
            "context_id": qa_row.id,
            "lang": qa_row.lang,
            "question_text": question,
            "answer_text": answer,
            "turn_index_user": user_msg.turn_index,
            "turn_index_assistant": assistant_msg.turn_index,
            "context_continued": continued,
            "input_mode": input_mode,
            "phase": reply.phase,
            "intake_complete": reply.intake_complete,
            "created_at": _fmt_utc(now),
        }
        if extra:
            payload.update(extra)
        return payload

    async def ask_text_stream(
        self,
        user_id: str,
        question: str,
        lang: str = "zh",
        *,
        new_context: bool = False,
    ) -> AsyncIterator[dict[str, Any]]:
        """文字问询 SSE：meta → (phase|token)* → done。症状不清会追问。"""
        question = question.strip()
        if not question:
            raise AppError("问题不能为空", code="empty_question", status_code=400)

        # 先解析会话拿 history，再组 OpenAI messages
        qa, history, continued, next_turn = await self._resolve_session(
            user_id, question, lang, new_context=new_context
        )
        await self.session.commit()
        req = self._build_text_request(
            history, question, user_id, lang=lang, stream=True
        )

        yield self._intake_meta(
            qa,
            question_text=question,
            continued=continued,
            next_turn=next_turn,
            input_mode="text",
            intake_round=count_user_turns(history) + 1,
        )

        gateway = self.gateway or create_gateway()
        owns = self.owns_gateway or self.gateway is None
        reply: IntakeReply | None = None
        async for event in iterate_intake_stream(gateway, req, owns_gateway=owns):
            if event.get("type") == "_complete":
                reply = event["reply"]
                continue
            yield event
        if reply is None:
            return

        answer = reply.answer.strip() or "我暂时没有想好怎么回答，请您再说一遍。"
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

        yield self._intake_done(
            qa_row,
            question=question,
            answer=answer,
            user_msg=user_msg,
            assistant_msg=assistant_msg,
            continued=continued,
            input_mode="text",
            reply=reply,
            now=now,
        )

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
        """语音问询 SSE：与文字相同，按症状追问直至初步判断。"""
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
            lang=lang,
            stream=True,
        )

        yield self._intake_meta(
            qa,
            question_text=question_label,
            continued=continued,
            next_turn=next_turn,
            input_mode="voice",
            intake_round=count_user_turns(history) + 1,
            extra={"audio_format": audio_format},
        )

        gateway = self.gateway or create_gateway()
        owns = self.owns_gateway or self.gateway is None
        reply: IntakeReply | None = None
        async for event in iterate_intake_stream(gateway, req, owns_gateway=owns):
            if event.get("type") == "_complete":
                reply = event["reply"]
                continue
            yield event
        if reply is None:
            return

        answer = reply.answer.strip() or "我暂时没有听清，请您再说一遍。"
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

        yield self._intake_done(
            qa_row,
            question=question_label,
            answer=answer,
            user_msg=user_msg,
            assistant_msg=assistant_msg,
            continued=continued,
            input_mode="voice",
            reply=reply,
            now=now,
        )

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
            phase=done.get("phase", "followup"),
            intake_complete=bool(done.get("intake_complete")),
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
