from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, SoftDeleteMixin, TimestampMixin
from app.utils.ids import new_uuid

if TYPE_CHECKING:
    from app.db.models.family import FamilyContact
    from app.db.models.media import MediaFile
    from app.db.models.user import User


class MedicalArchive(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "medical_archives"
    __table_args__ = (
        CheckConstraint(
            "source IS NULL OR source IN ('camera', 'album')",
            name="archive_source",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", name="fk_medical_archives_user"),
        nullable=False,
        index=True,
    )
    diagnosis: Mapped[str] = mapped_column(Text, nullable=False)
    medicine: Mapped[str] = mapped_column(Text, nullable=False)
    visit_date: Mapped[date] = mapped_column(Date, nullable=False)
    raw_ocr_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_media_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("media_files.id", name="fk_medical_archives_image"),
        nullable=True,
    )
    source: Mapped[str | None] = mapped_column(String(16), nullable=True)

    user: Mapped[User] = relationship(back_populates="medical_archives")
    image_media: Mapped[MediaFile | None] = relationship(back_populates="medical_archives")
    shares: Mapped[list[ArchiveShare]] = relationship(
        back_populates="archive",
        cascade="all, delete-orphan",
    )
    exports: Mapped[list[ArchiveExport]] = relationship(
        back_populates="archive",
        cascade="all, delete-orphan",
    )


class ArchiveOcrJob(CreatedAtMixin, Base):
    __tablename__ = "archive_ocr_jobs"
    __table_args__ = (
        CheckConstraint("source IN ('camera', 'album')", name="ocr_source"),
        CheckConstraint("status IN ('pending', 'succeeded', 'failed')", name="ocr_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", name="fk_archive_ocr_jobs_user"),
        nullable=False,
        index=True,
    )
    image_media_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("media_files.id", name="fk_archive_ocr_jobs_image"),
        nullable=True,
    )
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    diagnosis: Mapped[str | None] = mapped_column(Text, nullable=True)
    medicine: Mapped[str | None] = mapped_column(Text, nullable=True)
    visit_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    raw_ocr_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="succeeded")

    user: Mapped[User] = relationship(back_populates="archive_ocr_jobs")
    image_media: Mapped[MediaFile | None] = relationship(back_populates="archive_ocr_jobs")


class ArchiveShare(CreatedAtMixin, Base):
    __tablename__ = "archive_shares"
    __table_args__ = (
        CheckConstraint("status IN ('queued', 'sent', 'failed')", name="share_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    archive_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("medical_archives.id", ondelete="CASCADE", name="fk_archive_shares_archive"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", name="fk_archive_shares_user"),
        nullable=False,
    )
    contact_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("family_contacts.id", name="fk_archive_shares_contact"),
        nullable=False,
    )
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    archive: Mapped[MedicalArchive] = relationship(back_populates="shares")
    user: Mapped[User] = relationship(back_populates="archive_shares")
    contact: Mapped[FamilyContact] = relationship(back_populates="archive_shares")


class ArchiveExport(CreatedAtMixin, Base):
    __tablename__ = "archive_exports"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'ready', 'failed')", name="export_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    archive_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("medical_archives.id", ondelete="CASCADE", name="fk_archive_exports_archive"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", name="fk_archive_exports_user"),
        nullable=False,
    )
    pdf_media_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("media_files.id", name="fk_archive_exports_pdf"),
        nullable=True,
    )
    download_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ready")

    archive: Mapped[MedicalArchive] = relationship(back_populates="exports")
    user: Mapped[User] = relationship(back_populates="archive_exports")
    pdf_media: Mapped[MediaFile | None] = relationship(back_populates="archive_exports")
