from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.health_profile import (
    GlossaryListResponse,
    HealthReportDetail,
    HealthReportListResponse,
    HealthSummaryListResponse,
)
from app.security.jwt import get_current_subject
from app.services.health_profile_service import HealthProfileService

router = APIRouter()


def _service(session: Annotated[AsyncSession, Depends(get_session)]) -> HealthProfileService:
    return HealthProfileService(session)


@router.get("/health-summaries", response_model=HealthSummaryListResponse, tags=["health-summaries"])
async def list_health_summaries(
    service: Annotated[HealthProfileService, Depends(_service)],
    user_id: Annotated[str, Depends(get_current_subject)],
) -> HealthSummaryListResponse:
    return await service.list_summaries(user_id)


@router.get("/health-reports", response_model=HealthReportListResponse, tags=["health-reports"])
async def list_health_reports(
    service: Annotated[HealthProfileService, Depends(_service)],
    user_id: Annotated[str, Depends(get_current_subject)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> HealthReportListResponse:
    return await service.list_reports(user_id, page=page, page_size=page_size)


@router.get("/health-reports/{report_id}", response_model=HealthReportDetail, tags=["health-reports"])
async def get_health_report(
    report_id: str,
    service: Annotated[HealthProfileService, Depends(_service)],
    user_id: Annotated[str, Depends(get_current_subject)],
) -> HealthReportDetail:
    return await service.get_report(user_id, report_id)


@router.get("/report-glossaries", response_model=GlossaryListResponse, tags=["health-reports"])
async def list_report_glossaries(
    service: Annotated[HealthProfileService, Depends(_service)],
    _: Annotated[str, Depends(get_current_subject)],
) -> GlossaryListResponse:
    return await service.list_glossaries()
