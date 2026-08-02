from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text, UniqueConstraint
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
    qa_sessions: Mapped[list[QaSession]] = relationship(back_populates="voice_job")


class QaSession(CreatedAtMixin, SoftDeleteMixin, Base):
    __tablename__ = "qa_sessions"
    __table_args__ = (
        CheckConstraint("lang IN ('zh', 'en')", name="qa_lang"),
        CheckConstraint("input_mode IN ('voice', 'text')", name="qa_input_mode"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", name="fk_qa_sessions_user"),
        nullable=False,
        index=True,
    )
    lang: Mapped[str] = mapped_column(String(8), nullable=False, default="zh")
    input_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="voice")
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    answer_text: Mapped[str] = mapped_column(Text, nullable=False)
    audio_media_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("media_files.id", name="fk_qa_sessions_audio"),
        nullable=True,
    )
    voice_job_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("voice_recognize_jobs.id", name="fk_qa_sessions_voice_job"),
        nullable=True,
    )

    user: Mapped[User] = relationship(back_populates="qa_sessions")
    audio_media: Mapped[MediaFile | None] = relationship(
        back_populates="qa_sessions_as_audio",
        foreign_keys=[audio_media_id],
    )
    voice_job: Mapped[VoiceRecognizeJob | None] = relationship(back_populates="qa_sessions")
    recommendation: Mapped[QaRecommendation | None] = relationship(
        back_populates="session",
        uselist=False,
        cascade="all, delete-orphan",
    )


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
