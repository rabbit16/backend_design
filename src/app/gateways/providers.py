from app.gateways.ai_gateway import EchoAIGateway
from app.gateways.base import AIGateway


class ReverseEchoAIGateway(EchoAIGateway):
    provider = "reverse-echo"

    async def complete(self, request):  # noqa: ANN001
        response = await super().complete(request)
        response.message = f"reverse-echo: {request.message[::-1]}"
        response.provider = self.provider
        return response

    async def stream(self, request):  # noqa: ANN001
        for token in ["reverse-echo", ": ", request.message[::-1]]:
            yield token


def create_provider(provider: str) -> AIGateway:
    providers: dict[str, type[AIGateway]] = {
        "echo": EchoAIGateway,
        "reverse-echo": ReverseEchoAIGateway,
    }
    gateway_cls = providers.get(provider)
    if gateway_cls is None:
        raise ValueError(f"Unsupported AI gateway provider: {provider}")
    return gateway_cls()


def list_providers() -> list[str]:
    return ["echo", "reverse-echo"]
