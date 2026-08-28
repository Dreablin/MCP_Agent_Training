from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver

from apps.agent_app.audit import AgentAuditLog
from apps.agent_app.config import PROJECT_ROOT, AgentAppSettings
from apps.agent_app.graph import compile_agent_graph
from apps.agent_app.llm import FallbackChatModel, create_chat_model
from apps.agent_app.local_tools import combine_agent_tools
from apps.agent_app.mcp_registry import PersistentMCPToolRegistry


def create_studio_audit_log() -> AgentAuditLog:
    audit_log = AgentAuditLog(PROJECT_ROOT / "data" / "agent_debug.db")
    audit_log.setup()
    return audit_log


def build_fallback_graph() -> Any:
    return compile_agent_graph(
        FallbackChatModel(),
        [],
        create_studio_audit_log(),
        checkpointer=InMemorySaver(),
        allow_sync=True,
    )


@asynccontextmanager
async def make_graph(runtime: Any = None) -> AsyncIterator[Any]:
    settings = AgentAppSettings()
    audit_log = create_studio_audit_log()

    if not settings.studio_use_real_runtime:
        yield compile_agent_graph(
            FallbackChatModel(),
            [],
            audit_log,
            checkpointer=InMemorySaver(),
            allow_sync=True,
        )
        return

    model = create_chat_model(settings)
    async with PersistentMCPToolRegistry(settings) as registry:
        yield compile_agent_graph(
            model,
            combine_agent_tools(registry.tools),
            audit_log,
            checkpointer=InMemorySaver(),
            allow_sync=False,
        )


graph = build_fallback_graph()
