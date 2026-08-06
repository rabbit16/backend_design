"""基于官方 OpenAI Python SDK 的 Chat Completions 网关。"""

from __future__ import annotations

import os
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx
from openai import APIError, APIStatusError, AsyncOpenAI, AsyncStream
from openai.types.chat import ChatCompletion, ChatCompletionChunk as SdkChatCompletionChunk

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.core.logging import get_logger
from app.schemas.openai_chat import (
    ChatCompletionChoice,
    ChatCompletionChunk,
    ChatCompletionChunkChoice,
    ChatCompletionChunkDelta,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionUsage,
    ChatMessage,
)
from app.utils.ids import new_request_id

logger = get_logger(__name__)

_PROVIDER_MODEL_ALIASES = frozenset(
    {"openai", "openai-compatible", "openai_compatible", "echo", "reverse-echo", "reverse_echo", ""}
)


def _pick_http_proxy(explicit: str | None, settings_proxy: str) -> str | None:
    """优先显式配置 / OPENAI_HTTP_PROXY，其次 HTTPS_PROXY/HTTP_PROXY。

    故意不使用 ALL_PROXY=socks://…：httpx 对 socks 支持不稳，容易导致请求卡住，
    前端表现为 /qa/ask 只收到 meta、一直没有 token/done。
    """
    if explicit is not None:
        value = explicit.strip()
        return value or None
    if settings_proxy.strip():
        return settings_proxy.strip()
    for key in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        value = (os.environ.get(key) or "").strip()
        if value:
            return value
    return None


class OpenAICompatibleGateway:
    """使用 openai.AsyncOpenAI 调用任意兼容 /chat/completions 的上游。"""

    provider = "openai"

    def __init__(
        self,
        *,
        api_base: str | None = None,
        api_key: str | None = None,
        default_model: str | None = None,
        timeout_seconds: float | None = None,
        require_api_key: bool = True,
        trust_env: bool | None = None,
        http_proxy: str | None = None,
    ) -> None:
        settings = get_settings()
        self.api_base = (api_base or settings.openai_api_base).rstrip("/")
        self.api_key = (api_key if api_key is not None else settings.openai_api_key).strip()
        self.default_model = default_model or settings.openai_model
        self.timeout_seconds = timeout_seconds or settings.ai_gateway_timeout_seconds
        self._key_required = require_api_key and not (
            "localhost" in self.api_base or "127.0.0.1" in self.api_base
        )

        if self._key_required and not self.api_key:
            logger.warning(
                "openai_api_key_missing",
                api_base=self.api_base,
                hint="Set OPENAI_API_KEY in .env before calling the model",
            )

        proxy = _pick_http_proxy(http_proxy, settings.openai_http_proxy)
        # 已手动选定代理时关闭 trust_env，避免 ALL_PROXY=socks 覆盖/干扰
        use_env = False if proxy else (True if trust_env is None else trust_env)
        timeout = httpx.Timeout(
            connect=15.0,
            read=self.timeout_seconds,
            write=30.0,
            pool=15.0,
        )
        try:
            self._http = httpx.AsyncClient(timeout=timeout, trust_env=use_env, proxy=proxy)
        except ValueError as exc:
            logger.warning("openai_proxy_fallback", error=str(exc), proxy=None)
            # socks 等非法 scheme：再试一次 HTTP(S)_PROXY
            fallback = None
            for key in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
                candidate = (os.environ.get(key) or "").strip()
                if candidate and not candidate.lower().startswith("socks"):
                    fallback = candidate
                    break
            self._http = httpx.AsyncClient(timeout=timeout, trust_env=False, proxy=fallback)
            proxy = fallback

        self._client = AsyncOpenAI(
            api_key=self.api_key or "EMPTY",
            base_url=self.api_base,
            http_client=self._http,
            max_retries=1,
        )
        logger.info(
            "openai_gateway_ready",
            api_base=self.api_base,
            model=self.default_model,
            has_api_key=bool(self.api_key),
            proxy=proxy or "",
            sdk="openai",
        )

    def _ensure_ready(self) -> None:
        if self._key_required and not self.api_key:
            raise AppError(
                "未配置 OPENAI_API_KEY，无法调用上游大模型。"
                "请在 .env 设置 OPENAI_API_KEY，并确认 AI_GATEWAY_PROVIDER=openai。",
                code="openai_api_key_missing",
                status_code=500,
            )

    def _resolve_model(self, request: ChatCompletionRequest) -> str:
        if not request.model or request.model in _PROVIDER_MODEL_ALIASES:
            return self.default_model
        return request.model

    def _sdk_kwargs(self, request: ChatCompletionRequest, *, stream: bool) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self._resolve_model(request),
            "messages": [m.to_openai_param() for m in request.messages],
            "stream": stream,
        }
        if request.temperature is not None:
            kwargs["temperature"] = request.temperature
        if request.top_p is not None:
            kwargs["top_p"] = request.top_p
        if request.max_tokens is not None:
            kwargs["max_tokens"] = request.max_tokens
        if request.presence_penalty is not None:
            kwargs["presence_penalty"] = request.presence_penalty
        if request.frequency_penalty is not None:
            kwargs["frequency_penalty"] = request.frequency_penalty
        if request.user is not None:
            kwargs["user"] = request.user
        if request.modalities is not None:
            kwargs["modalities"] = request.modalities
        if request.audio is not None:
            kwargs["audio"] = request.audio
        if request.extra:
            kwargs.update(request.extra)
        return kwargs

    def _map_api_error(self, exc: Exception) -> AppError:
        if isinstance(exc, APIStatusError):
            body = ""
            try:
                body = str(exc.response.json())[:500]
            except Exception:  # noqa: BLE001
                body = (exc.message or str(exc))[:500]
            logger.error("openai_chat_http_error", status=exc.status_code, detail=body)
            return AppError(
                "上游模型调用失败",
                code="openai_upstream_error",
                status_code=502,
                details={"status": exc.status_code, "body": body},
            )
        if isinstance(exc, APIError):
            logger.error("openai_chat_api_error", error=str(exc))
            return AppError(
                "上游模型网络错误",
                code="openai_network_error",
                status_code=502,
            )
        logger.error("openai_chat_unknown_error", error=str(exc))
        return AppError(
            "上游模型调用失败",
            code="openai_upstream_error",
            status_code=502,
        )

    @staticmethod
    def _from_sdk_completion(data: ChatCompletion, *, provider: str) -> ChatCompletionResponse:
        choices: list[ChatCompletionChoice] = []
        for choice in data.choices:
            msg = choice.message
            content = msg.content or ""
            choices.append(
                ChatCompletionChoice(
                    index=choice.index,
                    message=ChatMessage(role=msg.role or "assistant", content=content),
                    finish_reason=choice.finish_reason,
                )
            )
        usage = None
        if data.usage is not None:
            usage = ChatCompletionUsage(
                prompt_tokens=data.usage.prompt_tokens or 0,
                completion_tokens=data.usage.completion_tokens or 0,
                total_tokens=data.usage.total_tokens or 0,
            )
        return ChatCompletionResponse(
            id=data.id,
            object=getattr(data, "object", None) or "chat.completion",
            created=data.created or int(time.time()),
            model=data.model or "",
            choices=choices,
            usage=usage,
            provider=provider,
        )

    @staticmethod
    def _from_sdk_chunk(data: SdkChatCompletionChunk, *, provider: str) -> ChatCompletionChunk:
        choices: list[ChatCompletionChunkChoice] = []
        for choice in data.choices:
            delta = choice.delta
            content = delta.content if delta is not None else None
            role = delta.role if delta is not None else None
            choices.append(
                ChatCompletionChunkChoice(
                    index=choice.index,
                    delta=ChatCompletionChunkDelta(role=role, content=content),
                    finish_reason=choice.finish_reason,
                )
            )
        return ChatCompletionChunk(
            id=data.id or f"chatcmpl-{new_request_id()}",
            object=getattr(data, "object", None) or "chat.completion.chunk",
            created=data.created or int(time.time()),
            model=data.model or "",
            choices=choices,
            provider=provider,
        )

    async def chat_completions(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        self._ensure_ready()
        kwargs = self._sdk_kwargs(request, stream=False)
        logger.info(
            "openai_chat_request",
            model=kwargs["model"],
            stream=False,
            message_count=len(kwargs["messages"]),
            modalities=kwargs.get("modalities"),
        )
        try:
            data = await self._client.chat.completions.create(**kwargs)
        except Exception as exc:  # noqa: BLE001
            raise self._map_api_error(exc) from exc

        parsed = self._from_sdk_completion(data, provider=self.provider)
        logger.info(
            "openai_chat_response",
            model=parsed.model,
            id=parsed.id,
            content_len=len(parsed.content),
        )
        return parsed

    async def chat_completions_stream(
        self, request: ChatCompletionRequest
    ) -> AsyncIterator[ChatCompletionChunk]:
        self._ensure_ready()
        kwargs = self._sdk_kwargs(request, stream=True)
        logger.info(
            "openai_chat_request",
            model=kwargs["model"],
            stream=True,
            message_count=len(kwargs["messages"]),
            modalities=kwargs.get("modalities"),
        )
        try:
            stream: AsyncStream[SdkChatCompletionChunk] = await self._client.chat.completions.create(
                **kwargs
            )
            async for event in stream:
                yield self._from_sdk_chunk(event, provider=self.provider)
        except AppError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise self._map_api_error(exc) from exc

    async def close(self) -> None:
        await self._client.close()
        await self._http.aclose()
