from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from nicegui import ui

from apps.calendar_app.api import events_router
from apps.calendar_app.command_runner import CalendarCommandRunner
from apps.calendar_app.config import CalendarAppSettings, get_settings
from apps.calendar_app.database import build_engine, build_session_factory
from apps.calendar_app.events import CalendarEventBus
from apps.calendar_app.mcp_server import create_mcp_server
from apps.calendar_app.models import CalendarEvent  # noqa: F401
from apps.calendar_app.ui.pages import register_pages
from shared.database_setup import initialize_database_if_missing
from shared.errors import register_error_handlers
from shared.health import register_health_route
from shared.logging import configure_logging, get_logger

APP_VERSION = "0.1.0"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_CONFIG = PROJECT_ROOT / "apps" / "calendar_app" / "alembic.ini"


def create_app(settings: CalendarAppSettings | None = None, *, include_ui: bool = False) -> FastAPI:
    resolved_settings = settings or get_settings()
    resolved_settings.ensure_data_dir()
    configure_logging(resolved_settings.log_level)

    engine = build_engine(resolved_settings.database_url)
    initialize_database_if_missing(
        resolved_settings.db_path,
        resolved_settings.database_url,
        ALEMBIC_CONFIG,
        PROJECT_ROOT,
    )
    session_factory = build_session_factory(engine)

    event_bus = CalendarEventBus()
    command_runner = CalendarCommandRunner(session_factory, event_bus)
    mcp = create_mcp_server(session_factory, command_runner)
    mcp_app = mcp.streamable_http_app(streamable_http_path="/")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            async with mcp.session_manager.run():
                yield
        finally:
            engine.dispose()

    app = FastAPI(title=resolved_settings.app_name, version=APP_VERSION, lifespan=lifespan)
    app.state.settings = resolved_settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.calendar_event_bus = event_bus
    app.state.calendar_command_runner = command_runner
    app.state.mcp_server = mcp

    register_error_handlers(app)
    register_health_route(app, resolved_settings.app_name, APP_VERSION)
    app.include_router(events_router)
    app.mount("/mcp", mcp_app)

    if include_ui:
        register_pages(
            resolved_settings,
            app.state.session_factory,
            app.state.calendar_event_bus,
            app.state.calendar_command_runner,
        )
        ui.run_with(app)

    return app


def main() -> None:
    settings = get_settings()
    logger = get_logger(__name__)
    logger.info("Starting %s on %s:%s", settings.app_name, settings.host, settings.port)
    uvicorn.run(
        create_app(settings, include_ui=True),
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
