from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.archive import (
    ArchiveListResponse,
    ArchiveRecord,
    CreateArchiveRequest,
    ExportPdfResponse,
    OcrResult,
    OkResponse,
    ShareArchiveRequest,
    ShareArchiveResponse,
    UpdateArchiveRequest,
)
from app.security.jwt import get_current_subject
from app.services.archive_service import ArchiveService

router = APIRouter(prefix="/archives", tags=["archives"])


def _service(session: Annotated[AsyncSession, Depends(get_session)]) -> ArchiveService:
    return ArchiveService(session)


@router.post("/ocr", response_model=OcrResult)
async def archives_ocr(
    service: Annotated[ArchiveService, Depends(_service)],
    user_id: Annotated[str, Depends(get_current_subject)],
    file: Annotated[UploadFile, File(description="病历/就诊单图片")],
    source: Annotated[Literal["camera", "album"], Form()] = "camera",
) -> OcrResult:
    content = await file.read()
    return await service.ocr(
        user_id,
        file_bytes=content,
        filename=file.filename,
        content_type=file.content_type,
        source=source,
    )


@router.get("", response_model=ArchiveListResponse)
async def list_archives(
    service: Annotated[ArchiveService, Depends(_service)],
    user_id: Annotated[str, Depends(get_current_subject)],
    q: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ArchiveListResponse:
    return await service.list_archives(user_id, q=q, page=page, page_size=page_size)


@router.post("", response_model=ArchiveRecord, status_code=status.HTTP_201_CREATED)
async def create_archive(
    payload: CreateArchiveRequest,
    service: Annotated[ArchiveService, Depends(_service)],
    user_id: Annotated[str, Depends(get_current_subject)],
) -> ArchiveRecord:
    return await service.create(user_id, payload)


@router.get("/{archive_id}", response_model=ArchiveRecord)
async def get_archive(
    archive_id: str,
    service: Annotated[ArchiveService, Depends(_service)],
    user_id: Annotated[str, Depends(get_current_subject)],
) -> ArchiveRecord:
    return await service.get(user_id, archive_id)


@router.patch("/{archive_id}", response_model=ArchiveRecord)
async def update_archive(
    archive_id: str,
    payload: UpdateArchiveRequest,
    service: Annotated[ArchiveService, Depends(_service)],
    user_id: Annotated[str, Depends(get_current_subject)],
) -> ArchiveRecord:
    return await service.update(user_id, archive_id, payload)


@router.delete("/{archive_id}", response_model=OkResponse)
async def delete_archive(
    archive_id: str,
    service: Annotated[ArchiveService, Depends(_service)],
    user_id: Annotated[str, Depends(get_current_subject)],
) -> OkResponse:
    await service.delete(user_id, archive_id)
    return OkResponse(ok=True)


@router.post("/{archive_id}/share", response_model=ShareArchiveResponse)
async def share_archive(
    archive_id: str,
    payload: ShareArchiveRequest,
    service: Annotated[ArchiveService, Depends(_service)],
    user_id: Annotated[str, Depends(get_current_subject)],
) -> ShareArchiveResponse:
    return await service.share(
        user_id,
        archive_id,
        contact_ids=payload.contact_ids,
        message=payload.message,
    )


@router.get("/{archive_id}/export", response_model=ExportPdfResponse)
async def export_archive(
    archive_id: str,
    service: Annotated[ArchiveService, Depends(_service)],
    user_id: Annotated[str, Depends(get_current_subject)],
) -> ExportPdfResponse:
    return await service.export_pdf(user_id, archive_id)
