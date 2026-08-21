from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from src.app.db.base import Base, CreatedAtMixin, SoftDeleteMixin, TimestampMixin
from src.app.utils.ids import new_uuid

if TYPE_CHECKING:
    from src.app.db.models.media import MediaFile
    from src.app.db.models.user import User


class HealthSummary(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "health_summaries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", name="fk_health_summaries_user"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(128), nullable=False, default="健康问题总结")
    exam_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    exam_no: Mapped[str | None] = mapped_column(String(64), nullable=True)
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)

    user: Mapped[User] = relationship(back_populates="health_summaries")
    items: Mapped[list[HealthSummaryItem]] = relationship(
        back_populates="summary",
        cascade="all, delete-orphan",
        order_by="HealthSummaryItem.sort_order",
    )


class HealthSummaryItem(CreatedAtMixin, Base):
    __tablename__ = "health_summary_items"
    __table_args__ = (
        CheckConstraint(
            "severity IS NULL OR severity IN ('low', 'medium', 'high')",
            name="summary_item_sev",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    summary_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("health_summaries.id", ondelete="CASCADE", name="fk_health_summary_items_summary"),
        nullable=False,
        index=True,
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str | None] = mapped_column(String(16), nullable=True)

    summary: Mapped[HealthSummary] = relationship(back_populates="items")


class HealthReport(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "health_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", name="fk_health_reports_user"),
        nullable=False,
        index=True,
    )
    patient_name: Mapped[str] = mapped_column(String(64), nullable=False)
    exam_date: Mapped[date] = mapped_column(Date, nullable=False)
    org_name: Mapped[str] = mapped_column(String(128), nullable=False)
    voucher_no: Mapped[str] = mapped_column(String(64), nullable=False)
    report_type: Mapped[str] = mapped_column(String(32), nullable=False, default="体检报告")
    pdf_media_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("media_files.id", name="fk_health_reports_pdf"),
        nullable=True,
    )
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    user: Mapped[User] = relationship(back_populates="health_reports")
    pdf_media: Mapped[MediaFile | None] = relationship(back_populates="health_reports")
    findings: Mapped[list[HealthReportFinding]] = relationship(
        back_populates="report",
        cascade="all, delete-orphan",
        order_by="HealthReportFinding.sort_order",
    )


class HealthReportFinding(CreatedAtMixin, Base):
    __tablename__ = "health_report_findings"
    __table_args__ = (
        CheckConstraint(
            "risk_level IS NULL OR risk_level IN ('low', 'medium', 'high')",
            name="finding_risk",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    report_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("health_reports.id", ondelete="CASCADE", name="fk_report_findings_report"),
        nullable=False,
        index=True,
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    suggestion: Mapped[str] = mapped_column(Text, nullable=False)
    risk_level: Mapped[str | None] = mapped_column(String(16), nullable=True)

    report: Mapped[HealthReport] = relationship(back_populates="findings")


class ReportGlossary(CreatedAtMixin, Base):
    __tablename__ = "report_glossaries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    term: Mapped[str] = mapped_column(String(64), nullable=False)
    definition: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
