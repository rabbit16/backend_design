"""用户当前问答上下文（session_id）缓存。

适老化场景：前端不传 session_id，后端按 user_id 自动匹配未过期上下文；
过期或不存在则新建。

过期策略（固定窗口，非滑动续期）：
- 新建上下文时写入 Redis，TTL = 30 天（可配置）
- 30 天内无论是否继续提问，都不刷新 TTL
- 到期后 key 自动失效，下次提问创建新的 context_id
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from src.app.cache.redis import get_redis
from src.app.core.config import get_settings
from src.app.core.logging import get_logger

logger = get_logger(__name__)

_KEY_PREFIX = "qa:context:user:"


@dataclass
class _MemoryEntry:
    session_id: str
    expires_at: float


_memory_store: dict[str, _MemoryEntry] = {}


def clear_context_store() -> None:
    _memory_store.clear()


def _key(user_id: str) -> str:
    return f"{_KEY_PREFIX}{user_id}"


class QaContextStore:
    """Redis 优先；未启用 Redis 时用进程内缓存（开发/单测）。"""

    def __init__(self, ttl_seconds: int | None = None) -> None:
        settings = get_settings()
        self.ttl_seconds = ttl_seconds or settings.qa_context_ttl_seconds

    async def get(self, user_id: str) -> str | None:
        redis = get_redis()
        if redis is not None:
            value = await redis.get(_key(user_id))
            return value if isinstance(value, str) and value else None

        entry = _memory_store.get(user_id)
        if entry is None:
            return None
        if time.monotonic() >= entry.expires_at:
            _memory_store.pop(user_id, None)
            return None
        return entry.session_id

    async def set(self, user_id: str, session_id: str) -> None:
        """仅在新建上下文时调用；写入后 TTL 不再因提问而延长。"""
        redis = get_redis()
        if redis is not None:
            await redis.set(_key(user_id), session_id, ex=self.ttl_seconds)
            logger.info(
                "qa_context_set",
                user_id=user_id,
                session_id=session_id,
                ttl_seconds=self.ttl_seconds,
                backend="redis",
            )
            return

        _memory_store[user_id] = _MemoryEntry(
            session_id=session_id,
            expires_at=time.monotonic() + self.ttl_seconds,
        )
        logger.info(
            "qa_context_set",
            user_id=user_id,
            session_id=session_id,
            ttl_seconds=self.ttl_seconds,
            backend="memory",
        )

    async def clear(self, user_id: str) -> None:
        redis = get_redis()
        if redis is not None:
            await redis.delete(_key(user_id))
            return
        _memory_store.pop(user_id, None)
