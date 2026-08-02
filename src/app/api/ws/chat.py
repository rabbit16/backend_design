from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.connections.manager import get_connection_manager
from app.connections.websocket import receive_chat_message, safe_send_error, validation_error_message
from app.gateways.registry import create_gateway
from app.schemas.chat import ChatRequest

router = APIRouter(tags=["websocket-chat"])


@router.websocket("/chat/{client_id}")
async def chat_websocket(websocket: WebSocket, client_id: str, model: str = "echo") -> None:
    manager = get_connection_manager()
    await manager.connect(client_id, websocket)
    gateway = create_gateway(model)
    try:
        await websocket.send_json({"type": "connected", "client_id": client_id})
        while True:
            try:
                incoming = await receive_chat_message(websocket)
            except ValidationError as exc:
                await safe_send_error(websocket, "invalid_payload", validation_error_message(exc))
                continue

            request = ChatRequest(message=incoming.message, client_id=client_id, model=model, stream=True)
            await websocket.send_json({"type": "start"})
            async for token in gateway.stream(request):
                await websocket.send_json({"type": "token", "delta": token})
            await websocket.send_json({"type": "done"})
    except WebSocketDisconnect:
        return
    finally:
        await gateway.close()
        await manager.disconnect(client_id, websocket)
