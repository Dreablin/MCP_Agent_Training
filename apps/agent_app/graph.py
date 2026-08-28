from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Protocol, cast
from uuid import uuid4

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig, RunnableLambda
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.types import Command

from apps.agent_app.audit import AgentAuditLog
from apps.agent_app.config import AgentAppSettings
from apps.agent_app.prompts import messages_with_system_prompt
from apps.agent_app.state import AgentState, HumanAnswer


class ToolBindableChatModel(Protocol):
    def bind_tools(self, tools: Sequence[BaseTool | Any]) -> Any:
        """Return a model/runnable configured for tool calling."""


class AgentGraphRuntime:
    def __init__(self, graph: Any, audit_log: AgentAuditLog, *, allow_sync: bool) -> None:
        self.graph = graph
        self.audit_log = audit_log
        self.allow_sync = allow_sync

    def run(self, user_input: str, thread_id: str | None = None) -> dict[str, Any]:
        self.ensure_sync_allowed()
        resolved_thread_id = thread_id or str(uuid4())
        run_id = str(uuid4())
        config = {"configurable": {"thread_id": resolved_thread_id}}
        state = initial_state(user_input, resolved_thread_id, run_id)
        self.audit_log.start_run(run_id, resolved_thread_id, user_input)
        result = self.graph.invoke(state, config)
        return {"thread_id": resolved_thread_id, "run_id": run_id, "state": result}

    async def arun(self, user_input: str, thread_id: str | None = None) -> dict[str, Any]:
        resolved_thread_id = thread_id or str(uuid4())
        run_id = str(uuid4())
        config = {"configurable": {"thread_id": resolved_thread_id}}
        state = initial_state(user_input, resolved_thread_id, run_id)
        self.audit_log.start_run(run_id, resolved_thread_id, user_input)
        result = await self.graph.ainvoke(state, config)
        return {"thread_id": resolved_thread_id, "run_id": run_id, "state": result}

    def resume(
        self,
        thread_id: str,
        run_id: str,
        answer: HumanAnswer,
    ) -> dict[str, Any]:
        self.ensure_sync_allowed()
        config = {"configurable": {"thread_id": thread_id}}
        result = self.graph.invoke(Command(resume=answer), config)
        return {"thread_id": thread_id, "run_id": run_id, "state": result}

    async def aresume(
        self,
        thread_id: str,
        run_id: str,
        answer: HumanAnswer,
    ) -> dict[str, Any]:
        config = {"configurable": {"thread_id": thread_id}}
        result = await self.graph.ainvoke(Command(resume=answer), config)
        return {"thread_id": thread_id, "run_id": run_id, "state": result}

    def ensure_sync_allowed(self) -> None:
        if self.allow_sync:
            return
        msg = (
            "Synchronous AgentGraphRuntime.run()/resume() are only supported for tests "
            "or synchronous tools. Use arun()/aresume() for the real MCP runtime."
        )
        raise RuntimeError(msg)


def initial_state(user_input: str, thread_id: str, run_id: str) -> AgentState:
    return {
        "run_id": run_id,
        "thread_id": thread_id,
        "user_input": user_input,
        "messages": [HumanMessage(content=user_input)],
        "status": "running",
    }


def build_agent_graph(
    model: ToolBindableChatModel,
    tools: Sequence[BaseTool | Any],
    audit_log: AgentAuditLog,
    *,
    checkpointer: Any,
    allow_sync: bool | None = None,
) -> AgentGraphRuntime:
    resolved_allow_sync = allow_sync if allow_sync is not None else not has_async_only_tools(tools)
    compiled_graph = compile_agent_graph(
        model,
        tools,
        audit_log,
        checkpointer=checkpointer,
        allow_sync=resolved_allow_sync,
    )
    return AgentGraphRuntime(compiled_graph, audit_log, allow_sync=resolved_allow_sync)


def compile_agent_graph(
    model: ToolBindableChatModel,
    tools: Sequence[BaseTool | Any],
    audit_log: AgentAuditLog,
    *,
    checkpointer: Any,
    allow_sync: bool | None = None,
) -> Any:
    builder = StateGraph(AgentState)
    model_with_tools = model.bind_tools(tools)
    resolved_allow_sync = allow_sync if allow_sync is not None else not has_async_only_tools(tools)
    tools_by_name = {tool.name: tool for tool in tools}

    def ensure_metadata(state: AgentState, config: RunnableConfig) -> AgentState:
        run_id = state.get("run_id") or str(uuid4())
        thread_id = state.get("thread_id") or thread_id_from_config(config) or str(uuid4())
        user_input = state.get("user_input") or user_input_from_state(state)
        updates: AgentState = {}
        if "run_id" not in state:
            updates["run_id"] = run_id
        if "thread_id" not in state:
            updates["thread_id"] = thread_id
        if "user_input" not in state:
            updates["user_input"] = user_input
        if "status" not in state:
            updates["status"] = "running"
        audit_log.ensure_run(run_id, thread_id, user_input)
        return updates

    def call_llm(state: AgentState) -> AgentState:
        if not resolved_allow_sync:
            msg = "Use async graph execution for runtimes with async-only tools."
            raise RuntimeError(msg)
        log_node_enter(audit_log, state, "llm")
        response = cast(
            AIMessage,
            model_with_tools.invoke(messages_with_system_prompt(state["messages"])),
        )
        updates: AgentState = {"messages": [response], "status": "running"}
        log_node_exit(audit_log, state, "llm", updates)
        return updates

    async def acall_llm(state: AgentState) -> AgentState:
        log_node_enter(audit_log, state, "llm")
        if hasattr(model_with_tools, "ainvoke"):
            response = cast(
                AIMessage,
                await model_with_tools.ainvoke(messages_with_system_prompt(state["messages"])),
            )
        else:
            response = cast(
                AIMessage,
                model_with_tools.invoke(messages_with_system_prompt(state["messages"])),
            )
        updates: AgentState = {"messages": [response], "status": "running"}
        log_node_exit(audit_log, state, "llm", updates)
        return updates

    def enforce_tool_policy(state: AgentState) -> AgentState:
        log_node_enter(audit_log, state, "enforce_tool_policy")
        latest = latest_message_from_state(state)
        if not isinstance(latest, AIMessage) or not latest.tool_calls:
            updates: AgentState = {"status": "running"}
            log_node_exit(audit_log, state, "enforce_tool_policy", updates)
            return updates

        violation = state_changing_batch_violation(latest.tool_calls, tools_by_name)
        if violation is None:
            updates = {"status": "running"}
            log_node_exit(audit_log, state, "enforce_tool_policy", updates)
            return updates

        audit_log.event(
            state["run_id"],
            state["thread_id"],
            "tool_policy_violation",
            node_name="enforce_tool_policy",
            payload={"tool_calls": latest.tool_calls, "reason": violation},
        )
        updates = {
            "messages": [
                ToolMessage(
                    content=violation,
                    name=str(tool_call.get("name", "")),
                    tool_call_id=str(tool_call.get("id", "")),
                    status="error",
                )
                for tool_call in latest.tool_calls
            ],
            "status": "running",
        }
        log_node_exit(audit_log, state, "enforce_tool_policy", updates)
        return updates

    tool_node = ToolNode(
        tools,
        handle_tool_errors=format_tool_error_for_llm,
        wrap_tool_call=make_audit_tool_wrapper(audit_log),
        awrap_tool_call=make_async_audit_tool_wrapper(audit_log),
    )

    def finalize(state: AgentState) -> AgentState:
        log_node_enter(audit_log, state, "finalize")
        final_response = final_response_from_state(state)
        updates: AgentState = {
            "final_response": final_response,
            "status": "completed",
        }
        audit_log.finish_run(state["run_id"], "completed")
        log_node_exit(audit_log, state, "finalize", updates)
        return updates

    builder.add_node("ensure_metadata", ensure_metadata)
    builder.add_node("llm", RunnableLambda(call_llm, afunc=acall_llm))
    builder.add_node("enforce_tool_policy", enforce_tool_policy)
    builder.add_node("tools", tool_node)
    builder.add_node("finalize", finalize)

    builder.add_edge(START, "ensure_metadata")
    builder.add_edge("ensure_metadata", "llm")
    builder.add_conditional_edges(
        "llm",
        route_after_llm,
        {
            "tools": "enforce_tool_policy",
            "final": "finalize",
        },
    )
    builder.add_conditional_edges(
        "enforce_tool_policy",
        route_after_tool_policy,
        {
            "tools": "tools",
            "llm": "llm",
        },
    )
    builder.add_edge("tools", "llm")
    builder.add_edge("finalize", END)

    return builder.compile(checkpointer=checkpointer)


def route_after_llm(state: AgentState) -> str:
    latest = latest_message_from_state(state)
    if isinstance(latest, AIMessage) and latest.tool_calls:
        return "tools"
    return "final"


def route_after_tool_policy(state: AgentState) -> str:
    latest = latest_message_from_state(state)
    if isinstance(latest, AIMessage) and latest.tool_calls:
        return "tools"
    return "llm"


def latest_message_from_state(state: AgentState) -> AnyMessage | None:
    messages = state.get("messages", [])
    if not messages:
        return None
    return messages[-1]


def final_response_from_state(state: AgentState) -> str:
    latest = latest_message_from_state(state)
    if latest is None:
        return ""
    return str(latest.content)


def format_tool_error_for_llm(exc: Exception) -> str:
    message = str(exc)
    if message:
        return message
    return type(exc).__name__


def state_changing_batch_violation(
    tool_calls: Sequence[Any],
    tools_by_name: dict[str, BaseTool | Any],
) -> str | None:
    if len(tool_calls) <= 1:
        return None
    state_changing_tool_names = [
        str(tool_call.get("name", "unknown_tool"))
        for tool_call in tool_calls
        if not tool_call_is_read_only(tool_call, tools_by_name)
    ]
    if not state_changing_tool_names:
        return None
    return (
        "Tool execution policy violation: state-changing tools must be called one "
        "at a time. Do not batch state-changing tools with other tool calls. "
        f"State-changing tools in this batch: {', '.join(state_changing_tool_names)}. "
        "Re-plan and call exactly one next tool, then wait for its ToolMessage result."
    )


def tool_call_is_read_only(
    tool_call: Any,
    tools_by_name: dict[str, BaseTool | Any],
) -> bool:
    tool_name = str(tool_call.get("name", ""))
    tool = tools_by_name.get(tool_name)
    if tool is None:
        return False
    metadata = getattr(tool, "metadata", None)
    if not isinstance(metadata, dict):
        return False
    return bool(metadata.get("read_only", False))


def thread_id_from_config(config: RunnableConfig) -> str | None:
    configurable = config.get("configurable")
    if not isinstance(configurable, dict):
        return None
    thread_id = configurable.get("thread_id")
    if isinstance(thread_id, str) and thread_id:
        return thread_id
    return None


def user_input_from_state(state: AgentState) -> str:
    for message in state.get("messages", []):
        if isinstance(message, HumanMessage):
            return str(message.content)
    return ""


def make_audit_tool_wrapper(audit_log: AgentAuditLog) -> Any:
    def wrap_tool_call(request: Any, execute: Any) -> ToolMessage | Command[Any]:
        import time

        state = cast(AgentState, request.state)
        tool_call = request.tool_call
        started = time.perf_counter()
        try:
            result = execute(request)
        except Exception as exc:
            duration_ms = round((time.perf_counter() - started) * 1000)
            audit_tool_exception(audit_log, state, tool_call, exc, duration_ms)
            raise
        duration_ms = round((time.perf_counter() - started) * 1000)
        audit_tool_result(audit_log, state, tool_call, result, duration_ms)
        return cast(ToolMessage | Command[Any], result)

    return wrap_tool_call


def make_async_audit_tool_wrapper(audit_log: AgentAuditLog) -> Any:
    async def awrap_tool_call(request: Any, execute: Any) -> ToolMessage | Command[Any]:
        import time

        state = cast(AgentState, request.state)
        tool_call = request.tool_call
        started = time.perf_counter()
        try:
            result = await execute(request)
        except Exception as exc:
            duration_ms = round((time.perf_counter() - started) * 1000)
            audit_tool_exception(audit_log, state, tool_call, exc, duration_ms)
            raise
        duration_ms = round((time.perf_counter() - started) * 1000)
        audit_tool_result(audit_log, state, tool_call, result, duration_ms)
        return cast(ToolMessage | Command[Any], result)

    return awrap_tool_call


def audit_tool_result(
    audit_log: AgentAuditLog,
    state: AgentState,
    tool_call: dict[str, Any],
    result: ToolMessage | Command[Any],
    duration_ms: int,
) -> None:
    result_payload: dict[str, Any]
    if isinstance(result, ToolMessage):
        result_payload = {
            "status": result.status,
            "content": result.content,
            "artifact": result.artifact,
        }
        if result.status == "error":
            result_payload["error"] = str(result.content)
    else:
        result_payload = {"command": str(result)}
    audit_log.tool_call(
        state["run_id"],
        state["thread_id"],
        str(tool_call["name"]),
        dict(tool_call.get("args", {})),
        result_payload,
        duration_ms,
    )


def audit_tool_exception(
    audit_log: AgentAuditLog,
    state: AgentState,
    tool_call: dict[str, Any],
    exc: Exception,
    duration_ms: int,
) -> None:
    audit_log.tool_call(
        state["run_id"],
        state["thread_id"],
        str(tool_call["name"]),
        dict(tool_call.get("args", {})),
        {"status": "error", "error": str(exc)},
        duration_ms,
    )


def log_node_enter(audit_log: AgentAuditLog, state: AgentState, node_name: str) -> None:
    audit_log.event(
        state["run_id"],
        state["thread_id"],
        "node_enter",
        node_name=node_name,
    )


def log_node_exit(
    audit_log: AgentAuditLog,
    state: AgentState,
    node_name: str,
    updates: AgentState,
) -> None:
    audit_log.event(
        state["run_id"],
        state["thread_id"],
        "node_exit",
        node_name=node_name,
        payload={"updates": updates},
    )
    audit_log.snapshot(
        state["run_id"],
        state["thread_id"],
        node_name,
        merge_state_for_audit(state, updates),
    )


def merge_state_for_audit(state: AgentState, updates: AgentState) -> dict[str, Any]:
    merged: dict[str, Any] = dict(state)
    update_values: dict[str, Any] = dict(updates)
    for key, value in update_values.items():
        if key == "messages":
            merged["messages"] = add_messages(cast(Any, state.get("messages", [])), value)
        else:
            merged[key] = value
    return merged


def has_async_only_tools(tools: Sequence[BaseTool | Any]) -> bool:
    for tool in tools:
        if getattr(tool, "coroutine", None) is not None and getattr(tool, "func", None) is None:
            return True
    return False


def build_sqlite_checkpointer(checkpoint_db_path: Path) -> Any:
    import sqlite3

    from langgraph.checkpoint.sqlite import SqliteSaver

    checkpoint_db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(checkpoint_db_path, check_same_thread=False)
    checkpointer = SqliteSaver(connection)
    checkpointer.setup()
    return checkpointer


def create_runtime(
    model: ToolBindableChatModel,
    tools: Sequence[BaseTool | Any],
    settings: AgentAppSettings | None = None,
) -> AgentGraphRuntime:
    resolved_settings = settings or AgentAppSettings()
    resolved_settings.ensure_data_dir()
    audit_log = AgentAuditLog(resolved_settings.audit_db_path)
    audit_log.setup()
    checkpointer = build_sqlite_checkpointer(resolved_settings.checkpoint_db_path)
    return build_agent_graph(model, tools, audit_log, checkpointer=checkpointer)


@asynccontextmanager
async def create_async_runtime(
    model: ToolBindableChatModel,
    tools: Sequence[BaseTool | Any],
    settings: AgentAppSettings | None = None,
) -> AsyncIterator[AgentGraphRuntime]:
    from langgraph.checkpoint.memory import InMemorySaver

    resolved_settings = settings or AgentAppSettings()
    resolved_settings.ensure_data_dir()
    audit_log = AgentAuditLog(resolved_settings.audit_db_path)
    audit_log.setup()
    yield build_agent_graph(
        model,
        tools,
        audit_log,
        checkpointer=InMemorySaver(),
        allow_sync=False,
    )
