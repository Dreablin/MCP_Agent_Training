from collections.abc import Sequence
from io import StringIO
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import InMemorySaver

from apps.agent_app.audit import AgentAuditLog
from apps.agent_app.cli import exception_messages, interactive_loop, parse_args, run_turn
from apps.agent_app.config import AgentAppSettings
from apps.agent_app.graph import build_agent_graph, create_async_runtime
from apps.agent_app.hitl import build_ask_human_tool


def test_parse_args_accepts_thread_id_and_debug() -> None:
    args = parse_args(["--thread-id", "debug-thread", "--debug"])

    assert args.thread_id == "debug-thread"
    assert args.debug is True


def test_run_turn_streams_tool_usage_and_final_response(tmp_path: Path) -> None:
    audit_log = create_audit_log(tmp_path)
    tracker = FakeToolTracker()
    model = ScriptedChatModel(
        [
            AIMessage(
                content="I will use email.",
                tool_calls=[
                    {
                        "name": "email_get_oldest_unread_email",
                        "args": {},
                        "id": "call-email",
                    }
                ],
            ),
            AIMessage(content="Email summary."),
        ]
    )
    runtime = build_agent_graph(
        model,
        tracker.tools(),
        audit_log,
        checkpointer=InMemorySaver(),
    )
    output = StringIO()

    final_response = asyncio_run(
        run_turn(runtime, "Read email", "cli-thread", output=output)
    )

    text = output.getvalue()
    assert "[llm] thinking..." in text
    assert "[tool] email_get_oldest_unread_email {}" in text
    assert "[tool:ok] email_get_oldest_unread_email email-1" in text
    assert "[final]" in text
    assert "Email summary." in text
    assert final_response == "Email summary."


def test_interactive_loop_handles_commands_and_exit(tmp_path: Path) -> None:
    audit_log = create_audit_log(tmp_path)
    model = ScriptedChatModel([AIMessage(content="Hello.")])
    runtime = build_agent_graph(
        model,
        [],
        audit_log,
        checkpointer=InMemorySaver(),
    )
    output = StringIO()
    commands = iter([":thread", ":help", "", "Hello", "exit"])

    asyncio_run(
        interactive_loop(
            runtime,
            "cli-thread",
            input_func=lambda prompt: next(commands),
            output=output,
        )
    )

    text = output.getvalue()
    assert "cli-thread" in text
    assert "Commands:" in text
    assert "Hello." in text
    assert text.endswith("Bye.\n")


def test_interactive_loop_keeps_one_thread_history(tmp_path: Path) -> None:
    audit_log = create_audit_log(tmp_path)
    model = ScriptedChatModel(
        [
            AIMessage(content="First answer."),
            AIMessage(content="Second answer."),
        ]
    )
    runtime = build_agent_graph(
        model,
        [],
        audit_log,
        checkpointer=InMemorySaver(),
    )
    output = StringIO()
    commands = iter(["First question", "Second question", "quit"])

    asyncio_run(
        interactive_loop(
            runtime,
            "cli-thread",
            input_func=lambda prompt: next(commands),
            output=output,
        )
    )

    second_turn_messages = model.seen_messages[1]
    human_messages = [
        message.content
        for message in second_turn_messages
        if isinstance(message, HumanMessage)
    ]
    assert human_messages == ["First question", "Second question"]


def test_run_turn_streams_tool_errors(tmp_path: Path) -> None:
    audit_log = create_audit_log(tmp_path)
    model = ScriptedChatModel(
        [
            AIMessage(
                content="Try tool.",
                tool_calls=[
                    {
                        "name": "broken_tool",
                        "args": {},
                        "id": "call-broken",
                    }
                ],
            ),
            AIMessage(content="Tool failed."),
        ]
    )
    runtime = build_agent_graph(
        model,
        [broken_tool()],
        audit_log,
        checkpointer=InMemorySaver(),
    )
    output = StringIO()

    asyncio_run(run_turn(runtime, "Break it", "cli-thread", output=output))

    assert "[tool:error] broken_tool" in output.getvalue()


def test_run_turn_handles_human_interrupt_and_resume(tmp_path: Path) -> None:
    audit_log = create_audit_log(tmp_path)
    model = ScriptedChatModel(
        [
            AIMessage(
                content="I need clarification.",
                tool_calls=[
                    {
                        "name": "ask_human",
                        "args": {
                            "question": "Which meeting should I cancel?",
                            "reason": "Two meetings match.",
                        },
                        "id": "call-human",
                    }
                ],
            ),
            AIMessage(content="I will cancel the second meeting."),
        ]
    )
    runtime = build_agent_graph(
        model,
        [build_ask_human_tool()],
        audit_log,
        checkpointer=InMemorySaver(),
        allow_sync=False,
    )
    output = StringIO()

    final_response = asyncio_run(
        run_turn(
            runtime,
            "Cancel dog meeting",
            "cli-thread",
            input_func=lambda prompt: "Cancel the second one.",
            output=output,
        )
    )

    text = output.getvalue()
    assert "[human] Which meeting should I cancel?" in text
    assert "[human:reason] Two meetings match." in text
    assert "[llm] resuming..." in text
    assert "[tool:ok] ask_human" in text
    assert "I will cancel the second meeting." in text
    assert final_response == "I will cancel the second meeting."
    assert any(isinstance(message, ToolMessage) for message in model.seen_messages[-1])


def test_cli_async_runtime_supports_async_streaming(tmp_path: Path) -> None:
    settings = AgentAppSettings(
        checkpoint_db_path=tmp_path / "agent_checkpoints.db",
        audit_db_path=tmp_path / "agent_debug.db",
    )
    model = ScriptedChatModel([AIMessage(content="Async runtime works.")])
    output = StringIO()

    async def run() -> str:
        async with create_async_runtime(model, [], settings) as runtime:
            return await run_turn(runtime, "Hello", "cli-thread", output=output)

    final_response = asyncio_run(run())

    assert final_response == "Async runtime works."
    assert "Async runtime works." in output.getvalue()


def test_exception_messages_unpack_exception_groups() -> None:
    exc = ExceptionGroup(
        "outer",
        [
            RuntimeError("first"),
            ExceptionGroup("inner", [ValueError("second")]),
        ],
    )

    assert exception_messages(exc) == [
        "RuntimeError: first",
        "ValueError: second",
    ]


def broken_tool() -> StructuredTool:
    def broken_tool() -> str:
        raise RuntimeError("boom")

    return StructuredTool.from_function(
        broken_tool,
        name="broken_tool",
        description="Always fails.",
    )


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
            )
        ]

    def email_get_oldest_unread_email(self) -> str:
        self.calls.append(("email_get_oldest_unread_email", {}))
        return "email-1"


def create_audit_log(tmp_path: Path) -> AgentAuditLog:
    audit_log = AgentAuditLog(tmp_path / "agent_debug.db")
    audit_log.setup()
    return audit_log


def asyncio_run(awaitable: Any) -> Any:
    import asyncio

    return asyncio.run(awaitable)
