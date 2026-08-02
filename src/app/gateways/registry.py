from fastapi import FastAPI, Request

from app.core.config import get_settings
from app.gateways.base import AIGateway
from app.gateways.providers import create_provider

_GATEWAY_STATE_KEY = "ai_gateway"


def create_gateway(provider: str | None = None) -> AIGateway:
    settings = get_settings()
    return create_provider(provider or settings.ai_gateway_provider)


def init_gateway_registry(app: FastAPI) -> None:
    app.state.ai_gateway = create_gateway()


def get_gateway(request: Request) -> AIGateway:
    return getattr(request.app.state, _GATEWAY_STATE_KEY)


async def close_gateway_registry(app: FastAPI) -> None:
    gateway: AIGateway | None = getattr(app.state, _GATEWAY_STATE_KEY, None)
    if gateway is not None:
        await gateway.close()
