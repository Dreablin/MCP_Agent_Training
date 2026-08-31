from __future__ import annotations

import argparse
import asyncio
import json
import sys
import traceback
from collections.abc import Callable, Sequence
from typing import Any, TextIO
from uuid import uuid4

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langgraph.types import Command, Interrupt

from apps.agent_app.config import AgentAppSettings
from apps.agent_app.graph import AgentGraphRuntime, create_async_runtime, initial_state
from apps.agent_app.llm import create_chat_model
from apps.agent_app.local_tools import combine_agent_tools
from apps.agent_app.mcp_registry import PersistentMCPToolRegistry
from apps.agent_app.state import AgentState, HumanAnswer

EXIT_COMMANDS = {"exit", "quit", ":q"}


def main(argv: Sequence[str] | None = None) -> int:
    configure_stdio()
    args = parse_args(argv)
    try:
        asyncio.run(async_main(args))
    except KeyboardInterrupt:
        print("\nBye.")
        return 130
    except Exception as exc:
        print_error(exc, debug=args.debug)
        return 1
    return 0


async def async_main(args: argparse.Namespace) -> None:
    settings = AgentAppSettings()
    model = create_chat_model(settings)
    thread_id = args.thread_id or create_cli_thread_id()

    print("Agent CLI")
    print(f"Provider: {settings.llm_provider}")
    print(f"Model: {settings.llm_model}")
    print(f"Thread: {thread_id}")
    print("Type exit or quit to stop.")

    async with (
        PersistentMCPToolRegistry(settings) as registry,
        create_async_runtime(model, combine_agent_tools(registry.tools), settings) as runtime,
    ):
        await interactive_loop(
            runtime,
            thread_id,
            input_func=input,
            output=sys.stdout,
            debug=args.debug,
        )


async def interactive_loop(
    runtime: AgentGraphRuntime,
    thread_id: str,
    *,
    input_func: Callable[[str], str],
    output: TextIO,
    debug: bool = False,
) -> None:
    while True:
        try:
            user_input = input_func("\n> ").strip()
        except EOFError:
            output.write("\n")
            return

        if not user_input:
            continue
        if user_input.lower() in EXIT_COMMANDS:
            output.write("Bye.\n")
            return
        if user_input == ":thread":
            output.write(f"{thread_id}\n")
            continue
        if user_input == ":help":
            output.write("Commands: :help, :thread, exit, quit\n")
            continue

        try:
            await run_turn(runtime, user_input, thread_id, input_func=input_func, output=output)
        except Exception as exc:
            print_error(exc, debug=debug, output=output)


async def run_turn(
    runtime: AgentGraphRuntime,
    user_input: str,
    thread_id: str,
    *,
    input_func: Callable[[str], str] = input,
    output: TextIO,
) -> str:
    run_id = str(uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    state = initial_state(user_input, thread_id, run_id)
    runtime.audit_log.start_run(run_id, thread_id, user_input)
    final_response = ""
    next_input: AgentStateInput = state

    output.write("[llm] thinking...\n")
    try:
        while True:
            interrupted = False
            async for update in runtime.graph.astream(next_input, config, stream_mode="updates"):
                interrupt_payload = interrupt_from_update(update)
                if interrupt_payload is not None:
                    answer = prompt_for_human_answer(interrupt_payload, input_func, output)
                    runtime.audit_log.resume(run_id, thread_id, dict(answer))
                    next_input = Command(resume=answer)
                    output.write("[llm] resuming...\n")
                    interrupted = True
                    break

                rendered = render_update(update, output)
                if rendered:
                    final_response = rendered
            if not interrupted:
                return final_response
    except Exception as exc:
        runtime.audit_log.fail_run(run_id, thread_id, exc)
        raise


AgentStateInput = AgentState | Command[Any]


def render_update(update: dict[str, Any], output: TextIO) -> str | None:
    final_response: str | None = None
    for node_name, node_update in update.items():
        if not isinstance(node_update, dict):
            continue
        if node_name == "llm":
            render_llm_update(node_update, output)
        elif node_name in {"tools", "ask_human", "approval"}:
            render_tool_update(node_update, output)
        elif node_name == "finalize":
            final_response = str(node_update.get("final_response", ""))
            output.write("[final]\n")
            if final_response:
                output.write(f"{final_response}\n")
    return final_response


def interrupt_from_update(update: dict[str, Any]) -> dict[str, Any] | None:
    raw_interrupts = update.get("__interrupt__")
    if raw_interrupts is None:
        return None
    if isinstance(raw_interrupts, (list, tuple)) and raw_interrupts:
        return interrupt_to_payload(raw_interrupts[0])
    return interrupt_to_payload(raw_interrupts)


def interrupt_to_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, Interrupt):
        payload = value.value
        interrupt_id = value.id
    else:
        payload = value
        interrupt_id = ""
    result = dict(payload) if isinstance(payload, dict) else {"question": str(payload)}
    if interrupt_id:
        result["interrupt_id"] = interrupt_id
    return result


def prompt_for_human_answer(
    payload: dict[str, Any],
    input_func: Callable[[str], str],
    output: TextIO,
) -> HumanAnswer:
    render_human_summary(payload.get("summary"), output)
    question = str(payload.get("question") or "The agent needs your input.")
    output.write(f"[human] {question}\n")
    reason = payload.get("reason")
    if reason:
        output.write(f"[human:reason] {reason}\n")
    render_human_details(payload.get("details"), output)
    render_human_options(payload.get("options"), output)
    if payload.get("kind") == "tool_approval":
        while True:
            value = input_func("human> ").strip()
            answer = approval_answer(value)
            if answer is not None:
                return answer
            output.write("[human:error] Choose 1 to approve or 2 to cancel.\n")
    value = input_func("human> ").strip()
    return {"kind": "answer", "value": value}


def approval_answer(value: str) -> HumanAnswer | None:
    normalized = value.strip().lower()
    if normalized in {"1", "approve", "approved", "yes", "y", "да"}:
        return {"kind": "approve", "value": value}
    if normalized in {"2", "cancel", "reject", "no", "n", "нет", "отмена"} or normalized.startswith(
        ("нет,", "не отправляй")
    ):
        return {"kind": "reject", "value": value}
    return None


def render_human_summary(summary: Any, output: TextIO) -> None:
    if not summary:
        return
    output.write("[human:context]\n")
    output.write(f"{text_content_value(summary)}\n")


def render_human_details(details: Any, output: TextIO) -> None:
    if not isinstance(details, dict):
        return
    for key, value in details.items():
        output.write(f"[human:details] {key}: {text_content_value(value)}\n")


def render_human_options(options: Any, output: TextIO) -> None:
    if not isinstance(options, list):
        return
    for index, option in enumerate(options, start=1):
        if not isinstance(option, dict):
            continue
        label = str(option.get("label") or option.get("id") or f"Option {index}")
        description = option.get("description")
        if description:
            output.write(f"[human:option] {index}. {label} - {description}\n")
        else:
            output.write(f"[human:option] {index}. {label}\n")


def render_llm_update(update: dict[str, Any], output: TextIO) -> None:
    for message in messages_from_update(update):
        if not isinstance(message, AIMessage):
            continue
        if message.tool_calls:
            content = text_content(message)
            if content:
                output.write(f"[llm] {content}\n")
            for tool_call in message.tool_calls:
                name = str(tool_call.get("name", "unknown_tool"))
                args = tool_call.get("args", {})
                output.write(f"[tool] {name} {format_json(args)}\n")


def render_tool_update(update: dict[str, Any], output: TextIO) -> None:
    for message in messages_from_update(update):
        if not isinstance(message, ToolMessage):
            continue
        status = message.status or "success"
        outcome = tool_message_outcome(message)
        if outcome == "rejected_by_user":
            prefix = "[tool:cancelled]"
        elif outcome == "denied_by_policy":
            prefix = "[tool:denied]"
        else:
            prefix = "[tool:error]" if status == "error" else "[tool:ok]"
        name = message.name or message.tool_call_id
        content = text_content(message)
        if content:
            output.write(f"{prefix} {name} {content}\n")
        else:
            output.write(f"{prefix} {name}\n")


def tool_message_outcome(message: ToolMessage) -> str | None:
    content = message.content
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except json.JSONDecodeError:
            return None
    if not isinstance(content, dict):
        return None
    outcome = content.get("outcome")
    return outcome if isinstance(outcome, str) else None


def messages_from_update(update: dict[str, Any]) -> list[BaseMessage]:
    messages = update.get("messages", [])
    if not isinstance(messages, list):
        return []
    return [message for message in messages if isinstance(message, BaseMessage)]


def text_content(message: BaseMessage) -> str:
    return text_content_value(message.content)


def text_content_value(content: Any) -> str:
    if isinstance(content, str):
        return content
    return format_json(content)


def format_json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return str(value)


def create_cli_thread_id() -> str:
    return f"cli-{uuid4().hex[:12]}"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the local MCP agent CLI.")
    parser.add_argument("--thread-id", help="Reuse a specific LangGraph thread id.")
    parser.add_argument("--debug", action="store_true", help="Print full tracebacks.")
    return parser.parse_args(argv)


def configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def print_error(exc: BaseException, *, debug: bool, output: TextIO | None = None) -> None:
    resolved_output = output or sys.stderr
    if debug:
        traceback.print_exception(exc, file=resolved_output)
        return
    for message in exception_messages(exc):
        print(f"Error: {message}", file=resolved_output)


def exception_messages(exc: BaseException) -> list[str]:
    if isinstance(exc, BaseExceptionGroup):
        messages: list[str] = []
        for nested in exc.exceptions:
            messages.extend(exception_messages(nested))
        return unique_messages(messages)
    message = str(exc)
    if message:
        return [f"{type(exc).__name__}: {message}"]
    return [type(exc).__name__]


def unique_messages(messages: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for message in messages:
        if message in seen:
            continue
        seen.add(message)
        unique.append(message)
    return unique


if __name__ == "__main__":
    raise SystemExit(main())
