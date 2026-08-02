from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.db.models.qa import QaMessage, QaSession
from app.gateways.registry import create_gateway
from app.schemas.chat import ChatRequest
from app.schemas.qa import TextAskResponse
from app.services.context_store import QaContextStore
from app.utils.ids import new_uuid


def _fmt_utc(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    else:
        dt = dt.astimezone(UTC)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _truncate_title(question: str, limit: int = 40) -> str:
    text = question.strip().replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _build_prompt(history: list[QaMessage], question: str) -> str:
    settings = get_settings()
    recent = history[-settings.qa_context_history_limit :]
    lines: list[str] = [
        "你是适老化语音问答助手，请用简短、清楚、口语化的中文回答老人的问题。",
        "以下是同一段对话的历史，请结合上下文回答最后一句用户问题。",
        "",
    ]
    for msg in recent:
        speaker = "用户" if msg.role == "user" else "助手"
        lines.append(f"{speaker}：{msg.content}")
    lines.append(f"用户：{question}")
    lines.append("助手：")
    return "\n".join(lines)


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

    async def ask_text(
        self,
        user_id: str,
        question: str,
        lang: str = "zh",
        *,
        new_context: bool = False,
    ) -> TextAskResponse:
        question = question.strip()
        if not question:
            raise AppError("问题不能为空", code="empty_question", status_code=400)

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
                    # Redis 有值但库中会话不可用 → 当作过期
                    await self.context_store.clear(user_id)

        if qa is None:
            qa = await self._create_session(user_id, lang, _truncate_title(question))
            await self.context_store.set(user_id, qa.id)
            continued = False
            history: list[QaMessage] = []
        else:
            history = list(qa.messages)

        next_turn = (history[-1].turn_index + 1) if history else 1

        gateway = create_gateway(get_settings().ai_gateway_provider)
        try:
            prompt = _build_prompt(history, question)
            ai = await gateway.complete(ChatRequest(message=prompt, client_id=user_id))
            answer = ai.message.strip() or "我暂时没有想好怎么回答，请您再说一遍。"
        finally:
            await gateway.close()

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
        qa.message_count = next_turn + 1
        qa.last_message_at = now
        if not qa.title:
            qa.title = _truncate_title(question)
        await self.session.commit()

        return TextAskResponse(
            context_id=qa.id,
            lang=qa.lang,  # type: ignore[arg-type]
            question_text=question,
            answer_text=answer,
            turn_index_user=user_msg.turn_index,
            turn_index_assistant=assistant_msg.turn_index,
            context_continued=continued,
            created_at=_fmt_utc(now),
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
