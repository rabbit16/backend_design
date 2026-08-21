from redis.asyncio import ConnectionPool, Redis

from src.app.core.config import get_settings

_pool: ConnectionPool | None = None
_client: Redis | None = None


def init_redis() -> Redis | None:
    global _pool, _client
    settings = get_settings()
    if not settings.redis_enabled:
        return None
    _pool = ConnectionPool.from_url(
        settings.redis_url,
        max_connections=settings.redis_max_connections,
        decode_responses=True,
    )
    _client = Redis(connection_pool=_pool)
    return _client


def get_redis() -> Redis | None:
    return _client


async def close_redis() -> None:
    global _pool, _client
    if _client is not None:
        await _client.aclose()
    if _pool is not None:
        await _pool.aclose()
    _client = None
    _pool = None
