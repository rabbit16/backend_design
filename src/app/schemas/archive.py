from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

ArchiveSource = Literal["camera", "album"]
OcrDocumentType = Literal["visit", "exam"]
OcrRiskLevel = Literal["low", "medium", "high"]


class OcrFinding(BaseModel):
    title: str
    suggestion: str
    risk_level: OcrRiskLevel | None = None
    sort_order: int = 0


class OcrResult(BaseModel):
    """OCR 结果；识别成功后已写入对应表。"""

    document_type: OcrDocumentType = "visit"
    id: str | None = None
    diagnosis: str
    medicine: str
    visit_date: date
    visit_no: str
    raw_ocr_text: str
    patient_name: str | None = None
    org_name: str | None = None
    voucher_no: str | None = None
    report_type: str | None = None
    findings: list[OcrFinding] = Field(default_factory=list)


class ArchiveRecord(BaseModel):
    id: str
    diagnosis: str
    medicine: str
    visit_date: date
    visit_no: str
    raw_ocr_text: str | None = None
    image_url: str | None = None
    created_at: str
    updated_at: str


class ArchiveListResponse(BaseModel):
    items: list[ArchiveRecord]
    total: int
    page: int
    page_size: int


class CreateArchiveRequest(BaseModel):
    diagnosis: str = Field(min_length=1)
    medicine: str = Field(min_length=1)
    visit_date: date
    visit_no: str = Field(min_length=1, max_length=64)
    raw_ocr_text: str | None = None
    image_url: str | None = None
    source: ArchiveSource | None = None


class UpdateArchiveRequest(BaseModel):
    diagnosis: str | None = Field(default=None, min_length=1)
    medicine: str | None = Field(default=None, min_length=1)
    visit_date: date | None = None
    visit_no: str | None = Field(default=None, min_length=1, max_length=64)


class ShareArchiveRequest(BaseModel):
    contact_ids: list[str] = Field(min_length=1)
    message: str | None = None


class ShareArchiveResponse(BaseModel):
    ok: bool = True
    shared_count: int


class ExportPdfResponse(BaseModel):
    download_url: str
    expires_in: int


class OkResponse(BaseModel):
    ok: bool = True
