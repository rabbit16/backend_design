from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.cache.redis import close_redis, init_redis
from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.base import Base
from app.db.session import dispose_engine, engine
from app.gateways.registry import close_gateway_registry, init_gateway_registry
from app.tasks.queue import init_task_queue

# 确保模型注册到 metadata
import app.db.models  # noqa: F401

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("app_starting")
    settings = get_settings()
    if settings.app_env in {"local", "dev", "test"}:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    init_redis()
    init_gateway_registry(app)
    task_queue = init_task_queue()
    await task_queue.start()
    yield
    await task_queue.stop()
    await close_gateway_registry(app)
    await close_redis()
    await dispose_engine()
    logger.info("app_stopped")
