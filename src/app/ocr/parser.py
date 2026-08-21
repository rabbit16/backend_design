from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from src.app.core.exceptions import AppError
from src.app.schemas.archive import OcrDocumentType, OcrFinding, OcrResult
from src.app.utils.ids import new_uuid

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)
_CN_DATE_RE = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")

_EXAM_TYPE_HINTS = (
    "exam",
    "checkup",
    "physical",
    "tijian",
    "体检",
    "体检单",
    "体检报告",
    "健康体检",
    "健康报告",
)
_VISIT_TYPE_HINTS = (
    "visit",
    "archive",
    "clinic",
    "outpatient",
    "处方",
    "病历",
    "就诊",
    "就诊单",
    "门诊",
    "出院",
    "就医指引",
    "取药",
)

_STRONG_EXAM_HINTS = ("体检报告", "健康体检")
_STRONG_VISIT_HINTS = ("就医指引", "门诊药房", "看诊科室", "取药单", "处方笺")
_EMPTY_MEDICINE = frozenset({"", "未见用药信息", "见体检建议", "按医嘱", "按医嘱服用"})


class OcrFindingPayload(BaseModel):
    title: str = ""
    suggestion: str = ""
    risk_level: str | None = None

    @field_validator("title", "suggestion", mode="before")
    @classmethod
    def _stringify(cls, value: object) -> str:
        if value is None:
            return ""
        return str(value).strip()

    @field_validator("risk_level", mode="before")
    @classmethod
    def _risk(cls, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip().lower()
        if not text:
            return None
        mapping = {"低": "low", "中": "medium", "高": "high", "中等": "medium"}
        mapped = mapping.get(text, text)
        if mapped in {"low", "medium", "high"}:
            return mapped
        return None


class OcrLlmPayload(BaseModel):
    """模型输出的中间结构；缺省字段由解析器补全。"""

    document_type: str = "visit"
    diagnosis: str = ""
    medicine: str = ""
    visit_date: str = ""
    visit_no: str = ""
    raw_ocr_text: str = ""
    patient_name: str = ""
    exam_date: str = ""
    org_name: str = ""
    voucher_no: str = ""
    report_type: str = ""
    findings: list[OcrFindingPayload] = Field(default_factory=list)

    @field_validator(
        "document_type",
        "diagnosis",
        "medicine",
        "visit_date",
        "visit_no",
        "raw_ocr_text",
        "patient_name",
        "exam_date",
        "org_name",
        "voucher_no",
        "report_type",
        mode="before",
    )
    @classmethod
    def _stringify(cls, value: object) -> str:
        if value is None:
            return ""
        return str(value).strip()

    @field_validator("findings", mode="before")
    @classmethod
    def _findings(cls, value: object) -> list[Any]:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        return []


class ExtractedDocument(BaseModel):
    document_type: OcrDocumentType
    raw_ocr_text: str
    diagnosis: str
    medicine: str
    visit_date: date
    visit_no: str
    patient_name: str = ""
    exam_date: date | None = None
    org_name: str = ""
    voucher_no: str = ""
    report_type: str = "体检报告"
    findings: list[OcrFinding] = Field(default_factory=list)

    def to_ocr_result(self, saved_id: str) -> OcrResult:
        if self.document_type == "exam":
            first = self.findings[0] if self.findings else None
            diagnosis = self.diagnosis or (first.title if first else "体检报告")
            medicine = self.medicine or (first.suggestion if first else "见体检建议")
            visit_date = self.exam_date or self.visit_date
            visit_no = self.voucher_no or self.visit_no
            return OcrResult(
                document_type="exam",
                id=saved_id,
                diagnosis=diagnosis,
                medicine=medicine,
                visit_date=visit_date,
                visit_no=visit_no,
                raw_ocr_text=self.raw_ocr_text,
                patient_name=self.patient_name or None,
                org_name=self.org_name or None,
                voucher_no=self.voucher_no or visit_no,
                report_type=self.report_type or "体检报告",
                findings=self.findings,
            )
        return OcrResult(
            document_type="visit",
            id=saved_id,
            diagnosis=self.diagnosis,
            medicine=self.medicine,
            visit_date=self.visit_date,
            visit_no=self.visit_no,
            raw_ocr_text=self.raw_ocr_text,
        )


def ocr_json_schema_text() -> str:
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "document_type",
            "diagnosis",
            "medicine",
            "visit_date",
            "visit_no",
            "raw_ocr_text",
        ],
        "properties": {
            "document_type": {
                "type": "string",
                "enum": ["visit", "exam"],
                "description": "visit=就诊/就医指引/取药/处方；exam=体检报告（不是指引单上的检验小节）",
            },
            "diagnosis": {"type": "string", "description": "主诊断；没有则空字符串，禁止编造"},
            "medicine": {
                "type": "string",
                "description": "药品栏目逐条：药名+规格+用法；没有药品则空字符串",
            },
            "visit_date": {"type": "string", "description": "就诊/打印日期 YYYY-MM-DD；没有则空"},
            "visit_no": {
                "type": "string",
                "description": "仅抄就诊号/门诊号/病历号；没有则空字符串，禁止编造",
            },
            "patient_name": {"type": "string", "description": "体检单：姓名"},
            "exam_date": {"type": "string", "description": "体检日期 YYYY-MM-DD"},
            "org_name": {"type": "string", "description": "体检机构"},
            "voucher_no": {
                "type": "string",
                "description": "仅抄体检凭证号；没有则空字符串，禁止编造",
            },
            "report_type": {"type": "string", "description": "默认 体检报告"},
            "findings": {
                "type": "array",
                "description": "仅 exam 的异常项",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "suggestion": {"type": "string"},
                        "risk_level": {"type": "string", "enum": ["low", "medium", "high"]},
                    },
                },
            },
            "raw_ocr_text": {"type": "string", "description": "最后填写：图片全文转写"},
        },
    }
    return json.dumps(schema, ensure_ascii=False, indent=2)


def openai_json_object_format() -> dict[str, str]:
    return {"type": "json_object"}


def fallback_visit_no(visit_date: date | None = None) -> str:
    """库表 visit_no 非空且需唯一；前缀标明不是单据上的真编号。"""
    day = visit_date or date.today()
    return f"未编号-{day.strftime('%Y%m%d')}-{new_uuid().replace('-', '')[:6].upper()}"


def fallback_voucher_no(exam_date: date | None = None) -> str:
    day = exam_date or date.today()
    return f"未编号-{day.strftime('%Y%m%d')}-{new_uuid().replace('-', '')[:6].upper()}"


def parse_visit_date(value: str) -> date | None:
    text = value.strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    matched = _CN_DATE_RE.search(text)
    if matched:
        try:
            return date(int(matched.group(1)), int(matched.group(2)), int(matched.group(3)))
        except ValueError:
            return None
    return None


def loads_json_object(text: str) -> dict[str, object]:
    stripped = _FENCE_RE.sub("", text.strip()).strip()
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end <= start:
            raise AppError(
                "模型未返回可解析的 JSON",
                code="ocr_invalid_json",
                status_code=502,
            ) from None
        try:
            data = json.loads(stripped[start : end + 1])
        except json.JSONDecodeError as exc:
            raise AppError(
                "模型未返回可解析的 JSON",
                code="ocr_invalid_json",
                status_code=502,
            ) from exc
    if not isinstance(data, dict):
        raise AppError("模型 JSON 必须是对象", code="ocr_invalid_json", status_code=502)
    return data


def normalize_document_type(payload: OcrLlmPayload) -> OcrDocumentType:
    blob = f"{payload.document_type}\n{payload.raw_ocr_text}"
    strong_exam = any(hint in blob for hint in _STRONG_EXAM_HINTS)
    strong_visit = any(hint in blob for hint in _STRONG_VISIT_HINTS)
    if strong_visit and not strong_exam:
        return "visit"
    if strong_exam and not strong_visit:
        return "exam"

    raw = payload.document_type.strip().lower()
    compact = raw.replace(" ", "")
    if any(hint in compact for hint in _EXAM_TYPE_HINTS):
        return "exam"
    if any(hint in compact for hint in _VISIT_TYPE_HINTS):
        return "visit"
    if payload.findings or payload.org_name or payload.voucher_no or payload.patient_name:
        if not payload.diagnosis and not payload.visit_no and not payload.medicine:
            return "exam"
        if payload.findings and not payload.medicine:
            return "exam"
    return "visit"


def medicine_from_raw_text(raw: str) -> str:
    """原文有「药品」栏目时，从全文补结构化用药（模型漏填的兜底）。"""
    if not raw.strip():
        return ""
    matched = re.search(
        r"药品[^\n]*\n(?P<body>.*?)(?=\n(?:检验|检查项目|第\s*\d+\s*页)|$)",
        raw,
        flags=re.S,
    )
    body = matched.group("body") if matched else ""
    if not body.strip() and "药品" in raw:
        body = raw.split("药品", 1)[-1]
    lines: list[str] = []
    for line in body.splitlines():
        text = line.strip()
        if not text:
            continue
        if text.startswith("检验") or text.startswith("检查项目"):
            break
        lines.append(text)
        if len(lines) >= 16:
            break
    return "\n".join(lines).strip()


def reject_unprinted_id(value: str, raw_ocr_text: str) -> str:
    """全文较长时，编号必须在原文中出现，否则视为编造。"""
    text = value.strip()
    if not text:
        return ""
    if len(raw_ocr_text) < 40:
        return text
    if text in raw_ocr_text:
        return text
    compact = re.sub(r"\s+", "", text)
    if compact and compact in re.sub(r"\s+", "", raw_ocr_text):
        return text
    return ""


def resolve_medicine(payload_medicine: str, raw_ocr_text: str) -> str:
    current = payload_medicine.strip()
    if current and current not in _EMPTY_MEDICINE:
        return current
    salvaged = medicine_from_raw_text(raw_ocr_text)
    return salvaged or current or "未见用药信息"


def _to_findings(items: list[OcrFindingPayload]) -> list[OcrFinding]:
    findings: list[OcrFinding] = []
    for item in items:
        title = item.title.strip()
        suggestion = item.suggestion.strip()
        if not title and not suggestion:
            continue
        findings.append(
            OcrFinding(
                title=title or "异常项",
                suggestion=suggestion or "建议结合纸质报告或到医院复查",
                risk_level=item.risk_level,  # type: ignore[arg-type]
                sort_order=len(findings),
            )
        )
    return findings


class OcrResultParser:
    def parse(self, content: str, *, raw_fallback: str = "") -> ExtractedDocument:
        if not content.strip():
            raise AppError("模型未返回识别结果", code="ocr_empty_response", status_code=502)
        payload = OcrLlmPayload.model_validate(loads_json_object(content))
        document_type = normalize_document_type(payload)
        raw_ocr_text = payload.raw_ocr_text or raw_fallback or content.strip()

        if document_type == "exam":
            exam_date = (
                parse_visit_date(payload.exam_date)
                or parse_visit_date(payload.visit_date)
                or date.today()
            )
            voucher_no = (
                reject_unprinted_id(payload.voucher_no, raw_ocr_text)
                or reject_unprinted_id(payload.visit_no, raw_ocr_text)
                or fallback_voucher_no(exam_date)
            )
            findings = _to_findings(payload.findings)
            if not findings:
                findings = [
                    OcrFinding(
                        title="未见明确异常项",
                        suggestion="建议结合纸质报告或到医院复查",
                        risk_level=None,
                        sort_order=0,
                    )
                ]
            return ExtractedDocument(
                document_type="exam",
                raw_ocr_text=raw_ocr_text,
                diagnosis=payload.diagnosis or findings[0].title,
                medicine=payload.medicine.strip() or "见体检建议",
                visit_date=exam_date,
                visit_no=voucher_no,
                patient_name=payload.patient_name or "未识别姓名",
                exam_date=exam_date,
                org_name=payload.org_name or "未识别机构",
                voucher_no=voucher_no,
                report_type=payload.report_type or "体检报告",
                findings=findings,
            )

        visit_date = (
            parse_visit_date(payload.visit_date)
            or parse_visit_date(payload.exam_date)
            or date.today()
        )
        printed_no = reject_unprinted_id(payload.visit_no, raw_ocr_text) or reject_unprinted_id(
            payload.voucher_no, raw_ocr_text
        )
        visit_no = printed_no or fallback_visit_no(visit_date)
        return ExtractedDocument(
            document_type="visit",
            raw_ocr_text=raw_ocr_text,
            diagnosis=payload.diagnosis or "未能识别诊断",
            medicine=resolve_medicine(payload.medicine, raw_ocr_text),
            visit_date=visit_date,
            visit_no=visit_no,
        )
