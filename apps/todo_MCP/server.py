from typing import Literal, cast

from mcp.server import MCPServer
from sqlalchemy.orm import Session, sessionmaker

from apps.todo_MCP.tools import register_tools

APP_VERSION = "0.1.0"
SERVER_NAME = "Todo MCP server"
MCPLogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
MCP_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


def create_mcp_server(
    session_factory: sessionmaker[Session],
    *,
    log_level: str = "INFO",
) -> MCPServer:
    normalized_log_level = normalize_mcp_log_level(log_level)
    mcp = MCPServer(
        SERVER_NAME,
        version=APP_VERSION,
        log_level=normalized_log_level,
    )
    register_tools(mcp, session_factory)
    return mcp


def normalize_mcp_log_level(log_level: str) -> MCPLogLevel:
    normalized = log_level.upper()
    if normalized not in MCP_LOG_LEVELS:
        msg = f"Unsupported log level: {log_level}"
        raise ValueError(msg)
    return cast(MCPLogLevel, normalized)
