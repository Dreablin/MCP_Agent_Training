from dataclasses import dataclass

from mcp.server import MCPServer

from apps.todo_MCP.config import TodoMCPSettings, get_settings
from apps.todo_MCP.server import create_mcp_server
from shared.logging import configure_logging, get_logger


@dataclass(frozen=True)
class TodoMCPRuntime:
    mcp: MCPServer
    settings: TodoMCPSettings


def create_runtime(settings: TodoMCPSettings | None = None) -> TodoMCPRuntime:
    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings.log_level)
    mcp = create_mcp_server(resolved_settings)
    return TodoMCPRuntime(mcp=mcp, settings=resolved_settings)


def main(settings: TodoMCPSettings | None = None) -> None:
    runtime = create_runtime(settings)
    logger = get_logger(__name__)
    logger.info("Starting Todo MCP server over stdio")
    runtime.mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
