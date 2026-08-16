from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

Severity = Literal["low", "medium", "high"]


class HealthSummaryItemOut(BaseModel):
    id: str
    content: str
    severity: Severity | None = None
    sort_order: int


class HealthSummaryOut(BaseModel):
    id: str
    title: str
    exam_date: date | None = None
    exam_no: str | None = None
    summary_text: str
    items: list[HealthSummaryItemOut]
    created_at: str
    updated_at: str


class HealthSummaryListResponse(BaseModel):
    items: list[HealthSummaryOut]


class HealthReportListItem(BaseModel):
    id: str
    patient_name: str
    exam_date: date
    org_name: str
    voucher_no: str
    report_type: str


class HealthReportListResponse(BaseModel):
    items: list[HealthReportListItem]
    total: int
    page: int
    page_size: int


class HealthReportFindingOut(BaseModel):
    id: str
    title: str
    suggestion: str
    risk_level: Severity | None = None
    sort_order: int


class GlossaryItemOut(BaseModel):
    id: str
    term: str
    definition: str
    sort_order: int


class HealthReportDetail(BaseModel):
    id: str
    patient_name: str
    exam_date: date
    org_name: str
    voucher_no: str
    report_type: str
    findings: list[HealthReportFindingOut]
    full_text: str | None = None
    glossary: list[GlossaryItemOut] = Field(default_factory=list)


class GlossaryListResponse(BaseModel):
    items: list[GlossaryItemOut]
