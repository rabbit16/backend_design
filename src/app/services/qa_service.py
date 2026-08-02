from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.db.models.qa import QaMessage, QaSession
from app.gateways.registry import create_gateway
from app.schemas.openai_chat import ChatCompletionRequest, ChatMessage
from app.schemas.qa import TextAskResponse
from app.services.context_store import QaContextStore
from app.utils.ids import new_uuid

SENIOR_SYSTEM_PROMPT = (
    "你是适老化语音问答助手。请用简短、清楚、口语化的中文回答老人的问题，"
    "避免生僻词和过长段落；涉及医疗时提醒仅供参考、不能替代医生诊断。"
)


def _fmt_utc(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    else:
        dt = dt.astimezone(UTC)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _truncate_title(question: str, limit: int = 40) -> str:
    text = question.strip().replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _history_to_openai_messages(history: list[QaMessage], question: str) -> list[ChatMessage]:
    settings = get_settings()
    recent = history[-settings.qa_context_history_limit :]
    messages: list[ChatMessage] = [ChatMessage(role="system", content=SENIOR_SYSTEM_PROMPT)]
    for msg in recent:
        if msg.role == "user":
            messages.append(ChatMessage(role="user", content=msg.content))
        elif msg.role == "assistant":
            messages.append(ChatMessage(role="assistant", content=msg.content))
    messages.append(ChatMessage(role="user", content=question))
    return messages


class QaService:
    def __init__(
        self,
        session: AsyncSession,
        context_store: QaContextStore | None = None,
    ) -> None:
        self.session = session
        self.context_store = context_store or QaContextStore()

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
        question: str,
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
            qa = await self._create_session(user_id, lang, _truncate_title(question))
            await self.context_store.set(user_id, qa.id)
            continued = False
            history: list[QaMessage] = []
        else:
            history = list(qa.messages)

        next_turn = (history[-1].turn_index + 1) if history else 1
        return qa, history, continued, next_turn

    def _build_completion_request(
        self,
        history: list[QaMessage],
        question: str,
        user_id: str,
        *,
        stream: bool,
    ) -> ChatCompletionRequest:
        settings = get_settings()
        return ChatCompletionRequest(
            model=settings.openai_model if settings.ai_gateway_provider == "openai" else settings.ai_gateway_provider,
            messages=_history_to_openai_messages(history, question),
            stream=stream,
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
        """SSE 事件流：meta → token* → done（或 error）。内部走 OpenAI 协议。"""
        question = question.strip()
        if not question:
            raise AppError("问题不能为空", code="empty_question", status_code=400)

        qa, history, continued, next_turn = await self._resolve_session(
            user_id, question, lang, new_context=new_context
        )
        await self.session.commit()

        yield {
            "type": "meta",
            "context_id": qa.id,
            "lang": qa.lang,
            "question_text": question,
            "context_continued": continued,
            "turn_index_user": next_turn,
            "turn_index_assistant": next_turn + 1,
        }

        gateway = create_gateway()
        chunks: list[str] = []
        try:
            req = self._build_completion_request(history, question, user_id, stream=True)
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
