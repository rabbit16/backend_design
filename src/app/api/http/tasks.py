from typing import Annotated

from fastapi import APIRouter, Depends

from app.schemas.response import ApiResponse, ok
from app.security.jwt import get_current_subject
from app.tasks.queue import get_task_queue

router = APIRouter(prefix="/tasks", tags=["tasks"])


async def demo_task(subject: str, payload: str) -> None:
    _ = (subject, payload)


@router.post("/demo", response_model=ApiResponse[dict[str, str]])
async def enqueue_demo_task(
    current_subject: Annotated[str, Depends(get_current_subject)],
) -> ApiResponse[dict[str, str]]:
    queue = get_task_queue()
    await queue.enqueue("demo_task", demo_task, current_subject, "hello")
    return ok({"status": "queued"})
