from fastapi import FastAPI

from src.app.api.http import archives
from src.app.api.http import auth
from src.app.api.http import chat as http_chat
from src.app.api.http import health
from src.app.api.http import health_profile
from src.app.api.http import me
from src.app.api.http import qa
from src.app.api.http import tasks
from src.app.api.ws import chat as ws_chat
from src.app.core.config import Settings


def register_routes(app: FastAPI, settings: Settings) -> None:
    app.include_router(health.router, prefix=settings.api_v1_prefix)
    app.include_router(auth.router, prefix=settings.api_v1_prefix)
    app.include_router(me.router, prefix=settings.api_v1_prefix)
    app.include_router(qa.router, prefix=settings.api_v1_prefix)
    app.include_router(archives.router, prefix=settings.api_v1_prefix)
    app.include_router(health_profile.router, prefix=settings.api_v1_prefix)
    app.include_router(http_chat.router, prefix=settings.api_v1_prefix)
    app.include_router(tasks.router, prefix=settings.api_v1_prefix)
    app.include_router(ws_chat.router, prefix=settings.ws_v1_prefix)
