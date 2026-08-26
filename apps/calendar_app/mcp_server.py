from mcp.server import MCPServer
from sqlalchemy.orm import Session, sessionmaker

from apps.calendar_app.mcp_tools import register_tools

APP_VERSION = "0.1.0"


def create_mcp_server(session_factory: sessionmaker[Session]) -> MCPServer:
    mcp = MCPServer(
        "Calendar MCP server",
        version=APP_VERSION,
    )
    register_tools(mcp, session_factory)
    return mcp
