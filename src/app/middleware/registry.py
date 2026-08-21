from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from src.app.core.config import Settings
from src.app.middleware.access_log import AccessLogMiddleware
from src.app.middleware.error_handler import ErrorBoundaryMiddleware
from src.app.middleware.rate_limit import RateLimitMiddleware
from src.app.middleware.request_id import RequestIdMiddleware


def register_middlewares(app: FastAPI, settings: Settings) -> None:
    app.add_middleware(ErrorBoundaryMiddleware)
    app.add_middleware(RateLimitMiddleware, settings=settings)
    if settings.access_log:
        app.add_middleware(AccessLogMiddleware)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
