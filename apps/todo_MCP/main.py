from dataclasses import dataclass
from pathlib import Path

from mcp.server import MCPServer
from sqlalchemy import Engine

from apps.todo_app.config import TodoAppSettings, get_settings
from apps.todo_app.database import build_engine, build_session_factory
from apps.todo_app.models import Task  # noqa: F401
from apps.todo_MCP.server import create_mcp_server
from shared.database_setup import initialize_database_if_missing
from shared.logging import configure_logging, get_logger

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_CONFIG = PROJECT_ROOT / "apps" / "todo_app" / "alembic.ini"


@dataclass(frozen=True)
class TodoMCPRuntime:
    mcp: MCPServer
    engine: Engine


def create_runtime(settings: TodoAppSettings | None = None) -> TodoMCPRuntime:
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
    mcp = create_mcp_server(session_factory, log_level=resolved_settings.log_level)
    return TodoMCPRuntime(mcp=mcp, engine=engine)


def main(settings: TodoAppSettings | None = None) -> None:
    runtime = create_runtime(settings)
    logger = get_logger(__name__)
    logger.info("Starting Todo MCP server over stdio")
    try:
        runtime.mcp.run(transport="stdio")
    finally:
        runtime.engine.dispose()


if __name__ == "__main__":
    main()
