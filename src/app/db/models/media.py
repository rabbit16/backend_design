from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, SoftDeleteMixin
from app.utils.ids import new_uuid

if TYPE_CHECKING:
    from app.db.models.archive import ArchiveExport, ArchiveOcrJob, MedicalArchive
    from app.db.models.health import HealthReport
    from app.db.models.qa import QaSession, VoiceRecognizeJob
    from app.db.models.user import User


class MediaFile(CreatedAtMixin, SoftDeleteMixin, Base):
    __tablename__ = "media_files"
    __table_args__ = (
        CheckConstraint("kind IN ('audio', 'image', 'pdf', 'other')", name="media_kind"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", name="fk_media_files_user"),
        nullable=False,
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)

    user: Mapped[User] = relationship(back_populates="media_files")
    voice_jobs: Mapped[list[VoiceRecognizeJob]] = relationship(back_populates="media")
    qa_sessions_as_audio: Mapped[list[QaSession]] = relationship(
        back_populates="audio_media",
        foreign_keys="QaSession.audio_media_id",
    )
    medical_archives: Mapped[list[MedicalArchive]] = relationship(back_populates="image_media")
    archive_ocr_jobs: Mapped[list[ArchiveOcrJob]] = relationship(back_populates="image_media")
    archive_exports: Mapped[list[ArchiveExport]] = relationship(back_populates="pdf_media")
    health_reports: Mapped[list[HealthReport]] = relationship(back_populates="pdf_media")
