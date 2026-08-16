from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AppError
from app.db.models.health import HealthReport, HealthSummary, ReportGlossary
from app.schemas.health_profile import (
    GlossaryItemOut,
    GlossaryListResponse,
    HealthReportDetail,
    HealthReportFindingOut,
    HealthReportListItem,
    HealthReportListResponse,
    HealthSummaryItemOut,
    HealthSummaryListResponse,
    HealthSummaryOut,
)
from app.utils.timefmt import fmt_utc


def _full_text_from_payload(raw: dict[str, Any] | None) -> str | None:
    if not isinstance(raw, dict):
        return None
    value = raw.get("full_text")
    if isinstance(value, str) and value.strip():
        return value
    return None


class HealthProfileService:
    """档案首页：健康问题总结 + 体检报告时间轴。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _summary_out(self, row: HealthSummary) -> HealthSummaryOut:
        items = [
            HealthSummaryItemOut(
                id=item.id,
                content=item.content,
                severity=item.severity,  # type: ignore[arg-type]
                sort_order=item.sort_order,
            )
            for item in sorted(row.items, key=lambda x: x.sort_order)
        ]
        return HealthSummaryOut(
            id=row.id,
            title=row.title,
            exam_date=row.exam_date,
            exam_no=row.exam_no,
            summary_text=row.summary_text,
            items=items,
            created_at=fmt_utc(row.created_at),
            updated_at=fmt_utc(row.updated_at),
        )

    async def list_summaries(self, user_id: str) -> HealthSummaryListResponse:
        result = await self.session.execute(
            select(HealthSummary)
            .where(
                HealthSummary.user_id == user_id,
                HealthSummary.deleted_at.is_(None),
            )
            .options(selectinload(HealthSummary.items))
            .order_by(HealthSummary.updated_at.desc())
        )
        rows = result.scalars().unique().all()
        return HealthSummaryListResponse(items=[self._summary_out(r) for r in rows])

    async def list_reports(
        self,
        user_id: str,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> HealthReportListResponse:
        page = max(page, 1)
        page_size = min(max(page_size, 1), 100)
        filters = [
            HealthReport.user_id == user_id,
            HealthReport.deleted_at.is_(None),
        ]
        total = (
            await self.session.execute(select(func.count()).select_from(HealthReport).where(*filters))
        ).scalar_one()
        result = await self.session.execute(
            select(HealthReport)
            .where(*filters)
            .order_by(HealthReport.exam_date.desc(), HealthReport.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = result.scalars().all()
        return HealthReportListResponse(
            items=[
                HealthReportListItem(
                    id=r.id,
                    patient_name=r.patient_name,
                    exam_date=r.exam_date,
                    org_name=r.org_name,
                    voucher_no=r.voucher_no,
                    report_type=r.report_type,
                )
                for r in rows
            ],
            total=int(total),
            page=page,
            page_size=page_size,
        )

    async def get_report(self, user_id: str, report_id: str) -> HealthReportDetail:
        result = await self.session.execute(
            select(HealthReport)
            .where(
                HealthReport.id == report_id,
                HealthReport.user_id == user_id,
                HealthReport.deleted_at.is_(None),
            )
            .options(selectinload(HealthReport.findings))
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise AppError("报告不存在", code="report_not_found", status_code=404)

        findings = [
            HealthReportFindingOut(
                id=f.id,
                title=f.title,
                suggestion=f.suggestion,
                risk_level=f.risk_level,  # type: ignore[arg-type]
                sort_order=f.sort_order,
            )
            for f in sorted(row.findings, key=lambda x: x.sort_order)
        ]
        glossary = await self._glossary_items()
        return HealthReportDetail(
            id=row.id,
            patient_name=row.patient_name,
            exam_date=row.exam_date,
            org_name=row.org_name,
            voucher_no=row.voucher_no,
            report_type=row.report_type,
            findings=findings,
            full_text=_full_text_from_payload(row.raw_payload),
            glossary=glossary,
        )

    async def list_glossaries(self) -> GlossaryListResponse:
        return GlossaryListResponse(items=await self._glossary_items())

    async def _glossary_items(self) -> list[GlossaryItemOut]:
        result = await self.session.execute(
            select(ReportGlossary)
            .where(ReportGlossary.enabled.is_(True))
            .order_by(ReportGlossary.sort_order.asc(), ReportGlossary.created_at.asc())
        )
        rows = result.scalars().all()
        return [
            GlossaryItemOut(
                id=g.id,
                term=g.term,
                definition=g.definition,
                sort_order=g.sort_order,
            )
            for g in rows
        ]
