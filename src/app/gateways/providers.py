from app.core.config import get_settings
from app.gateways.ai_gateway import EchoAIGateway, ReverseEchoAIGateway
from app.gateways.base import AIGateway
from app.gateways.openai_compatible import OpenAICompatibleGateway


def create_provider(provider: str | None = None) -> AIGateway:
    settings = get_settings()
    name = (provider or settings.ai_gateway_provider).strip().lower()

    if name in {"echo"}:
        return EchoAIGateway()
    if name in {"reverse-echo", "reverse_echo"}:
        return ReverseEchoAIGateway()
    if name in {"openai", "openai-compatible", "openai_compatible"}:
        return OpenAICompatibleGateway()

    raise ValueError(
        f"Unsupported AI gateway provider: {provider!r}. "
        f"Use one of: {', '.join(list_providers())}"
    )


def list_providers() -> list[str]:
    return ["echo", "reverse-echo", "openai"]
