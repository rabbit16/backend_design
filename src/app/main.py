from fastapi import FastAPI

from src.app.api.router import register_routes
from src.app.connections.manager import init_connection_manager
from src.app.core.config import get_settings
from src.app.core.exceptions import register_exception_handlers
from src.app.core.lifecycle import lifespan
from src.app.core.logging import configure_logging
from src.app.middleware.registry import register_middlewares
from src.app.observability.tracing import configure_tracing


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        lifespan=lifespan,
    )

    init_connection_manager(settings.max_ws_connections)
    register_exception_handlers(app)
    register_middlewares(app, settings)
    register_routes(app, settings)
    configure_tracing(app, settings)
    return app


app = create_app()

if __name__ == '__main__':
    ...

