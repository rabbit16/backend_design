from fastapi import FastAPI, Request

from app.core.config import get_settings
from app.core.logging import get_logger
from app.gateways.base import AIGateway
from app.gateways.providers import create_provider

_GATEWAY_STATE_KEY = "ai_gateway"
logger = get_logger(__name__)


def create_gateway(provider: str | None = None) -> AIGateway:
    settings = get_settings()
    return create_provider(provider or settings.ai_gateway_provider)


def init_gateway_registry(app: FastAPI) -> None:
    gateway = create_gateway()
    app.state.ai_gateway = gateway
    logger.info(
        "ai_gateway_registry_ready",
        provider=getattr(gateway, "provider", "unknown"),
    )


def get_gateway(request: Request) -> AIGateway:
    gateway = getattr(request.app.state, _GATEWAY_STATE_KEY, None)
    if gateway is None:
        gateway = create_gateway()
        request.app.state.ai_gateway = gateway
    return gateway


def get_app_gateway(app: FastAPI) -> AIGateway:
    gateway = getattr(app.state, _GATEWAY_STATE_KEY, None)
    if gateway is None:
        gateway = create_gateway()
        app.state.ai_gateway = gateway
    return gateway


async def close_gateway_registry(app: FastAPI) -> None:
    gateway: AIGateway | None = getattr(app.state, _GATEWAY_STATE_KEY, None)
    if gateway is not None:
        await gateway.close()
        setattr(app.state, _GATEWAY_STATE_KEY, None)
