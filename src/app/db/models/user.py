from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, SoftDeleteMixin, TimestampMixin
from app.utils.ids import new_uuid

if TYPE_CHECKING:
    from app.db.models.archive import ArchiveExport, ArchiveOcrJob, ArchiveShare, MedicalArchive
    from app.db.models.family import FamilyContact, FamilyPushRule
    from app.db.models.health import HealthReport, HealthSummary
    from app.db.models.media import MediaFile
    from app.db.models.qa import QaMessage, QaRecommendation, QaSession, VoiceRecognizeJob


class User(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("phone", name="uq_users_phone"),
        CheckConstraint("preferred_lang IN ('zh', 'en')", name="lang"),
        CheckConstraint("status IN ('active', 'disabled')", name="status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    phone: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    preferred_lang: Mapped[str] = mapped_column(String(8), nullable=False, default="zh")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")

    preferences: Mapped[UserPreference | None] = relationship(
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    sessions: Mapped[list[AuthSession]] = relationship(back_populates="user")
    media_files: Mapped[list[MediaFile]] = relationship(back_populates="user")
    voice_jobs: Mapped[list[VoiceRecognizeJob]] = relationship(back_populates="user")
    qa_sessions: Mapped[list[QaSession]] = relationship(back_populates="user")
    qa_messages: Mapped[list[QaMessage]] = relationship(back_populates="user")
    qa_recommendations: Mapped[list[QaRecommendation]] = relationship(back_populates="user")
    medical_archives: Mapped[list[MedicalArchive]] = relationship(back_populates="user")
    archive_ocr_jobs: Mapped[list[ArchiveOcrJob]] = relationship(back_populates="user")
    archive_shares: Mapped[list[ArchiveShare]] = relationship(back_populates="user")
    archive_exports: Mapped[list[ArchiveExport]] = relationship(back_populates="user")
    health_summaries: Mapped[list[HealthSummary]] = relationship(back_populates="user")
    health_reports: Mapped[list[HealthReport]] = relationship(back_populates="user")
    family_contacts: Mapped[list[FamilyContact]] = relationship(back_populates="user")
    family_push_rules: Mapped[FamilyPushRule | None] = relationship(
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )


class SmsCode(CreatedAtMixin, Base):
    __tablename__ = "sms_codes"
    __table_args__ = (
        CheckConstraint("purpose IN ('login', 'register', 'reset_password')", name="sms_purpose"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    phone: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(8), nullable=False)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False, default="login")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    request_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)


class AuthSession(CreatedAtMixin, Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (UniqueConstraint("refresh_token_hash", name="uq_auth_sessions_refresh"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", name="fk_auth_sessions_user"),
        nullable=False,
        index=True,
    )
    refresh_token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    device_info: Mapped[str | None] = mapped_column(String(255), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="sessions")


class UserPreference(Base):
    __tablename__ = "user_preferences"
    __table_args__ = (CheckConstraint("preferred_lang IN ('zh', 'en')", name="pref_lang"),)

    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE", name="fk_user_preferences_user"),
        primary_key=True,
    )
    preferred_lang: Mapped[str] = mapped_column(String(8), nullable=False, default="zh")
    font_scale: Mapped[Decimal] = mapped_column(
        Numeric(3, 2),
        nullable=False,
        default=Decimal("1.00"),
    )
    high_contrast: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped[User] = relationship(back_populates="preferences")
