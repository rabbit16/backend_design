"""任意 OpenAI 兼容服务（OpenAI / DeepSeek / vLLM / Ollama openai 接口等）。"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.core.logging import get_logger
from app.schemas.openai_chat import (
    ChatCompletionChunk,
    ChatCompletionRequest,
    ChatCompletionResponse,
)

logger = get_logger(__name__)


class OpenAICompatibleGateway:
    provider = "openai"

    def __init__(
        self,
        *,
        api_base: str | None = None,
        api_key: str | None = None,
        default_model: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        settings = get_settings()
        self.api_base = (api_base or settings.openai_api_base).rstrip("/")
        self.api_key = api_key if api_key is not None else settings.openai_api_key
        self.default_model = default_model or settings.openai_model
        self.timeout_seconds = timeout_seconds or settings.ai_gateway_timeout_seconds
        self._client = httpx.AsyncClient(
            base_url=self.api_base,
            timeout=self.timeout_seconds,
            headers=self._headers(),
        )

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _resolve_model(self, request: ChatCompletionRequest) -> str:
        # /chat 脚手架里 model 曾兼作 provider 名；真正上游模型名取自配置
        aliases = {"openai", "openai-compatible", "openai_compatible", ""}
        if not request.model or request.model in aliases:
            return self.default_model
        return request.model

    def _payload(self, request: ChatCompletionRequest, *, stream: bool) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self._resolve_model(request),
            "messages": [m.model_dump(exclude_none=True) for m in request.messages],
            "stream": stream,
        }
        if request.temperature is not None:
            body["temperature"] = request.temperature
        if request.top_p is not None:
            body["top_p"] = request.top_p
        if request.max_tokens is not None:
            body["max_tokens"] = request.max_tokens
        if request.presence_penalty is not None:
            body["presence_penalty"] = request.presence_penalty
        if request.frequency_penalty is not None:
            body["frequency_penalty"] = request.frequency_penalty
        if request.user is not None:
            body["user"] = request.user
        if request.extra:
            body.update(request.extra)
        return body

    async def chat_completions(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        payload = self._payload(request, stream=False)
        try:
            resp = await self._client.post("/chat/completions", json=payload)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:500]
            logger.error("openai_chat_http_error", status=exc.response.status_code, detail=detail)
            raise AppError(
                "上游模型调用失败",
                code="openai_upstream_error",
                status_code=502,
                details={"status": exc.response.status_code, "body": detail},
            ) from exc
        except httpx.HTTPError as exc:
            logger.error("openai_chat_network_error", error=str(exc))
            raise AppError(
                "上游模型网络错误",
                code="openai_network_error",
                status_code=502,
            ) from exc

        data = resp.json()
        parsed = ChatCompletionResponse.model_validate(data)
        parsed.provider = self.provider
        return parsed

    async def chat_completions_stream(
        self, request: ChatCompletionRequest
    ) -> AsyncIterator[ChatCompletionChunk]:
        payload = self._payload(request, stream=True)
        try:
            async with self._client.stream("POST", "/chat/completions", json=payload) as resp:
                if resp.status_code >= 400:
                    body = (await resp.aread()).decode("utf-8", errors="replace")[:500]
                    raise AppError(
                        "上游模型调用失败",
                        code="openai_upstream_error",
                        status_code=502,
                        details={"status": resp.status_code, "body": body},
                    )
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    if line.startswith(":"):
                        # SSE comment / keep-alive
                        continue
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = ChatCompletionChunk.model_validate(json.loads(data))
                    except Exception:  # noqa: BLE001
                        logger.warning("openai_stream_parse_skip", data=data[:200])
                        continue
                    chunk.provider = self.provider
                    yield chunk
        except AppError:
            raise
        except httpx.HTTPError as exc:
            logger.error("openai_stream_network_error", error=str(exc))
            raise AppError(
                "上游模型网络错误",
                code="openai_network_error",
                status_code=502,
            ) from exc

    async def close(self) -> None:
        await self._client.aclose()
