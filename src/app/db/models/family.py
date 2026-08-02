from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, SoftDeleteMixin, TimestampMixin
from app.utils.ids import new_uuid

if TYPE_CHECKING:
    from app.db.models.archive import ArchiveShare
    from app.db.models.user import User


class FamilyContact(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "family_contacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", name="fk_family_contacts_user"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    relation: Mapped[str | None] = mapped_column(String(32), nullable=True)

    user: Mapped[User] = relationship(back_populates="family_contacts")
    archive_shares: Mapped[list[ArchiveShare]] = relationship(back_populates="contact")


class FamilyPushRule(Base):
    __tablename__ = "family_push_rules"

    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE", name="fk_family_push_rules_user"),
        primary_key=True,
    )
    on_record_saved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    on_abnormal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    on_visit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped[User] = relationship(back_populates="family_push_rules")
