import json
import sqlite3
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool, ToolException
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import SecretStr
from pytest import MonkeyPatch

from apps.agent_app.audit import AgentAuditLog
from apps.agent_app.config import AgentAppSettings
from apps.agent_app.graph import (
    build_agent_graph,
    build_sqlite_checkpointer,
    compile_agent_graph,
    format_tool_error_for_llm,
    merge_state_for_audit,
)
from apps.agent_app.llm import create_chat_model
from apps.agent_app.mcp_registry import (
    MCPToolExecutionError,
    build_mcp_client,
    build_mcp_client_config,
    build_mcp_server_specs,
    convert_mcp_tool_content,
)
from apps.agent_app.state import AgentState


def test_agent_mcp_config_includes_existing_three_mcp_styles() -> None:
    settings = AgentAppSettings()

    config = build_mcp_client_config(settings)

    assert config["email"] == {
        "transport": "streamable_http",
        "url": "http://127.0.0.1:8111/mcp",
    }
    assert config["calendar"] == {
        "transport": "streamable_http",
        "url": "http://127.0.0.1:8013/mcp/",
    }
    assert config["todo"] == {
        "transport": "stdio",
        "command": sys.executable,
        "args": ["-m", "apps.todo_MCP.main"],
    }
    assert settings.llm_provider == "ollama"
    assert settings.llm_model == "gemma4:31b"
    assert settings.ollama_base_url == "http://127.0.0.1:11434"


def test_agent_llm_factory_uses_ollama_by_default() -> None:
    settings = AgentAppSettings()

    model = create_chat_model(settings)

    assert type(model).__name__ == "ChatOllama"
    assert model.model == "gemma4:31b"
    assert str(model.base_url).rstrip("/") == "http://127.0.0.1:11434"


def test_agent_llm_factory_can_switch_to_openai() -> None:
    settings = AgentAppSettings(
        llm_provider="openAI",
        llm_model="gpt-4.1-mini",
        openai_api_key=SecretStr("sk-test"),
    )

    model = create_chat_model(settings)

    assert settings.llm_provider == "openai"
    assert type(model).__name__ == "ChatOpenAI"
    assert model.model_name == "gpt-4.1-mini"


def test_agent_stdio_client_uses_explicit_transport_wrapper() -> None:
    settings = AgentAppSettings()

    specs = build_mcp_server_specs(settings)
    todo_spec = next(spec for spec in specs if spec.name == "todo")
    client = build_mcp_client(todo_spec)

    assert todo_spec.target == sys.executable
    assert todo_spec.args == ("-m", "apps.todo_MCP.main")
    assert "StdioServerParameters" not in type(client.server).__name__


def test_agent_runs_user_llm_tool_toolmessage_llm_final(tmp_path: Path) -> None:
    audit_log = create_audit_log(tmp_path)
    tracker = FakeToolTracker()
    model = ScriptedChatModel(
        [
            AIMessage(
                content="I will read the oldest unread email.",
                tool_calls=[
                    {
                        "name": "email_get_oldest_unread_email",
                        "args": {},
                        "id": "call_email",
                    }
                ],
            ),
            AIMessage(content="The oldest unread email is email-1."),
        ]
    )
    runtime = build_agent_graph(
        model,
        tracker.tools(),
        audit_log,
        checkpointer=InMemorySaver(),
    )

    response = runtime.run("Read my oldest unread email", thread_id="thread-e2e")
    state = response["state"]
    tool_messages = [message for message in state["messages"] if isinstance(message, ToolMessage)]

    assert state["status"] == "completed"
    assert state["final_response"] == "The oldest unread email is email-1."
    assert tracker.calls == [("email_get_oldest_unread_email", {})]
    assert len(tool_messages) == 1
    assert tool_messages[0].tool_call_id == "call_email"
    assert model.invocation_count == 2
    assert count_rows(audit_log.db_path, "tool_calls") == 1
    assert isinstance(model.seen_messages[0][0], SystemMessage)
    assert "MCP tools" in str(model.seen_messages[0][0].content)


def test_agent_executes_multiple_sequential_tool_calls_before_finalizing(
    tmp_path: Path,
) -> None:
    audit_log = create_audit_log(tmp_path)
    tracker = FakeToolTracker()
    model = ScriptedChatModel(
        [
            AIMessage(
                content="Read email first.",
                tool_calls=[
                    {
                        "name": "email_get_oldest_unread_email",
                        "args": {},
                        "id": "call_email",
                    }
                ],
            ),
            AIMessage(
                content="Find the related meeting.",
                tool_calls=[
                    {
                        "name": "calendar_search_calendar_events",
                        "args": {"query": "Dog"},
                        "id": "call_calendar",
                    }
                ],
            ),
            AIMessage(
                content="Create the follow-up task.",
                tool_calls=[
                    {
                        "name": "todo_create_todo_task",
                        "args": {"title": "Follow up"},
                        "id": "call_todo",
                    }
                ],
            ),
            AIMessage(content="All done."),
        ]
    )
    runtime = build_agent_graph(
        model,
        tracker.tools(),
        audit_log,
        checkpointer=InMemorySaver(),
    )

    response = runtime.run("Process the oldest unread email", thread_id="thread-multi")
    state = response["state"]
    tool_messages = [message for message in state["messages"] if isinstance(message, ToolMessage)]

    assert state["status"] == "completed"
    assert state["final_response"] == "All done."
    assert tracker.calls == [
        ("email_get_oldest_unread_email", {}),
        ("calendar_search_calendar_events", {"query": "Dog"}),
        ("todo_create_todo_task", {"title": "Follow up"}),
    ]
    assert len(tool_messages) == 3
    assert model.invocation_count == 4
    assert count_rows(audit_log.db_path, "human_interrupts") == 0
    assert count_rows(audit_log.db_path, "tool_calls") == 3


def test_agent_rejects_batched_state_changing_tool_calls(tmp_path: Path) -> None:
    audit_log = create_audit_log(tmp_path)
    tracker = FakeMutatingToolTracker()
    model = ScriptedChatModel(
        [
            AIMessage(
                content="I will create the event and mark the email read.",
                tool_calls=[
                    {
                        "name": "calendar_create_calendar_event",
                        "args": {"title": "Meeting"},
                        "id": "call_calendar",
                    },
                    {
                        "name": "email_mark_email_read",
                        "args": {"message_id": "email-1"},
                        "id": "call_email",
                    },
                ],
            ),
            AIMessage(content="I need to do one state-changing action at a time."),
        ]
    )
    runtime = build_agent_graph(
        model,
        tracker.tools(),
        audit_log,
        checkpointer=InMemorySaver(),
    )

    response = runtime.run("Create meeting from email", thread_id="thread-policy")
    state = response["state"]
    tool_messages = [message for message in state["messages"] if isinstance(message, ToolMessage)]

    assert tracker.calls == []
    assert state["status"] == "completed"
    assert state["final_response"] == "I need to do one state-changing action at a time."
    assert len(tool_messages) == 2
    assert {message.tool_call_id for message in tool_messages} == {"call_calendar", "call_email"}
    assert all(message.status == "error" for message in tool_messages)
    assert "state-changing tools must be called one at a time" in str(tool_messages[0].content)
    assert model.invocation_count == 2
    assert count_rows(audit_log.db_path, "tool_calls") == 0


def test_agent_allows_batched_read_only_tool_calls(tmp_path: Path) -> None:
    audit_log = create_audit_log(tmp_path)
    tracker = FakeReadOnlyToolTracker()
    model = ScriptedChatModel(
        [
            AIMessage(
                content="I will inspect email and calendar.",
                tool_calls=[
                    {
                        "name": "email_get_oldest_unread_email",
                        "args": {},
                        "id": "call_email",
                    },
                    {
                        "name": "calendar_search_calendar_events",
                        "args": {"query": "Planning"},
                        "id": "call_calendar",
                    },
                ],
            ),
            AIMessage(content="I inspected both."),
        ]
    )
    runtime = build_agent_graph(
        model,
        tracker.tools(),
        audit_log,
        checkpointer=InMemorySaver(),
    )

    response = runtime.run("Inspect context", thread_id="thread-read-only-batch")
    state = response["state"]
    tool_messages = [message for message in state["messages"] if isinstance(message, ToolMessage)]

    assert tracker.calls == [
        ("email_get_oldest_unread_email", {}),
        ("calendar_search_calendar_events", {"query": "Planning"}),
    ]
    assert len(tool_messages) == 2
    assert all(message.status != "error" for message in tool_messages)
    assert state["final_response"] == "I inspected both."
    assert count_rows(audit_log.db_path, "tool_calls") == 2


def test_tool_error_returns_to_llm_instead_of_interrupting(tmp_path: Path) -> None:
    audit_log = create_audit_log(tmp_path)
    model = ScriptedChatModel(
        [
            AIMessage(
                content="Try moving the event.",
                tool_calls=[
                    {
                        "name": "calendar_update_calendar_event",
                        "args": {
                            "event_id": "event-1",
                            "start_at": "2026-08-27T15:00:00",
                        },
                        "id": "call_calendar",
                    }
                ],
            ),
            AIMessage(content="I could not move it because Calendar overlap."),
        ]
    )
    runtime = build_agent_graph(
        model,
        [error_tool()],
        audit_log,
        checkpointer=InMemorySaver(),
    )

    response = runtime.run("Move event", thread_id="thread-conflict")
    state = response["state"]
    tool_messages = [message for message in state["messages"] if isinstance(message, ToolMessage)]

    assert "__interrupt__" not in state
    assert state["status"] == "completed"
    assert state["final_response"] == "I could not move it because Calendar overlap."
    assert tool_messages[0].status == "error"
    assert model.invocation_count == 2
    assert count_rows(audit_log.db_path, "human_interrupts") == 0
    tool_result = latest_json(audit_log.db_path, "tool_calls", "result_json")
    assert tool_result["status"] == "error"
    assert latest_value(audit_log.db_path, "tool_calls", "error") is not None


def test_tool_error_formatter_returns_clean_message() -> None:
    error = MCPToolExecutionError("VALIDATION_ERROR: start_at must not include timezone")

    assert format_tool_error_for_llm(error) == (
        "VALIDATION_ERROR: start_at must not include timezone"
    )


def test_sync_run_rejects_async_only_tools(tmp_path: Path) -> None:
    audit_log = create_audit_log(tmp_path)
    model = ScriptedChatModel([AIMessage(content="No tool needed.")])
    runtime = build_agent_graph(
        model,
        [async_only_tool()],
        audit_log,
        checkpointer=InMemorySaver(),
    )

    with pytest.raises(RuntimeError, match="Use arun"):
        runtime.run("Call async tool", thread_id="thread-async-only")


def test_audit_snapshot_merge_applies_message_reducer() -> None:
    first = AIMessage(content="First", id="same-id")
    replacement = AIMessage(content="Replacement", id="same-id")
    appended = ToolMessage(content="Tool result", tool_call_id="call-1")

    state: AgentState = {"messages": [first], "run_id": "run-1", "thread_id": "thread-1"}
    updates: AgentState = {"messages": [replacement, appended], "status": "running"}

    merged = merge_state_for_audit(state, updates)

    assert [message.content for message in merged["messages"]] == [
        "Replacement",
        "Tool result",
    ]
    assert merged["status"] == "running"


def test_direct_graph_execution_creates_missing_audit_ids(tmp_path: Path) -> None:
    audit_log = create_audit_log(tmp_path)
    model = ScriptedChatModel([AIMessage(content="Hello from Studio.")])
    graph = compile_agent_graph(
        model,
        [],
        audit_log,
        checkpointer=InMemorySaver(),
        allow_sync=True,
    )

    state = graph.invoke(
        {"messages": [HumanMessage(content="Hello")]},
        {"configurable": {"thread_id": "studio-thread"}},
    )

    assert state["thread_id"] == "studio-thread"
    assert state["run_id"]
    assert state["user_input"] == "Hello"
    assert state["status"] == "completed"
    assert count_rows(audit_log.db_path, "agent_runs") == 1


def test_sqlite_checkpointer_can_be_created(tmp_path: Path) -> None:
    checkpointer = build_sqlite_checkpointer(tmp_path / "agent_checkpoints.db")

    assert checkpointer is not None


def test_convert_mcp_tool_content_prefers_structured_content() -> None:
    class TextBlock:
        text = "text fallback"

    content = convert_mcp_tool_content([TextBlock()], {"id": "123"})

    assert content == {"id": "123"}


def test_convert_mcp_tool_content_falls_back_to_text_content() -> None:
    class TextBlock:
        text = "hello"

    content = convert_mcp_tool_content([TextBlock()], None)

    assert content == "hello"


def test_langgraph_studio_fallback_entrypoint_is_exported() -> None:
    from apps.agent_app.studio import graph, make_graph

    assert graph is not None
    assert make_graph is not None


def test_langgraph_json_uses_studio_factory() -> None:
    config = json.loads(Path("langgraph.json").read_text(encoding="utf-8"))

    assert config["graphs"]["agent"] == "./apps/agent_app/studio.py:make_graph"


def test_langgraph_studio_real_runtime_fails_fast(monkeypatch: MonkeyPatch) -> None:
    from apps.agent_app import studio

    class ExplodingRegistry:
        def __init__(self, settings: AgentAppSettings) -> None:
            self.settings = settings

        async def __aenter__(self) -> "ExplodingRegistry":
            raise RuntimeError("mcp unavailable")

        async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> bool | None:
            return None

    monkeypatch.setenv("AGENT_STUDIO_USE_REAL_RUNTIME", "true")
    monkeypatch.setattr(studio, "PersistentMCPToolRegistry", ExplodingRegistry)

    async def enter_studio_graph() -> None:
        async with studio.make_graph():
            pass

    with pytest.raises(RuntimeError, match="mcp unavailable"):
        asyncio_run(enter_studio_graph())


class ScriptedChatModel:
    def __init__(self, responses: list[AIMessage]) -> None:
        self.responses = responses
        self.invocation_count = 0
        self.seen_messages: list[list[AnyMessage]] = []

    def bind_tools(self, tools: Sequence[StructuredTool | Any]) -> "ScriptedChatModel":
        return self

    def invoke(self, messages: list[AnyMessage]) -> AIMessage:
        self.seen_messages.append(messages)
        response = self.responses[self.invocation_count]
        self.invocation_count += 1
        return response


class FakeToolTracker:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def tools(self) -> list[StructuredTool]:
        return [
            StructuredTool.from_function(
                self.email_get_oldest_unread_email,
                name="email_get_oldest_unread_email",
                description="Get oldest unread email.",
                metadata={"read_only": True},
            ),
            StructuredTool.from_function(
                self.calendar_search_calendar_events,
                name="calendar_search_calendar_events",
                description="Search calendar events.",
                metadata={"read_only": True},
            ),
            StructuredTool.from_function(
                self.todo_create_todo_task,
                name="todo_create_todo_task",
                description="Create todo task.",
                metadata={"read_only": False},
            ),
        ]

    def email_get_oldest_unread_email(self) -> str:
        self.calls.append(("email_get_oldest_unread_email", {}))
        return "email-1"

    def calendar_search_calendar_events(self, query: str) -> str:
        self.calls.append(("calendar_search_calendar_events", {"query": query}))
        return "event-1"

    def todo_create_todo_task(self, title: str) -> str:
        self.calls.append(("todo_create_todo_task", {"title": title}))
        return "task-1"


class FakeMutatingToolTracker:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def tools(self) -> list[StructuredTool]:
        return [
            StructuredTool.from_function(
                self.calendar_create_calendar_event,
                name="calendar_create_calendar_event",
                description="Create calendar event.",
                metadata={"read_only": False},
            ),
            StructuredTool.from_function(
                self.email_mark_email_read,
                name="email_mark_email_read",
                description="Mark email read.",
                metadata={"read_only": False},
            ),
        ]

    def calendar_create_calendar_event(self, title: str) -> str:
        self.calls.append(("calendar_create_calendar_event", {"title": title}))
        return "event-1"

    def email_mark_email_read(self, message_id: str) -> str:
        self.calls.append(("email_mark_email_read", {"message_id": message_id}))
        return "email-1"


class FakeReadOnlyToolTracker:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def tools(self) -> list[StructuredTool]:
        return [
            StructuredTool.from_function(
                self.email_get_oldest_unread_email,
                name="email_get_oldest_unread_email",
                description="Get oldest unread email.",
                metadata={"read_only": True},
            ),
            StructuredTool.from_function(
                self.calendar_search_calendar_events,
                name="calendar_search_calendar_events",
                description="Search calendar events.",
                metadata={"read_only": True},
            ),
        ]

    def email_get_oldest_unread_email(self) -> str:
        self.calls.append(("email_get_oldest_unread_email", {}))
        return "email-1"

    def calendar_search_calendar_events(self, query: str) -> str:
        self.calls.append(("calendar_search_calendar_events", {"query": query}))
        return "event-1"


def error_tool() -> StructuredTool:
    def calendar_update_calendar_event(event_id: str, start_at: str) -> str:
        raise ToolException(
            f"Calendar overlap for event_id={event_id}, start_at={start_at}"
        )

    return StructuredTool.from_function(
        calendar_update_calendar_event,
        name="calendar_update_calendar_event",
        description="Update calendar event.",
    )


def async_only_tool() -> StructuredTool:
    async def calendar_search_calendar_events(query: str) -> str:
        return f"event for {query}"

    return StructuredTool.from_function(
        coroutine=calendar_search_calendar_events,
        name="calendar_search_calendar_events",
        description="Search calendar events.",
    )


def create_audit_log(tmp_path: Path) -> AgentAuditLog:
    audit_log = AgentAuditLog(tmp_path / "agent_debug.db")
    audit_log.setup()
    return audit_log


def count_rows(db_path: Path, table_name: str) -> int:
    with sqlite3.connect(db_path) as connection:
        cursor = connection.execute(f"select count(*) from {table_name}")
        value = cursor.fetchone()[0]
    return int(value)


def latest_json(db_path: Path, table_name: str, column_name: str) -> dict[str, object]:
    with sqlite3.connect(db_path) as connection:
        cursor = connection.execute(
            f"select {column_name} from {table_name} order by id desc limit 1"
        )
        value = cursor.fetchone()[0]
    return dict(json.loads(value))


def latest_value(db_path: Path, table_name: str, column_name: str) -> object:
    with sqlite3.connect(db_path) as connection:
        cursor = connection.execute(
            f"select {column_name} from {table_name} order by id desc limit 1"
        )
        return cursor.fetchone()[0]


def asyncio_run(awaitable: Any) -> Any:
    import asyncio

    return asyncio.run(awaitable)
