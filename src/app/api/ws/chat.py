from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.connections.manager import get_connection_manager
from app.connections.websocket import receive_chat_message, safe_send_error, validation_error_message
from app.core.config import get_settings
from app.gateways.registry import create_gateway
from app.schemas.chat import ChatRequest

router = APIRouter(tags=["websocket-chat"])


@router.websocket("/chat/{client_id}")
async def chat_websocket(websocket: WebSocket, client_id: str, model: str | None = None) -> None:
    settings = get_settings()
    provider = (model or settings.ai_gateway_provider).strip()
    manager = get_connection_manager()
    await manager.connect(client_id, websocket)
    gateway = create_gateway(provider)
    llm_model = settings.openai_model if provider.lower().startswith("openai") else provider
    try:
        await websocket.send_json(
            {
                "type": "connected",
                "client_id": client_id,
                "provider": getattr(gateway, "provider", provider),
                "model": llm_model,
            }
        )
        while True:
            try:
                incoming_msg = await receive_chat_message(websocket)
            except ValidationError as exc:
                await safe_send_error(websocket, "invalid_payload", validation_error_message(exc))
                continue

            request = ChatRequest(
                message=incoming_msg.message,
                client_id=client_id,
                model=llm_model,
                stream=True,
            )
            await websocket.send_json({"type": "start"})
            async for chunk in gateway.chat_completions_stream(request.to_openai()):
                delta = chunk.delta_content
                if delta:
                    await websocket.send_json({"type": "token", "delta": delta})
            await websocket.send_json({"type": "done"})
    except WebSocketDisconnect:
        return
    finally:
        await gateway.close()
        await manager.disconnect(client_id, websocket)
