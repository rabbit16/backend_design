from fastapi import WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.core.logging import get_logger
from app.schemas.chat import WebSocketChatMessage

logger = get_logger(__name__)


async def receive_chat_message(websocket: WebSocket) -> WebSocketChatMessage:
    payload = await websocket.receive_json()
    return WebSocketChatMessage.model_validate(payload)


async def safe_send_error(websocket: WebSocket, code: str, message: str) -> None:
    try:
        await websocket.send_json({"type": "error", "code": code, "message": message})
    except WebSocketDisconnect:
        return
    except RuntimeError as exc:
        logger.warning("websocket_send_error_failed", error=str(exc))


def validation_error_message(exc: ValidationError) -> str:
    first = exc.errors()[0]
    loc = ".".join(str(part) for part in first.get("loc", []))
    return f"{loc}: {first.get('msg', 'invalid payload')}"
