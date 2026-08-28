import argparse
import asyncio
import json
import sys
import traceback
from collections.abc import Callable, Sequence
from typing import Any, TextIO
from uuid import uuid4

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

from apps.agent_app.config import AgentAppSettings
from apps.agent_app.graph import AgentGraphRuntime, create_async_runtime, initial_state
from apps.agent_app.llm import create_chat_model
from apps.agent_app.local_tools import combine_agent_tools
from apps.agent_app.mcp_registry import PersistentMCPToolRegistry

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
            await run_turn(runtime, user_input, thread_id, output=output)
        except Exception as exc:
            print_error(exc, debug=debug, output=output)


async def run_turn(
    runtime: AgentGraphRuntime,
    user_input: str,
    thread_id: str,
    *,
    output: TextIO,
) -> str:
    run_id = str(uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    state = initial_state(user_input, thread_id, run_id)
    runtime.audit_log.start_run(run_id, thread_id, user_input)
    final_response = ""

    output.write("[llm] thinking...\n")
    async for update in runtime.graph.astream(state, config, stream_mode="updates"):
        rendered = render_update(update, output)
        if rendered:
            final_response = rendered

    return final_response


def render_update(update: dict[str, Any], output: TextIO) -> str | None:
    final_response: str | None = None
    for node_name, node_update in update.items():
        if not isinstance(node_update, dict):
            continue
        if node_name == "llm":
            render_llm_update(node_update, output)
        elif node_name == "tools":
            render_tool_update(node_update, output)
        elif node_name == "finalize":
            final_response = str(node_update.get("final_response", ""))
            output.write("[final]\n")
            if final_response:
                output.write(f"{final_response}\n")
    return final_response


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
        prefix = "[tool:error]" if status == "error" else "[tool:ok]"
        name = message.name or message.tool_call_id
        content = text_content(message)
        if content:
            output.write(f"{prefix} {name} {content}\n")
        else:
            output.write(f"{prefix} {name}\n")


def messages_from_update(update: dict[str, Any]) -> list[BaseMessage]:
    messages = update.get("messages", [])
    if not isinstance(messages, list):
        return []
    return [message for message in messages if isinstance(message, BaseMessage)]


def text_content(message: BaseMessage) -> str:
    content = message.content
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
