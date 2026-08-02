from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

settings = get_settings()

if settings.database_url.startswith("sqlite"):
    database_file = settings.database_url.rsplit("///", maxsplit=1)[-1]
    if database_file not in {":memory:", ""}:
        Path(database_file).parent.mkdir(parents=True, exist_ok=True)

_engine_kwargs = {"echo": settings.database_echo, "pool_pre_ping": True}
if not settings.database_url.startswith("sqlite"):
    _engine_kwargs.update(
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
    )

engine = create_async_engine(settings.database_url, **_engine_kwargs)
AsyncSessionFactory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionFactory() as session:
        yield session


async def dispose_engine() -> None:
    await engine.dispose()
