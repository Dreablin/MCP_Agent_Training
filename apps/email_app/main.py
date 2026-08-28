from pathlib import Path

import uvicorn
from fastapi import FastAPI
from nicegui import ui

from apps.email_app.api import messages_router
from apps.email_app.config import EmailAppSettings, get_settings
from apps.email_app.database import build_engine, build_session_factory
from apps.email_app.events import EmailEventBus
from apps.email_app.models import EmailMessage  # noqa: F401
from apps.email_app.ui.pages import register_pages
from shared.database_setup import initialize_database_if_missing
from shared.errors import register_error_handlers
from shared.health import register_health_route
from shared.logging import configure_logging, get_logger

APP_VERSION = "0.1.0"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_CONFIG = PROJECT_ROOT / "apps" / "email_app" / "alembic.ini"


def create_app(settings: EmailAppSettings | None = None, *, include_ui: bool = False) -> FastAPI:
    resolved_settings = settings or get_settings()
    resolved_settings.ensure_data_dir()
    configure_logging(resolved_settings.log_level)

    app = FastAPI(title=resolved_settings.app_name, version=APP_VERSION)
    app.state.settings = resolved_settings

    engine = build_engine(resolved_settings.database_url)
    initialize_database_if_missing(
        resolved_settings.db_path,
        resolved_settings.database_url,
        ALEMBIC_CONFIG,
        PROJECT_ROOT,
    )
    app.state.engine = engine
    app.state.session_factory = build_session_factory(engine)
    app.state.email_event_bus = EmailEventBus()

    register_error_handlers(app)
    register_health_route(app, resolved_settings.app_name, APP_VERSION)
    app.include_router(messages_router)

    if include_ui:
        register_pages(resolved_settings, app.state.session_factory, app.state.email_event_bus)
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
