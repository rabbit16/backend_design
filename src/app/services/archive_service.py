from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AppError
from app.db.models.archive import ArchiveExport, ArchiveOcrJob, ArchiveShare, MedicalArchive
from app.db.models.family import FamilyContact
from app.db.models.media import MediaFile
from app.schemas.archive import (
    ArchiveListResponse,
    ArchiveRecord,
    CreateArchiveRequest,
    ExportPdfResponse,
    OcrResult,
    ShareArchiveResponse,
    UpdateArchiveRequest,
)
from app.utils.ids import new_uuid
from app.utils.timefmt import fmt_utc

EXPORT_TTL_SECONDS = 600


class ArchiveService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

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
        if not file_bytes:
            raise AppError("图片不能为空", code="empty_file", status_code=400)

        ext = "jpg"
        if filename and "." in filename:
            ext = filename.rsplit(".", 1)[-1].lower()[:8] or "jpg"
        mime = content_type or "image/jpeg"
        storage_key = f"ocr/{user_id}/{new_uuid()}.{ext}"
        media = await self._ensure_image_media(
            user_id,
            mime_type=mime,
            storage_key=storage_key,
            size_bytes=len(file_bytes),
        )

        # 暂无真实 OCR：落中间态 job，返回可编辑的占位结果（便于联调）
        today = date.today()
        diagnosis = "支气管炎倾向，建议复查"
        medicine = "按医嘱服用止咳药，注意饮水"
        visit_no = f"MZ{today.strftime('%Y%m%d')}{new_uuid().replace('-', '')[:6].upper()}"
        raw_text = (
            f"[stub-ocr] file={filename or 'upload'} bytes={len(file_bytes)}\n"
            f"诊断：{diagnosis}\n用药：{medicine}\n就诊日：{today.isoformat()}\n就诊号：{visit_no}"
        )
        job = ArchiveOcrJob(
            id=new_uuid(),
            user_id=user_id,
            image_media_id=media.id if media else None,
            source=source,
            diagnosis=diagnosis,
            medicine=medicine,
            visit_date=today,
            visit_no=visit_no,
            raw_ocr_text=raw_text,
            status="succeeded",
        )
        self.session.add(job)
        await self.session.commit()
        return OcrResult(
            diagnosis=diagnosis,
            medicine=medicine,
            visit_date=today,
            visit_no=visit_no,
            raw_ocr_text=raw_text,
        )

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
