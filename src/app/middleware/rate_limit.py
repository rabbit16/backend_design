import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from src.app.cache.redis import get_redis
from src.app.core.config import Settings


@dataclass(frozen=True)
class RateLimitConfig:
    requests: int
    window_seconds: int


class InMemoryRateLimiter:
    def __init__(self, config: RateLimitConfig) -> None:
        self.config = config
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    async def allow(self, key: str) -> tuple[bool, int]:
        now = time.monotonic()
        hits = self._hits[key]
        window_start = now - self.config.window_seconds
        while hits and hits[0] < window_start:
            hits.popleft()
        if len(hits) >= self.config.requests:
            return False, self.config.window_seconds
        hits.append(now)
        return True, max(0, self.config.requests - len(hits))


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, settings: Settings) -> None:  # noqa: ANN001
        super().__init__(app)
        self.settings = settings
        self.memory_limiter = InMemoryRateLimiter(
            RateLimitConfig(
                requests=settings.rate_limit_requests,
                window_seconds=settings.rate_limit_window_seconds,
            )
        )

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if not self.settings.rate_limit_enabled or request.url.path.endswith("/health"):
            return await call_next(request)

        key = request.headers.get("x-api-key") or request.client.host if request.client else "unknown"
        allowed, remaining = await self._allow(key)
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"code": "rate_limited", "message": "Too many requests"},
                headers={"retry-after": str(self.settings.rate_limit_window_seconds)},
            )

        response = await call_next(request)
        response.headers["x-ratelimit-remaining"] = str(remaining)
        return response

    async def _allow(self, key: str) -> tuple[bool, int]:
        redis = get_redis()
        if redis is None:
            return await self.memory_limiter.allow(key)

        redis_key = f"rate_limit:{key}"
        count = await redis.incr(redis_key)
        if count == 1:
            await redis.expire(redis_key, self.settings.rate_limit_window_seconds)
        return count <= self.settings.rate_limit_requests, max(
            0,
            self.settings.rate_limit_requests - count,
        )
