import asyncio
from collections import defaultdict

from fastapi import WebSocket

from src.app.core.exceptions import AppError


class ConnectionManager:
    def __init__(self, max_connections: int) -> None:
        self.max_connections = max_connections
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, client_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            if self.total_connections >= self.max_connections:
                raise AppError("Too many websocket connections", status_code=503)
            await websocket.accept()
            self._connections[client_id].add(websocket)

    async def disconnect(self, client_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            sockets = self._connections.get(client_id)
            if not sockets:
                return
            sockets.discard(websocket)
            if not sockets:
                self._connections.pop(client_id, None)

    async def send_to_client(self, client_id: str, message: dict) -> None:
        sockets = list(self._connections.get(client_id, set()))
        await asyncio.gather(*(socket.send_json(message) for socket in sockets), return_exceptions=True)

    async def broadcast(self, message: dict) -> None:
        sockets = [socket for group in self._connections.values() for socket in group]
        await asyncio.gather(*(socket.send_json(message) for socket in sockets), return_exceptions=True)

    @property
    def total_connections(self) -> int:
        return sum(len(sockets) for sockets in self._connections.values())


_manager: ConnectionManager | None = None


def init_connection_manager(max_connections: int) -> ConnectionManager:
    global _manager
    _manager = ConnectionManager(max_connections=max_connections)
    return _manager


def get_connection_manager() -> ConnectionManager:
    if _manager is None:
        raise RuntimeError("Connection manager is not initialized")
    return _manager
