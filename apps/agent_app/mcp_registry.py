from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from typing import Any

from langchain_core.tools import BaseTool, StructuredTool, ToolException
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters, stdio_client

from apps.agent_app.config import PROJECT_ROOT, AgentAppSettings


@dataclass(frozen=True)
class MCPServerSpec:
    name: str
    transport: str
    target: str
    args: tuple[str, ...] = ()


class MCPToolExecutionError(ToolException):
    """Raised when an MCP tool returns CallToolResult(isError=True)."""


def build_mcp_server_specs(settings: AgentAppSettings) -> list[MCPServerSpec]:
    return [
        MCPServerSpec(
            name="email",
            transport="streamable_http",
            target=settings.email_mcp_url,
        ),
        MCPServerSpec(
            name="calendar",
            transport="streamable_http",
            target=settings.calendar_mcp_url,
        ),
        MCPServerSpec(
            name="todo",
            transport="stdio",
            target=settings.todo_mcp_command,
            args=settings.todo_mcp_args,
        ),
    ]


def build_mcp_client_config(settings: AgentAppSettings) -> dict[str, dict[str, Any]]:
    return {
        "email": {
            "transport": "streamable_http",
            "url": settings.email_mcp_url,
        },
        "calendar": {
            "transport": "streamable_http",
            "url": settings.calendar_mcp_url,
        },
        "todo": {
            "transport": "stdio",
            "command": settings.todo_mcp_command,
            "args": list(settings.todo_mcp_args),
        },
    }


class PersistentMCPToolRegistry:
    def __init__(self, settings: AgentAppSettings) -> None:
        self.settings = settings
        self.tools: list[BaseTool] = []
        self._clients: list[Client] = []
        self._exit_stack = AsyncExitStack()

    async def __aenter__(self) -> "PersistentMCPToolRegistry":
        await self._exit_stack.__aenter__()
        for spec in build_mcp_server_specs(self.settings):
            client = await self._exit_stack.enter_async_context(build_mcp_client(spec))
            self._clients.append(client)
            self.tools.extend(await load_tools_from_client(spec.name, client))
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> bool | None:
        return await self._exit_stack.__aexit__(exc_type, exc, traceback)


def build_mcp_client(spec: MCPServerSpec) -> Client:
    if spec.transport == "stdio":
        return Client(
            stdio_client(
                StdioServerParameters(
                    command=spec.target,
                    args=list(spec.args),
                    cwd=PROJECT_ROOT,
                )
            )
        )
    if spec.transport == "streamable_http":
        return Client(spec.target)
    msg = f"Unsupported MCP transport: {spec.transport}"
    raise ValueError(msg)


async def load_tools_from_client(server_name: str, client: Client) -> list[BaseTool]:
    result = await client.list_tools()
    return [
        build_langchain_tool(
            server_name,
            client,
            tool.name,
            tool.description or "",
            tool.input_schema,
            tool.annotations,
        )
        for tool in result.tools
    ]


def build_langchain_tool(
    server_name: str,
    client: Client,
    mcp_tool_name: str,
    description: str,
    input_schema: dict[str, Any],
    annotations: Any,
) -> BaseTool:
    async def call_mcp_tool(**arguments: Any) -> Any:
        result = await client.call_tool(mcp_tool_name, dict(arguments))
        content = convert_mcp_tool_content(result.content, result.structured_content)
        if result.is_error:
            raise MCPToolExecutionError(str(content))
        return content

    return StructuredTool(
        name=f"{server_name}_{mcp_tool_name}",
        description=description,
        args_schema=input_schema,
        coroutine=call_mcp_tool,
        metadata={
            "source": "mcp",
            "mcp_server": server_name,
            "mcp_tool_name": mcp_tool_name,
            "read_only": is_read_only_tool(annotations),
        },
    )


def convert_mcp_tool_content(content_blocks: list[Any], structured_content: Any) -> Any:
    if structured_content is not None:
        return structured_content

    text_parts: list[str] = []
    for block in content_blocks:
        text = getattr(block, "text", None)
        if isinstance(text, str):
            text_parts.append(text)
        else:
            text_parts.append(str(block))
    return "\n".join(text_parts)


def is_read_only_tool(annotations: Any) -> bool:
    return bool(getattr(annotations, "read_only_hint", False))


@asynccontextmanager
async def persistent_mcp_tool_registry(
    settings: AgentAppSettings,
) -> AsyncIterator[PersistentMCPToolRegistry]:
    async with PersistentMCPToolRegistry(settings) as registry:
        yield registry
