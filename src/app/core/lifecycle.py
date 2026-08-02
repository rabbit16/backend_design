from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import inspect
from sqlalchemy.exc import OperationalError

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


def _create_missing_tables(connection) -> None:  # noqa: ANN001
    """只创建尚不存在的表，避免 MySQL 1050（表已存在）。"""
    existing = set(inspect(connection).get_table_names())
    missing = [table for table in Base.metadata.sorted_tables if table.name not in existing]
    if not missing:
        logger.info("db_schema_up_to_date", tables=len(existing))
        return
    logger.info("db_creating_missing_tables", tables=[t.name for t in missing])
    try:
        Base.metadata.create_all(connection, tables=missing, checkfirst=True)
    except OperationalError as exc:
        # 并发启动等边界情况：表已存在则忽略
        if getattr(exc.orig, "args", [None])[0] != 1050:
            raise
        logger.warning("db_create_skipped_existing", error=str(exc.orig))


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("app_starting")
    settings = get_settings()
    if settings.app_env in {"local", "dev", "test"}:
        async with engine.begin() as conn:
            await conn.run_sync(_create_missing_tables)
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
