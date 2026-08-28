from mcp.server import MCPServer

from apps.todo_MCP.config import TodoMCPSettings, get_settings
from apps.todo_MCP.tools import register_tools

APP_VERSION = "0.1.0"


def create_mcp_server(
    settings: TodoMCPSettings | None = None,
) -> MCPServer:
    resolved_settings = settings or get_settings()
    mcp = MCPServer(
        resolved_settings.app_name,
        version=APP_VERSION,
        log_level=resolved_settings.log_level,
    )
    register_tools(mcp, resolved_settings)
    return mcp
