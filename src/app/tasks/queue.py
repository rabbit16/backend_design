import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from src.app.core.config import get_settings
from src.app.core.logging import get_logger

logger = get_logger(__name__)

TaskCallable = Callable[..., Awaitable[Any]]


@dataclass(frozen=True)
class QueuedTask:
    name: str
    func: TaskCallable
    args: tuple[Any, ...]
    kwargs: dict[str, Any]


class TaskQueue:
    def __init__(self, worker_count: int, max_size: int) -> None:
        self.queue: asyncio.Queue[QueuedTask] = asyncio.Queue(maxsize=max_size)
        self.worker_count = worker_count
        self._workers: list[asyncio.Task] = []
        self._stopping = asyncio.Event()

    async def start(self) -> None:
        self._stopping.clear()
        self._workers = [
            asyncio.create_task(self._worker(i), name=f"task-worker-{i}")
            for i in range(self.worker_count)
        ]

    async def stop(self) -> None:
        self._stopping.set()
        await self.queue.join()
        for worker in self._workers:
            worker.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()

    async def enqueue(self, name: str, func: TaskCallable, *args: Any, **kwargs: Any) -> None:
        await self.queue.put(QueuedTask(name=name, func=func, args=args, kwargs=kwargs))

    async def _worker(self, worker_id: int) -> None:
        while not self._stopping.is_set():
            task = await self.queue.get()
            try:
                await task.func(*task.args, **task.kwargs)
                logger.info("task_completed", worker_id=worker_id, task=task.name)
            except Exception as exc:
                logger.exception("task_failed", worker_id=worker_id, task=task.name, error=str(exc))
            finally:
                self.queue.task_done()


_queue: TaskQueue | None = None


def init_task_queue() -> TaskQueue:
    global _queue
    settings = get_settings()
    _queue = TaskQueue(
        worker_count=settings.task_worker_count,
        max_size=settings.task_queue_max_size,
    )
    return _queue


def get_task_queue() -> TaskQueue:
    if _queue is None:
        raise RuntimeError("Task queue is not initialized")
    return _queue
