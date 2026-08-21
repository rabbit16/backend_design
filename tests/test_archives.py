import asyncio
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import select

from src.app.db.models.family import FamilyContact
from src.app.db.models.health import (
    HealthReport,
    HealthReportFinding,
    HealthSummary,
    HealthSummaryItem,
    ReportGlossary,
)
from src.app.db.models.user import User
from src.app.db.session import AsyncSessionFactory
from src.app.main import create_app
from src.app.security.jwt import clear_revoked_sessions
from src.app.services.sms_service import clear_sms_store
from src.app.utils.ids import new_uuid


def _auth_headers(client: TestClient, phone: str = "13200132000") -> dict[str, str]:
    client.post("/api/v1/auth/sms/send", json={"phone": phone, "purpose": "register"})
    reg = client.post(
        "/api/v1/auth/register",
        json={"phone": phone, "code": "123456", "password": "secret12"},
    )
    if reg.status_code == 409:
        client.post("/api/v1/auth/sms/send", json={"phone": phone, "purpose": "login"})
        login = client.post(
            "/api/v1/auth/login/sms",
            json={"phone": phone, "code": "123456"},
        )
        token = login.json()["access_token"]
    else:
        assert reg.status_code == 200, reg.text
        token = reg.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _client() -> TestClient:
    clear_sms_store()
    clear_revoked_sessions()
    return TestClient(create_app())


def test_archives_crud_and_ocr() -> None:
    phone = "13200132001"
    with _client() as client:
        headers = _auth_headers(client, phone)

        ocr = client.post(
            "/api/v1/archives/ocr",
            headers=headers,
            files={"file": ("slip.jpg", b"fake-image-bytes", "image/jpeg")},
            data={"source": "camera"},
        )
        assert ocr.status_code == 200, ocr.text
        ocr_body = ocr.json()
        assert ocr_body["document_type"] == "visit"
        assert ocr_body["id"]
        assert ocr_body["diagnosis"]
        assert ocr_body["medicine"]
        assert ocr_body["visit_date"]
        assert ocr_body["visit_no"]
        assert ocr_body["raw_ocr_text"]
        assert "支气管炎" in ocr_body["diagnosis"]
        archive_id = ocr_body["id"]

        empty = client.post(
            "/api/v1/archives/ocr",
            headers=headers,
            files={"file": ("empty.jpg", b"", "image/jpeg")},
            data={"source": "album"},
        )
        assert empty.status_code == 400
        assert empty.json()["code"] == "empty_file"

        listed = client.get("/api/v1/archives?page=1&page_size=100", headers=headers)
        assert listed.status_code == 200
        body = listed.json()
        assert body["total"] >= 1
        assert body["page"] == 1
        assert body["page_size"] == 100
        item = next(i for i in body["items"] if i["id"] == archive_id)
        assert item["visit_no"] == ocr_body["visit_no"]
        assert item["visit_date"] == ocr_body["visit_date"]
        assert item["diagnosis"] == ocr_body["diagnosis"]

        dup = client.post(
            "/api/v1/archives",
            headers=headers,
            json={
                "diagnosis": ocr_body["diagnosis"],
                "medicine": ocr_body["medicine"],
                "visit_date": ocr_body["visit_date"],
                "visit_no": ocr_body["visit_no"],
                "raw_ocr_text": ocr_body["raw_ocr_text"],
                "source": "camera",
            },
        )
        assert dup.status_code == 409
        assert dup.json()["code"] == "visit_no_conflict"

        patched = client.patch(
            f"/api/v1/archives/{archive_id}",
            headers=headers,
            json={"medicine": "修订后的用药说明"},
        )
        assert patched.status_code == 200
        assert patched.json()["medicine"] == "修订后的用药说明"
        assert patched.json()["visit_no"] == ocr_body["visit_no"]

        got = client.get(f"/api/v1/archives/{archive_id}", headers=headers)
        assert got.status_code == 200
        assert got.json()["medicine"] == "修订后的用药说明"
        assert got.json()["raw_ocr_text"] == ocr_body["raw_ocr_text"]

        exported = client.get(f"/api/v1/archives/{archive_id}/export", headers=headers)
        assert exported.status_code == 200
        assert exported.json()["download_url"]
        assert exported.json()["expires_in"] == 600

        deleted = client.delete(f"/api/v1/archives/{archive_id}", headers=headers)
        assert deleted.status_code == 200
        assert deleted.json()["ok"] is True

        missing = client.get(f"/api/v1/archives/{archive_id}", headers=headers)
        assert missing.status_code == 404
        assert missing.json()["code"] == "archive_not_found"


def test_ocr_exam_saves_health_report() -> None:
    from unittest.mock import AsyncMock, patch

    from src.app.ocr.parser import ExtractedDocument
    from src.app.schemas.archive import OcrFinding

    phone = "13200132011"
    extracted = ExtractedDocument(
        document_type="exam",
        raw_ocr_text="瑞慈体检全文",
        diagnosis="体重过低",
        medicine="见体检建议",
        visit_date=date(2025, 11, 3),
        visit_no="312101033225",
        patient_name="毕小雪",
        exam_date=date(2025, 11, 3),
        org_name="瑞慈体检上海静安机构",
        voucher_no="312101033225",
        report_type="体检报告",
        findings=[
            OcrFinding(
                title="体重过低 BMI 18.2",
                suggestion="加强营养，适量运动",
                risk_level="medium",
                sort_order=0,
            )
        ],
    )
    with _client() as client:
        headers = _auth_headers(client, phone)
        with patch(
            "src.app.services.archive_service.VisionOcrExtractor.extract",
            AsyncMock(return_value=extracted),
        ):
            ocr = client.post(
                "/api/v1/archives/ocr",
                headers=headers,
                files={"file": ("exam.jpg", b"fake-image-bytes", "image/jpeg")},
                data={"source": "album"},
            )
        assert ocr.status_code == 200, ocr.text
        body = ocr.json()
        assert body["document_type"] == "exam"
        assert body["patient_name"] == "毕小雪"
        assert body["org_name"] == "瑞慈体检上海静安机构"
        assert body["voucher_no"] == "312101033225"
        assert body["findings"][0]["risk_level"] == "medium"
        report_id = body["id"]

        archives = client.get("/api/v1/archives", headers=headers)
        assert archives.json()["items"] == []

        reports = client.get("/api/v1/health-reports?page=1&page_size=100", headers=headers)
        assert reports.status_code == 200
        assert any(i["id"] == report_id for i in reports.json()["items"])

        detail = client.get(f"/api/v1/health-reports/{report_id}", headers=headers)
        assert detail.status_code == 200, detail.text
        report = detail.json()
        assert report["patient_name"] == "毕小雪"
        assert report["full_text"] == "瑞慈体检全文"
        assert report["findings"][0]["title"] == "体重过低 BMI 18.2"


def test_archive_visit_no_unique_per_user() -> None:
    phone = "13200132004"
    payload = {
        "diagnosis": "感冒",
        "medicine": "感冒灵",
        "visit_date": "2026-07-27",
        "visit_no": "MZ202607270018",
    }
    with _client() as client:
        headers = _auth_headers(client, phone)
        first = client.post("/api/v1/archives", headers=headers, json=payload)
        assert first.status_code == 201, first.text
        dup = client.post("/api/v1/archives", headers=headers, json=payload)
        assert dup.status_code == 409
        assert dup.json()["code"] == "visit_no_conflict"

        client.delete(f"/api/v1/archives/{first.json()['id']}", headers=headers)
        reused = client.post("/api/v1/archives", headers=headers, json=payload)
        assert reused.status_code == 201, reused.text


def test_archive_share() -> None:
    phone = "13200132002"
    with _client() as client:
        headers = _auth_headers(client, phone)
        created = client.post(
            "/api/v1/archives",
            headers=headers,
            json={
                "diagnosis": "感冒",
                "medicine": "感冒灵",
                "visit_date": "2026-07-27",
                "visit_no": "MZ202607270099",
            },
        )
        assert created.status_code == 201
        archive_id = created.json()["id"]

        async def seed_contact() -> str:
            async with AsyncSessionFactory() as session:
                user = (
                    await session.execute(select(User).where(User.phone == phone))
                ).scalar_one()
                contact = FamilyContact(
                    id=new_uuid(),
                    user_id=user.id,
                    name="女儿",
                    phone="13900000001",
                    relation="daughter",
                )
                session.add(contact)
                await session.commit()
                return contact.id

        contact_id = asyncio.run(seed_contact())

        shared = client.post(
            f"/api/v1/archives/{archive_id}/share",
            headers=headers,
            json={"contact_ids": [contact_id], "message": "看看这份病历"},
        )
        assert shared.status_code == 200, shared.text
        assert shared.json()["shared_count"] == 1


def test_health_summaries_and_reports() -> None:
    phone = "13200132003"
    with _client() as client:
        headers = _auth_headers(client, phone)

        async def seed() -> str:
            async with AsyncSessionFactory() as session:
                user = (
                    await session.execute(select(User).where(User.phone == phone))
                ).scalar_one()
                summary = HealthSummary(
                    id=new_uuid(),
                    user_id=user.id,
                    title="健康问题总结",
                    exam_date=date(2025, 11, 3),
                    exam_no="312101033225",
                    summary_text="综合近期体检与就诊记录……",
                )
                summary.items.append(
                    HealthSummaryItem(
                        id=new_uuid(),
                        content="体重指数偏低（BMI 18.2），需加强营养与适量运动",
                        severity="medium",
                        sort_order=0,
                    )
                )
                summary.items.append(
                    HealthSummaryItem(
                        id=new_uuid(),
                        content="血压偏高，建议低盐饮食",
                        severity="high",
                        sort_order=1,
                    )
                )
                report = HealthReport(
                    id=new_uuid(),
                    user_id=user.id,
                    patient_name="毕小雪",
                    exam_date=date(2025, 11, 3),
                    org_name="瑞慈体检上海静安机构",
                    voucher_no="312101033225",
                    report_type="体检报告",
                    raw_payload={"full_text": "完整报告正文……"},
                )
                report.findings.append(
                    HealthReportFinding(
                        id=new_uuid(),
                        title="【1】体重过低。体重指数 BMI 值偏低（18.2）。",
                        suggestion="建议平衡膳食，适量运动，定期复查体重。",
                        risk_level="medium",
                        sort_order=0,
                    )
                )
                glossary = ReportGlossary(
                    id=new_uuid(),
                    term="随诊",
                    definition="如有不适，及时就诊。",
                    sort_order=0,
                    enabled=True,
                )
                session.add_all([summary, report, glossary])
                await session.commit()
                return report.id

        report_id = asyncio.run(seed())

        summaries = client.get("/api/v1/health-summaries", headers=headers)
        assert summaries.status_code == 200, summaries.text
        items = summaries.json()["items"]
        assert len(items) == 1
        assert items[0]["title"] == "健康问题总结"
        assert items[0]["exam_date"] == "2025-11-03"
        assert items[0]["exam_no"] == "312101033225"
        assert len(items[0]["items"]) == 2
        assert items[0]["items"][0]["severity"] == "medium"
        assert items[0]["created_at"].endswith("Z")
        assert items[0]["updated_at"].endswith("Z")

        reports = client.get("/api/v1/health-reports?page=1&page_size=100", headers=headers)
        assert reports.status_code == 200
        listed = reports.json()
        assert listed["total"] == 1
        assert listed["page"] == 1
        assert listed["page_size"] == 100
        card = listed["items"][0]
        assert card["voucher_no"] == "312101033225"
        assert card["exam_date"] == "2025-11-03"
        assert "findings" not in card
        assert "full_text" not in card
        assert "glossary" not in card

        detail = client.get(f"/api/v1/health-reports/{report_id}", headers=headers)
        assert detail.status_code == 200, detail.text
        body = detail.json()
        assert body["full_text"] == "完整报告正文……"
        assert len(body["findings"]) == 1
        assert body["findings"][0]["risk_level"] == "medium"
        assert any(g["term"] == "随诊" for g in body["glossary"])

        glossaries = client.get("/api/v1/report-glossaries", headers=headers)
        assert glossaries.status_code == 200
        assert any(g["term"] == "随诊" for g in glossaries.json()["items"])


def test_display_page_empty_lists() -> None:
    phone = "13200132005"
    with _client() as client:
        headers = _auth_headers(client, phone)
        summaries = client.get("/api/v1/health-summaries", headers=headers)
        assert summaries.status_code == 200
        assert summaries.json() == {"items": []}

        reports = client.get("/api/v1/health-reports", headers=headers)
        assert reports.status_code == 200
        body = reports.json()
        assert body["items"] == []
        assert body["total"] == 0

        archives = client.get("/api/v1/archives", headers=headers)
        assert archives.status_code == 200
        body = archives.json()
        assert body["items"] == []
        assert body["total"] == 0


def test_cannot_read_other_users_archive_or_report() -> None:
    owner_phone = "13200132006"
    other_phone = "13200132007"
    with _client() as client:
        owner = _auth_headers(client, owner_phone)
        created = client.post(
            "/api/v1/archives",
            headers=owner,
            json={
                "diagnosis": "支气管炎",
                "medicine": "止咳药",
                "visit_date": "2026-07-27",
                "visit_no": "MZ202607270077",
            },
        )
        assert created.status_code == 201
        archive_id = created.json()["id"]

        async def seed_report() -> str:
            async with AsyncSessionFactory() as session:
                user = (
                    await session.execute(select(User).where(User.phone == owner_phone))
                ).scalar_one()
                report = HealthReport(
                    id=new_uuid(),
                    user_id=user.id,
                    patient_name="毕小雪",
                    exam_date=date(2025, 11, 3),
                    org_name="瑞慈体检上海静安机构",
                    voucher_no="OWN-ONLY",
                    report_type="体检报告",
                )
                session.add(report)
                await session.commit()
                return report.id

        report_id = asyncio.run(seed_report())
        other = _auth_headers(client, other_phone)

        hidden_archive = client.get(f"/api/v1/archives/{archive_id}", headers=other)
        assert hidden_archive.status_code == 404
        hidden_report = client.get(f"/api/v1/health-reports/{report_id}", headers=other)
        assert hidden_report.status_code == 404
        assert client.get("/api/v1/archives", headers=other).json()["items"] == []
        assert client.get("/api/v1/health-reports", headers=other).json()["items"] == []


def test_archives_require_auth() -> None:
    with _client() as client:
        resp = client.get("/api/v1/archives")
        assert resp.status_code == 401
        assert client.get("/api/v1/health-summaries").status_code == 401
        assert client.get("/api/v1/health-reports").status_code == 401
