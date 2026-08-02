from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, SoftDeleteMixin
from app.utils.ids import new_uuid

if TYPE_CHECKING:
    from app.db.models.media import MediaFile
    from app.db.models.user import User


class VoiceRecognizeJob(CreatedAtMixin, Base):
    __tablename__ = "voice_recognize_jobs"
    __table_args__ = (
        CheckConstraint("lang IN ('zh', 'en')", name="voice_lang"),
        CheckConstraint("status IN ('pending', 'succeeded', 'failed')", name="voice_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", name="fk_voice_jobs_user"),
        nullable=False,
        index=True,
    )
    media_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("media_files.id", name="fk_voice_jobs_media"),
        nullable=True,
    )
    lang: Mapped[str] = mapped_column(String(8), nullable=False, default="zh")
    recognized_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="succeeded")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped[User] = relationship(back_populates="voice_jobs")
    media: Mapped[MediaFile | None] = relationship(back_populates="voice_jobs")
    qa_messages: Mapped[list[QaMessage]] = relationship(back_populates="voice_job")


class QaSession(SoftDeleteMixin, Base):
    """多轮问询会话容器；id 即为对外唯一 session_id。"""

    __tablename__ = "qa_sessions"
    __table_args__ = (
        CheckConstraint("lang IN ('zh', 'en')", name="qa_lang"),
        CheckConstraint("status IN ('active', 'closed')", name="qa_session_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", name="fk_qa_sessions_user"),
        nullable=False,
        index=True,
    )
    lang: Mapped[str] = mapped_column(String(8), nullable=False, default="zh")
    title: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped[User] = relationship(back_populates="qa_sessions")
    messages: Mapped[list[QaMessage]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="QaMessage.turn_index",
    )
    recommendation: Mapped[QaRecommendation | None] = relationship(
        back_populates="session",
        uselist=False,
        cascade="all, delete-orphan",
    )


class QaMessage(CreatedAtMixin, Base):
    """会话内单条消息；按 turn_index 还原多轮上下文。"""

    __tablename__ = "qa_messages"
    __table_args__ = (
        UniqueConstraint("session_id", "turn_index", name="uq_qa_messages_session_turn"),
        CheckConstraint("role IN ('user', 'assistant', 'system')", name="qa_msg_role"),
        CheckConstraint(
            "input_mode IS NULL OR input_mode IN ('voice', 'text')",
            name="qa_msg_input_mode",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("qa_sessions.id", ondelete="CASCADE", name="fk_qa_messages_session"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", name="fk_qa_messages_user"),
        nullable=False,
        index=True,
    )
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    input_mode: Mapped[str | None] = mapped_column(String(16), nullable=True)
    audio_media_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("media_files.id", name="fk_qa_messages_audio"),
        nullable=True,
    )
    voice_job_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("voice_recognize_jobs.id", name="fk_qa_messages_voice_job"),
        nullable=True,
    )

    session: Mapped[QaSession] = relationship(back_populates="messages")
    user: Mapped[User] = relationship(back_populates="qa_messages")
    audio_media: Mapped[MediaFile | None] = relationship(
        back_populates="qa_messages_as_audio",
        foreign_keys=[audio_media_id],
    )
    voice_job: Mapped[VoiceRecognizeJob | None] = relationship(back_populates="qa_messages")


class QaRecommendation(CreatedAtMixin, Base):
    __tablename__ = "qa_recommendations"
    __table_args__ = (
        UniqueConstraint("session_id", name="uq_qa_recommendations_session"),
        CheckConstraint("risk_level IN ('low', 'medium', 'high')", name="risk"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("qa_sessions.id", ondelete="CASCADE", name="fk_qa_reco_session"),
        nullable=False,
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", name="fk_qa_reco_user"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False, default="low")
    disclaimer: Mapped[str] = mapped_column(Text, nullable=False)

    session: Mapped[QaSession] = relationship(back_populates="recommendation")
    user: Mapped[User] = relationship(back_populates="qa_recommendations")
