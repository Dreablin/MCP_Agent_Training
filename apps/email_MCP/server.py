from mcp.server import MCPServer
from starlette.applications import Starlette

from apps.email_MCP.config import EmailMCPSettings, get_settings
from apps.email_MCP.tools import register_tools
from shared.logging import configure_logging

APP_VERSION = "0.1.0"


def create_mcp_server(settings: EmailMCPSettings | None = None) -> MCPServer:
    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings.log_level)

    mcp = MCPServer(
        resolved_settings.app_name,
        version=APP_VERSION,
        log_level=resolved_settings.log_level,
    )
    register_tools(mcp, resolved_settings)
    return mcp


def create_app(settings: EmailMCPSettings | None = None) -> Starlette:
    resolved_settings = settings or get_settings()
    mcp = create_mcp_server(resolved_settings)
    return mcp.streamable_http_app(streamable_http_path=resolved_settings.streamable_http_path)
