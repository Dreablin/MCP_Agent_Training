from collections.abc import Sequence
from io import StringIO
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import InMemorySaver

from apps.agent_app.audit import AgentAuditLog
from apps.agent_app.cli import (
    approval_answer,
    exception_messages,
    interactive_loop,
    parse_args,
    prompt_for_human_answer,
    render_tool_update,
    run_turn,
)
from apps.agent_app.config import AgentAppSettings
from apps.agent_app.graph import build_agent_graph, create_async_runtime
from apps.agent_app.hitl import build_ask_human_tool


def test_parse_args_accepts_thread_id_and_debug() -> None:
    args = parse_args(["--thread-id", "debug-thread", "--debug"])

    assert args.thread_id == "debug-thread"
    assert args.debug is True


def test_approval_answer_maps_numbered_options_and_rejects_unknown_input() -> None:
    assert approval_answer("1") == {"kind": "approve", "value": "1"}
    assert approval_answer("2") == {"kind": "reject", "value": "2"}
    assert approval_answer("Нет, не отправляй это письмо.") == {
        "kind": "reject",
        "value": "Нет, не отправляй это письмо.",
    }
    assert approval_answer("6") is None


def test_approval_prompt_repeats_after_unknown_input() -> None:
    answers = iter(["6", "1"])
    output = StringIO()

    answer = prompt_for_human_answer(
        {
            "kind": "tool_approval",
            "question": "Approve sending this email?",
            "options": [
                {"id": "approve", "label": "Approve"},
                {"id": "reject", "label": "Cancel"},
            ],
        },
        lambda prompt: next(answers),
        output,
    )

    assert answer == {"kind": "approve", "value": "1"}
    assert "[human:error] Choose 1 to approve or 2 to cancel." in output.getvalue()


def test_cancelled_tool_result_is_not_rendered_as_tool_ok() -> None:
    output = StringIO()
    message = ToolMessage(
        content=(
            '{"executed": false, "outcome": "rejected_by_user", '
            '"retryable": false, "status": "cancelled"}'
        ),
        name="email_send_email",
        tool_call_id="call-email",
        status="success",
    )

    render_tool_update({"messages": [message]}, output)

    assert output.getvalue().startswith("[tool:cancelled] email_send_email")


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


def test_run_turn_displays_email_approval_details(tmp_path: Path) -> None:
    audit_log = create_audit_log(tmp_path)
    sender = FakeEmailSender()
    model = ScriptedChatModel(
        [
            AIMessage(
                content="I will send the email.",
                tool_calls=[
                    {
                        "name": "email_send_email",
                        "args": {
                            "recipient_email": "recipient@example.test",
                            "subject": "Meetings",
                            "body": "Tomorrow you have a meeting.",
                        },
                        "id": "call-send-email",
                    }
                ],
            ),
            AIMessage(content="The email was sent."),
        ]
    )
    runtime = build_agent_graph(
        model,
        [sender.tool()],
        audit_log,
        checkpointer=InMemorySaver(),
    )
    output = StringIO()

    final_response = asyncio_run(
        run_turn(
            runtime,
            "Send the email",
            "cli-thread",
            input_func=lambda prompt: "1",
            output=output,
        )
    )

    text = output.getvalue()
    assert "[human] Approve sending this email?" in text
    assert "[human:details] recipient_email: recipient@example.test" in text
    assert "[human:details] subject: Meetings" in text
    assert sender.calls == [
        {
            "recipient_email": "recipient@example.test",
            "subject": "Meetings",
            "body": "Tomorrow you have a meeting.",
        }
    ]
    assert final_response == "The email was sent."


def test_run_turn_requests_follow_up_after_rejected_email(tmp_path: Path) -> None:
    audit_log = create_audit_log(tmp_path)
    sender = FakeEmailSender()
    model = ScriptedChatModel(
        [
            AIMessage(
                content="I will send the email.",
                tool_calls=[
                    {
                        "name": "email_send_email",
                        "args": {
                            "recipient_email": "recipient@example.test",
                            "subject": "Meetings",
                            "body": "Tomorrow you have a meeting.",
                        },
                        "id": "call-rejected-email",
                    }
                ],
            ),
            AIMessage(
                content=(
                    "- The calendar was checked.\n"
                    "- The email was not sent because the user rejected it."
                )
            ),
            AIMessage(content="I will leave the email unsent."),
        ]
    )
    runtime = build_agent_graph(
        model,
        [sender.tool()],
        audit_log,
        checkpointer=InMemorySaver(),
    )
    output = StringIO()
    answers = iter(["2", "Leave it unsent."])

    final_response = asyncio_run(
        run_turn(
            runtime,
            "Send the email",
            "cli-thread",
            input_func=lambda prompt: next(answers),
            output=output,
        )
    )

    text = output.getvalue()
    assert "[tool:cancelled] email_send_email" in text
    assert "[human:context]" in text
    assert "- The calendar was checked." in text
    assert "[human] What should I do next?" in text
    assert sender.calls == []
    assert final_response == "I will leave the email unsent."


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


class FakeEmailSender:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def tool(self) -> StructuredTool:
        return StructuredTool.from_function(
            self.send_email,
            name="email_send_email",
            description="Send an email.",
            metadata={"read_only": False},
        )

    def send_email(self, recipient_email: str, subject: str, body: str) -> str:
        self.calls.append(
            {
                "recipient_email": recipient_email,
                "subject": subject,
                "body": body,
            }
        )
        return "sent"


def create_audit_log(tmp_path: Path) -> AgentAuditLog:
    audit_log = AgentAuditLog(tmp_path / "agent_debug.db")
    audit_log.setup()
    return audit_log


def asyncio_run(awaitable: Any) -> Any:
    import asyncio

    return asyncio.run(awaitable)
