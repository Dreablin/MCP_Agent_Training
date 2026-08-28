from mcp.server import MCPServer
from sqlalchemy.orm import Session, sessionmaker

from apps.calendar_app.command_runner import CalendarCommandRunner
from apps.calendar_app.mcp_tools import register_tools

APP_VERSION = "0.1.0"


def create_mcp_server(
    session_factory: sessionmaker[Session],
    command_runner: CalendarCommandRunner | None = None,
) -> MCPServer:
    resolved_runner = command_runner or CalendarCommandRunner(session_factory)
    mcp = MCPServer(
        "Calendar MCP server",
        version=APP_VERSION,
    )
    register_tools(mcp, session_factory, resolved_runner)
    return mcp
