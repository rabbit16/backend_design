from src.app.core.config import get_settings
from src.app.core.exceptions import AppError
from src.app.core.logging import get_logger
from src.app.gateways.ai_gateway import EchoAIGateway, ReverseEchoAIGateway
from src.app.gateways.base import AIGateway
from src.app.gateways.openai_compatible import OpenAICompatibleGateway

logger = get_logger(__name__)


def create_provider(provider: str | None = None) -> AIGateway:
    settings = get_settings()
    name = (provider or settings.ai_gateway_provider).strip().lower()

    if name in {"echo"}:
        logger.info("ai_gateway_created", provider="echo")
        return EchoAIGateway()
    if name in {"reverse-echo", "reverse_echo"}:
        logger.info("ai_gateway_created", provider="reverse-echo")
        return ReverseEchoAIGateway()
    if name in {"openai", "openai-compatible", "openai_compatible"}:
        gateway = OpenAICompatibleGateway()
        logger.info(
            "ai_gateway_created",
            provider="openai",
            api_base=gateway.api_base,
            model=gateway.default_model,
        )
        return gateway

    raise AppError(
        f"不支持的 AI 网关: {provider!r}，可选: {', '.join(list_providers())}",
        code="unsupported_ai_provider",
        status_code=500,
    )


def list_providers() -> list[str]:
    return ["echo", "reverse-echo", "openai"]
