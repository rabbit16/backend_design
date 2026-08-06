from fastapi import APIRouter

from app.core.config import get_settings
from app.schemas.common import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        app=settings.app_name,
        env=settings.app_env,
        ai_provider=settings.ai_gateway_provider,
        openai_model=settings.openai_model,
        openai_configured=bool(settings.openai_api_key.strip()),
    )
