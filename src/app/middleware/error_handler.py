from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from src.app.core.logging import get_logger

logger = get_logger(__name__)


class ErrorBoundaryMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        try:
            return await call_next(request)
        except Exception as exc:
            logger.exception("middleware_unhandled_error", path=request.url.path, error=str(exc))
            return JSONResponse(
                status_code=500,
                content={"code": "internal_server_error", "message": "Internal server error"},
            )
