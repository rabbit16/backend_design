from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.app.core.config import get_settings
from src.app.core.exceptions import AppError
from src.app.db.models.archive import ArchiveExport, ArchiveOcrJob, ArchiveShare, MedicalArchive
from src.app.db.models.family import FamilyContact
from src.app.db.models.media import MediaFile
from src.app.gateways.base import AIGateway
from src.app.gateways.registry import create_gateway
from src.app.ocr.extractor import VisionOcrExtractor
from src.app.ocr.image import sniff_image_mime, validate_image_bytes
from src.app.ocr.parser import ExtractedDocument
from src.app.schemas.archive import (
    ArchiveListResponse,
    ArchiveRecord,
    CreateArchiveRequest,
    ExportPdfResponse,
    OcrResult,
    ShareArchiveResponse,
    UpdateArchiveRequest,
)
from src.app.services.health_profile_service import HealthProfileService
from src.app.utils.ids import new_uuid
from src.app.utils.timefmt import fmt_utc

EXPORT_TTL_SECONDS = 600


class ArchiveService:
    def __init__(
        self,
        session: AsyncSession,
        gateway: AIGateway | None = None,
        ocr_extractor: VisionOcrExtractor | None = None,
        *,
        owns_gateway: bool = False,
    ) -> None:
        self.session = session
        self.gateway = gateway
        self._ocr_extractor = ocr_extractor
        self.owns_gateway = owns_gateway

    def _to_record(self, row: MedicalArchive) -> ArchiveRecord:
        image_url = None
        if row.image_media is not None:
            image_url = row.image_media.url
        return ArchiveRecord(
            id=row.id,
            diagnosis=row.diagnosis,
            medicine=row.medicine,
            visit_date=row.visit_date,
            visit_no=row.visit_no,
            raw_ocr_text=row.raw_ocr_text,
            image_url=image_url,
            created_at=fmt_utc(row.created_at),
            updated_at=fmt_utc(row.updated_at),
        )

    async def _ensure_unique_visit_no(
        self,
        user_id: str,
        visit_no: str,
        *,
        exclude_id: str | None = None,
    ) -> str:
        normalized = visit_no.strip()
        if not normalized:
            raise AppError("就诊号不能为空", code="invalid_visit_no", status_code=422)
        stmt = select(MedicalArchive.id).where(
            MedicalArchive.user_id == user_id,
            MedicalArchive.visit_no == normalized,
            MedicalArchive.deleted_at.is_(None),
        )
        if exclude_id:
            stmt = stmt.where(MedicalArchive.id != exclude_id)
        existing = (await self.session.execute(stmt.limit(1))).scalar_one_or_none()
        if existing is not None:
            raise AppError("该就诊号已存在", code="visit_no_conflict", status_code=409)
        return normalized

    async def _get_owned(self, user_id: str, archive_id: str) -> MedicalArchive:
        result = await self.session.execute(
            select(MedicalArchive)
            .where(
                MedicalArchive.id == archive_id,
                MedicalArchive.user_id == user_id,
                MedicalArchive.deleted_at.is_(None),
            )
            .options(selectinload(MedicalArchive.image_media))
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise AppError("档案不存在", code="archive_not_found", status_code=404)
        return row

    async def _ensure_image_media(
        self,
        user_id: str,
        *,
        image_url: str | None = None,
        mime_type: str = "image/jpeg",
        storage_key: str | None = None,
        size_bytes: int | None = None,
    ) -> MediaFile | None:
        if not image_url and not storage_key:
            return None
        media = MediaFile(
            id=new_uuid(),
            user_id=user_id,
            kind="image",
            mime_type=mime_type,
            storage_key=storage_key or image_url or f"archives/{user_id}/{new_uuid()}",
            url=image_url,
            size_bytes=size_bytes,
        )
        self.session.add(media)
        await self.session.flush()
        return media

    async def ocr(
        self,
        user_id: str,
        *,
        file_bytes: bytes,
        filename: str | None,
        content_type: str | None,
        source: str,
    ) -> OcrResult:
        if source not in {"camera", "album"}:
            raise AppError("source 必须是 camera 或 album", code="invalid_source", status_code=422)

        settings = get_settings()
        validate_image_bytes(file_bytes, max_bytes=settings.ocr_max_image_bytes)
        mime = sniff_image_mime(file_bytes, filename=filename, content_type=content_type)

        ext = "jpg"
        if filename and "." in filename:
            ext = filename.rsplit(".", 1)[-1].lower()[:8] or "jpg"
        storage_key = f"ocr/{user_id}/{new_uuid()}.{ext}"
        media = await self._ensure_image_media(
            user_id,
            mime_type=mime,
            storage_key=storage_key,
            size_bytes=len(file_bytes),
        )

        job = ArchiveOcrJob(
            id=new_uuid(),
            user_id=user_id,
            image_media_id=media.id if media else None,
            source=source,
            status="pending",
        )
        self.session.add(job)
        await self.session.flush()

        gateway = self.gateway
        owns = self.owns_gateway
        if self._ocr_extractor is not None:
            extractor = self._ocr_extractor
        else:
            if gateway is None:
                gateway = create_gateway()
                owns = True
            extractor = VisionOcrExtractor(gateway)

        try:
            extracted = await extractor.extract(
                file_bytes,
                source=source,
                filename=filename,
                content_type=content_type,
                user_id=user_id,
            )
        except Exception:
            job.status = "failed"
            await self.session.commit()
            raise
        else:
            job.diagnosis = extracted.diagnosis
            job.medicine = extracted.medicine
            job.visit_date = extracted.visit_date
            job.visit_no = extracted.visit_no
            job.raw_ocr_text = extracted.raw_ocr_text
            job.status = "succeeded"
            try:
                result = await self._persist_extracted(
                    user_id,
                    extracted,
                    source=source,
                    image_media_id=media.id if media else None,
                )
            except Exception:
                await self.session.commit()
                raise
            await self.session.commit()
            return result
        finally:
            if owns and gateway is not None:
                await gateway.close()

    async def _persist_extracted(
        self,
        user_id: str,
        extracted: ExtractedDocument,
        *,
        source: str,
        image_media_id: str | None,
    ) -> OcrResult:
        if extracted.document_type == "exam":
            report = await HealthProfileService(self.session).create_report(
                user_id,
                patient_name=extracted.patient_name,
                exam_date=extracted.exam_date or extracted.visit_date,
                org_name=extracted.org_name,
                voucher_no=extracted.voucher_no or extracted.visit_no,
                report_type=extracted.report_type,
                full_text=extracted.raw_ocr_text,
                findings=extracted.findings,
                extra_payload={"source": source, "image_media_id": image_media_id},
            )
            return extracted.to_ocr_result(report.id)

        visit_no = await self._ensure_unique_visit_no(user_id, extracted.visit_no)
        row = MedicalArchive(
            id=new_uuid(),
            user_id=user_id,
            diagnosis=extracted.diagnosis,
            medicine=extracted.medicine,
            visit_date=extracted.visit_date,
            visit_no=visit_no,
            raw_ocr_text=extracted.raw_ocr_text,
            image_media_id=image_media_id,
            source=source,
        )
        self.session.add(row)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            raise AppError("该就诊号已存在", code="visit_no_conflict", status_code=409) from exc
        return extracted.to_ocr_result(row.id)

    async def list_archives(
        self,
        user_id: str,
        *,
        q: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> ArchiveListResponse:
        page = max(page, 1)
        page_size = min(max(page_size, 1), 100)

        filters = [
            MedicalArchive.user_id == user_id,
            MedicalArchive.deleted_at.is_(None),
        ]
        if q and q.strip():
            like = f"%{q.strip()}%"
            filters.append(
                or_(
                    MedicalArchive.diagnosis.ilike(like),
                    MedicalArchive.medicine.ilike(like),
                    MedicalArchive.visit_no.ilike(like),
                    MedicalArchive.raw_ocr_text.ilike(like),
                )
            )

        total = (
            await self.session.execute(select(func.count()).select_from(MedicalArchive).where(*filters))
        ).scalar_one()

        result = await self.session.execute(
            select(MedicalArchive)
            .where(*filters)
            .options(selectinload(MedicalArchive.image_media))
            .order_by(MedicalArchive.visit_date.desc(), MedicalArchive.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = result.scalars().all()
        return ArchiveListResponse(
            items=[self._to_record(r) for r in rows],
            total=int(total),
            page=page,
            page_size=page_size,
        )

    async def create(self, user_id: str, payload: CreateArchiveRequest) -> ArchiveRecord:
        visit_no = await self._ensure_unique_visit_no(user_id, payload.visit_no)
        media = await self._ensure_image_media(user_id, image_url=payload.image_url)
        row = MedicalArchive(
            id=new_uuid(),
            user_id=user_id,
            diagnosis=payload.diagnosis.strip(),
            medicine=payload.medicine.strip(),
            visit_date=payload.visit_date,
            visit_no=visit_no,
            raw_ocr_text=payload.raw_ocr_text,
            image_media_id=media.id if media else None,
            source=payload.source,
        )
        self.session.add(row)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError("该就诊号已存在", code="visit_no_conflict", status_code=409) from exc
        row = await self._get_owned(user_id, row.id)
        return self._to_record(row)

    async def get(self, user_id: str, archive_id: str) -> ArchiveRecord:
        row = await self._get_owned(user_id, archive_id)
        return self._to_record(row)

    async def update(
        self, user_id: str, archive_id: str, payload: UpdateArchiveRequest
    ) -> ArchiveRecord:
        row = await self._get_owned(user_id, archive_id)
        if payload.diagnosis is not None:
            row.diagnosis = payload.diagnosis.strip()
        if payload.medicine is not None:
            row.medicine = payload.medicine.strip()
        if payload.visit_date is not None:
            row.visit_date = payload.visit_date
        if payload.visit_no is not None:
            row.visit_no = await self._ensure_unique_visit_no(
                user_id, payload.visit_no, exclude_id=archive_id
            )
        row.updated_at = datetime.now(UTC)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError("该就诊号已存在", code="visit_no_conflict", status_code=409) from exc
        row = await self._get_owned(user_id, archive_id)
        return self._to_record(row)

    async def delete(self, user_id: str, archive_id: str) -> None:
        row = await self._get_owned(user_id, archive_id)
        row.deleted_at = datetime.now(UTC)
        await self.session.commit()

    async def share(
        self,
        user_id: str,
        archive_id: str,
        contact_ids: list[str],
        message: str | None,
    ) -> ShareArchiveResponse:
        await self._get_owned(user_id, archive_id)
        unique_ids = list(dict.fromkeys(contact_ids))
        result = await self.session.execute(
            select(FamilyContact).where(
                FamilyContact.user_id == user_id,
                FamilyContact.deleted_at.is_(None),
                FamilyContact.id.in_(unique_ids),
            )
        )
        contacts = result.scalars().all()
        found = {c.id for c in contacts}
        missing = [cid for cid in unique_ids if cid not in found]
        if missing:
            raise AppError(
                "部分联系人不存在",
                code="contact_not_found",
                status_code=404,
                details={"missing": missing},
            )

        now = datetime.now(UTC)
        for contact in contacts:
            self.session.add(
                ArchiveShare(
                    id=new_uuid(),
                    archive_id=archive_id,
                    user_id=user_id,
                    contact_id=contact.id,
                    message=message,
                    status="queued",
                    sent_at=None,
                )
            )
        # 简化：落库即视为已入队；真实推送可异步改 status=sent
        await self.session.commit()
        _ = now
        return ShareArchiveResponse(ok=True, shared_count=len(contacts))

    async def export_pdf(self, user_id: str, archive_id: str) -> ExportPdfResponse:
        row = await self._get_owned(user_id, archive_id)
        expires_at = datetime.now(UTC) + timedelta(seconds=EXPORT_TTL_SECONDS)
        export_id = new_uuid()
        download_url = f"/api/v1/archives/{archive_id}/exports/{export_id}.pdf"
        export = ArchiveExport(
            id=export_id,
            archive_id=row.id,
            user_id=user_id,
            pdf_media_id=None,
            download_url=download_url,
            expires_at=expires_at,
            status="ready",
        )
        self.session.add(export)
        await self.session.commit()
        return ExportPdfResponse(download_url=download_url, expires_in=EXPORT_TTL_SECONDS)
