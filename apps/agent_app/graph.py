import json
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Protocol, cast
from uuid import uuid4

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig, RunnableLambda
from langchain_core.tools import BaseTool
from langgraph.errors import GraphInterrupt
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.types import Command, interrupt

from apps.agent_app.audit import AgentAuditLog
from apps.agent_app.config import AgentAppSettings
from apps.agent_app.policy import PolicyDecision, PolicyEngine, PolicyResult
from apps.agent_app.prompts import messages_for_rejection_follow_up, messages_with_system_prompt
from apps.agent_app.state import AgentState, HumanAnswer, PendingToolPolicy


class ToolBindableChatModel(Protocol):
    def bind_tools(self, tools: Sequence[BaseTool | Any]) -> Any:
        """Return a model/runnable configured for tool calling."""

    def invoke(self, messages: list[AnyMessage]) -> AIMessage:
        """Return a chat response without tool binding."""


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
        try:
            result = self.graph.invoke(state, config)
        except GraphInterrupt:
            raise
        except Exception as exc:
            self.audit_log.fail_run(run_id, resolved_thread_id, exc)
            raise
        return {"thread_id": resolved_thread_id, "run_id": run_id, "state": result}

    async def arun(self, user_input: str, thread_id: str | None = None) -> dict[str, Any]:
        resolved_thread_id = thread_id or str(uuid4())
        run_id = str(uuid4())
        config = {"configurable": {"thread_id": resolved_thread_id}}
        state = initial_state(user_input, resolved_thread_id, run_id)
        self.audit_log.start_run(run_id, resolved_thread_id, user_input)
        try:
            result = await self.graph.ainvoke(state, config)
        except GraphInterrupt:
            raise
        except Exception as exc:
            self.audit_log.fail_run(run_id, resolved_thread_id, exc)
            raise
        return {"thread_id": resolved_thread_id, "run_id": run_id, "state": result}

    def resume(
        self,
        thread_id: str,
        run_id: str,
        answer: HumanAnswer,
    ) -> dict[str, Any]:
        self.ensure_sync_allowed()
        config = {"configurable": {"thread_id": thread_id}}
        self.audit_log.resume(run_id, thread_id, dict(answer))
        try:
            result = self.graph.invoke(Command(resume=answer), config)
        except GraphInterrupt:
            raise
        except Exception as exc:
            self.audit_log.fail_run(run_id, thread_id, exc)
            raise
        return {"thread_id": thread_id, "run_id": run_id, "state": result}

    async def aresume(
        self,
        thread_id: str,
        run_id: str,
        answer: HumanAnswer,
    ) -> dict[str, Any]:
        config = {"configurable": {"thread_id": thread_id}}
        self.audit_log.resume(run_id, thread_id, dict(answer))
        try:
            result = await self.graph.ainvoke(Command(resume=answer), config)
        except GraphInterrupt:
            raise
        except Exception as exc:
            self.audit_log.fail_run(run_id, thread_id, exc)
            raise
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
        "pending_tool_policy": None,
        "approval_outcome": None,
        "rejected_tool_names": [],
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
    policy_engine = PolicyEngine()

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

    def call_rejection_summary(state: AgentState) -> AgentState:
        if not resolved_allow_sync:
            msg = "Use async graph execution for runtimes with async-only tools."
            raise RuntimeError(msg)
        log_node_enter(audit_log, state, "rejection_summary")
        response = model.invoke(messages_for_rejection_follow_up(state["messages"]))
        updates: AgentState = {"messages": [response], "status": "running"}
        log_node_exit(audit_log, state, "rejection_summary", updates)
        return updates

    async def acall_rejection_summary(state: AgentState) -> AgentState:
        log_node_enter(audit_log, state, "rejection_summary")
        summary_model: Any = model
        if hasattr(summary_model, "ainvoke"):
            response = cast(
                AIMessage,
                await summary_model.ainvoke(messages_for_rejection_follow_up(state["messages"])),
            )
        else:
            response = cast(
                AIMessage,
                summary_model.invoke(messages_for_rejection_follow_up(state["messages"])),
            )
        updates: AgentState = {"messages": [response], "status": "running"}
        log_node_exit(audit_log, state, "rejection_summary", updates)
        return updates

    def policy_engine_node(state: AgentState) -> AgentState:
        log_node_enter(audit_log, state, "policy_engine")
        latest = latest_message_from_state(state)
        if not isinstance(latest, AIMessage) or not latest.tool_calls:
            updates: AgentState = cleared_policy_updates()
            log_node_exit(audit_log, state, "policy_engine", updates)
            return updates

        violation = state_changing_batch_violation(latest.tool_calls, tools_by_name)
        if violation is not None:
            audit_log.event(
                state["run_id"],
                state["thread_id"],
                "tool_policy_violation",
                node_name="policy_engine",
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
                **cleared_policy_updates(),
            }
            log_node_exit(audit_log, state, "policy_engine", updates)
            return updates

        evaluated_calls = [
            (cast(dict[str, Any], tool_call), policy_engine.evaluate(tool_call, state))
            for tool_call in latest.tool_calls
        ]
        for tool_call, result in evaluated_calls:
            audit_policy_evaluation(audit_log, state, tool_call, result)

        denied_calls = [
            (tool_call, result)
            for tool_call, result in evaluated_calls
            if result.decision is PolicyDecision.DENY
        ]
        if denied_calls:
            updates = {
                "messages": [
                    ToolMessage(
                        content=json.dumps(
                            {
                                "outcome": "denied_by_policy",
                                "status": "denied",
                                "executed": False,
                                "retryable": False,
                                "reason": result.reason,
                            },
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                        name=str(tool_call.get("name", "")),
                        tool_call_id=str(tool_call.get("id", "")),
                        status="success",
                    )
                    for tool_call, result in denied_calls
                ],
                **cleared_policy_updates(),
            }
            log_node_exit(audit_log, state, "policy_engine", updates)
            return updates

        confirmation = next(
            (
                (tool_call, result)
                for tool_call, result in evaluated_calls
                if result.decision is PolicyDecision.CONFIRM
            ),
            None,
        )
        if confirmation is not None:
            tool_call, result = confirmation
            updates = {
                "pending_tool_policy": pending_tool_policy(tool_call, result),
                "approval_outcome": None,
                "status": "running",
            }
            log_node_exit(audit_log, state, "policy_engine", updates)
            return updates

        updates = cleared_policy_updates()
        log_node_exit(audit_log, state, "policy_engine", updates)
        return updates

    tool_node = ToolNode(
        tools,
        handle_tool_errors=format_tool_error_for_llm,
        wrap_tool_call=make_audit_tool_wrapper(audit_log),
        awrap_tool_call=make_async_audit_tool_wrapper(audit_log),
    )

    def ask_human_node(state: AgentState) -> AgentState:
        import time

        log_node_enter(audit_log, state, "ask_human")
        tool_call = latest_human_tool_call(state, tools_by_name)
        if tool_call is None:
            updates: AgentState = {"status": "running"}
            log_node_exit(audit_log, state, "ask_human", updates)
            return updates

        started = time.perf_counter()
        result = execute_human_tool_call(audit_log, state, tool_call)
        duration_ms = round((time.perf_counter() - started) * 1000)
        audit_tool_result(audit_log, state, tool_call, result, duration_ms)
        updates = {"messages": [result], "status": "running"}
        log_node_exit(audit_log, state, "ask_human", updates)
        return updates

    def approval_node(state: AgentState) -> AgentState:
        log_node_enter(audit_log, state, "approval")
        pending = state.get("pending_tool_policy")
        if not isinstance(pending, dict) or pending.get("decision") != PolicyDecision.CONFIRM.value:
            updates: AgentState = {"status": "running"}
            log_node_exit(audit_log, state, "approval", updates)
            return updates

        tool_call = latest_tool_call_by_id(state, str(pending.get("tool_call_id", "")))
        if tool_call is None:
            updates = {
                "messages": [
                    ToolMessage(
                        content="Approval could not find the planned tool call.",
                        name=str(pending.get("tool_name", "")),
                        tool_call_id=str(pending.get("tool_call_id", "")),
                        status="error",
                    )
                ],
                "pending_tool_policy": None,
                "approval_outcome": "rejected",
                "status": "running",
            }
            log_node_exit(audit_log, state, "approval", updates)
            return updates

        payload = pending.get("display_payload")
        approval_payload = dict(payload) if isinstance(payload, dict) else {}
        try:
            answer = interrupt(approval_payload)
        except GraphInterrupt as exc:
            audit_log.event(
                state["run_id"],
                state["thread_id"],
                "approval_requested",
                node_name="approval",
                payload={
                    "tool_name": tool_call["name"],
                    "tool_call_id": tool_call.get("id", ""),
                    "rule_id": pending.get("rule_id", ""),
                },
            )
            audit_human_interrupt(audit_log, state, approval_payload, exc)
            raise

        answer_payload = human_answer_payload(answer)
        audit_log.resume(state["run_id"], state["thread_id"], answer_payload)
        if approval_is_approved(answer_payload):
            audit_log.event(
                state["run_id"],
                state["thread_id"],
                "approval_approved",
                node_name="approval",
                payload={"tool_name": tool_call["name"], "tool_call_id": tool_call.get("id", "")},
            )
            updates = {
                "pending_tool_policy": None,
                "approval_outcome": "approved",
                "status": "running",
            }
            log_node_exit(audit_log, state, "approval", updates)
            return updates

        audit_log.event(
            state["run_id"],
            state["thread_id"],
            "approval_rejected",
            node_name="approval",
            payload={"tool_name": tool_call["name"], "tool_call_id": tool_call.get("id", "")},
        )
        result = ToolMessage(
            content=json.dumps(
                {
                    "outcome": "rejected_by_user",
                    "status": "cancelled",
                    "executed": False,
                    "retryable": False,
                    "reason": "The user did not approve this action.",
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            name=str(tool_call["name"]),
            tool_call_id=str(tool_call.get("id", "")),
            status="success",
        )
        updates = {
            "messages": [result],
            "pending_tool_policy": None,
            "approval_outcome": "rejected",
            "rejected_tool_names": rejected_tool_names_after(state, str(tool_call["name"])),
            "status": "running",
        }
        log_node_exit(audit_log, state, "approval", updates)
        return updates

    def rejection_follow_up_node(state: AgentState) -> AgentState:
        log_node_enter(audit_log, state, "rejection_follow_up")
        payload = rejection_follow_up_payload(state)
        try:
            answer = interrupt(payload)
        except GraphInterrupt as exc:
            audit_log.event(
                state["run_id"],
                state["thread_id"],
                "rejection_follow_up_requested",
                node_name="rejection_follow_up",
                payload={"summary": payload["summary"]},
            )
            audit_human_interrupt(audit_log, state, payload, exc)
            raise

        answer_payload = human_answer_payload(answer)
        audit_log.resume(state["run_id"], state["thread_id"], answer_payload)
        audit_log.event(
            state["run_id"],
            state["thread_id"],
            "rejection_follow_up_received",
            node_name="rejection_follow_up",
            payload=answer_payload,
        )
        updates: AgentState = {
            "messages": [HumanMessage(content=rejection_follow_up_message(answer_payload))],
            "approval_outcome": None,
            "status": "running",
        }
        log_node_exit(audit_log, state, "rejection_follow_up", updates)
        return updates

    def human_gate(state: AgentState) -> AgentState:
        log_node_enter(audit_log, state, "human_gate")
        updates: AgentState = {"status": "running"}
        log_node_exit(audit_log, state, "human_gate", updates)
        return updates

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
    builder.add_node(
        "rejection_summary",
        RunnableLambda(call_rejection_summary, afunc=acall_rejection_summary),
    )
    builder.add_node("policy_engine", policy_engine_node)
    builder.add_node("tools", tool_node)
    builder.add_node("ask_human", ask_human_node)
    builder.add_node("approval", approval_node)
    builder.add_node("rejection_follow_up", rejection_follow_up_node)
    builder.add_node("human_gate", human_gate)
    builder.add_node("finalize", finalize)

    builder.add_edge(START, "ensure_metadata")
    builder.add_edge("ensure_metadata", "llm")
    builder.add_conditional_edges(
        "llm",
        route_after_llm,
        {
            "tools": "policy_engine",
            "final": "finalize",
        },
    )
    builder.add_conditional_edges(
        "policy_engine",
        route_after_tool_policy,
        {
            "tools": "tools",
            "ask_human": "ask_human",
            "approval": "approval",
            "llm": "llm",
        },
    )
    builder.add_edge("tools", "human_gate")
    builder.add_edge("ask_human", "human_gate")
    builder.add_conditional_edges(
        "approval",
        route_after_approval,
        {
            "tools": "tools",
            "rejection_summary": "rejection_summary",
            "llm": "llm",
        },
    )
    builder.add_edge("rejection_summary", "rejection_follow_up")
    builder.add_edge("rejection_follow_up", "llm")
    builder.add_edge("human_gate", "llm")
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
        if pending_confirmation_matches_latest_tool_call(state):
            return "approval"
        if latest_human_tool_call(state, {}) is not None:
            return "ask_human"
        return "tools"
    return "llm"


def route_after_approval(state: AgentState) -> str:
    if state.get("approval_outcome") == "approved":
        return "tools"
    if state.get("approval_outcome") == "rejected":
        return "rejection_summary"
    return "llm"


def latest_message_from_state(state: AgentState) -> AnyMessage | None:
    messages = state.get("messages", [])
    if not messages:
        return None
    return messages[-1]


def latest_tool_call_by_id(state: AgentState, tool_call_id: str) -> dict[str, Any] | None:
    latest = latest_message_from_state(state)
    if not isinstance(latest, AIMessage) or not latest.tool_calls:
        return None
    for tool_call in latest.tool_calls:
        if str(tool_call.get("id", "")) == tool_call_id:
            return cast(dict[str, Any], tool_call)
    return None


def pending_confirmation_matches_latest_tool_call(state: AgentState) -> bool:
    pending = state.get("pending_tool_policy")
    if not isinstance(pending, dict) or pending.get("decision") != PolicyDecision.CONFIRM.value:
        return False
    tool_call_id = str(pending.get("tool_call_id", ""))
    return latest_tool_call_by_id(state, tool_call_id) is not None


def cleared_policy_updates() -> AgentState:
    return {
        "pending_tool_policy": None,
        "approval_outcome": None,
        "status": "running",
    }


def rejected_tool_names_after(state: AgentState, tool_name: str) -> list[str]:
    rejected = list(state.get("rejected_tool_names", []))
    if tool_name not in rejected:
        rejected.append(tool_name)
    return rejected


def rejection_follow_up_payload(state: AgentState) -> dict[str, str]:
    latest = latest_message_from_state(state)
    summary = str(latest.content) if isinstance(latest, AIMessage) else ""
    if not summary:
        summary = "The requested action was not performed because it was rejected."
    return {
        "kind": "rejection_follow_up",
        "summary": summary,
        "question": "What should I do next?",
    }


def rejection_follow_up_message(answer: dict[str, Any]) -> str:
    value = answer.get("value")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return "The human did not provide further instructions."


def pending_tool_policy(
    tool_call: dict[str, Any],
    result: PolicyResult,
) -> PendingToolPolicy:
    return {
        "decision": result.decision.value,
        "rule_id": result.rule_id,
        "reason": result.reason,
        "tool_call_id": str(tool_call.get("id", "")),
        "tool_name": str(tool_call.get("name", "")),
        "display_payload": result.display_payload,
    }


def approval_is_approved(answer: dict[str, Any]) -> bool:
    kind = str(answer.get("kind", "")).lower()
    value = str(answer.get("value", "")).strip().lower()
    return kind == "approve" or value in {"1", "approve", "approved", "yes", "y", "да"}


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
        except GraphInterrupt:
            raise
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
        except GraphInterrupt:
            raise
        except Exception as exc:
            duration_ms = round((time.perf_counter() - started) * 1000)
            audit_tool_exception(audit_log, state, tool_call, exc, duration_ms)
            raise
        duration_ms = round((time.perf_counter() - started) * 1000)
        audit_tool_result(audit_log, state, tool_call, result, duration_ms)
        return cast(ToolMessage | Command[Any], result)

    return awrap_tool_call


def execute_human_tool_call(
    audit_log: AgentAuditLog,
    state: AgentState,
    tool_call: dict[str, Any],
) -> ToolMessage:
    payload = human_interrupt_payload(tool_call)
    try:
        answer = interrupt(payload)
    except GraphInterrupt as exc:
        audit_human_interrupt(audit_log, state, payload, exc)
        raise

    answer_payload = human_answer_payload(answer)
    audit_log.resume(state["run_id"], state["thread_id"], answer_payload)
    return ToolMessage(
        content=json.dumps(answer_payload, ensure_ascii=False, sort_keys=True),
        name=str(tool_call.get("name", "ask_human")),
        tool_call_id=str(tool_call.get("id", "")),
        status="success",
    )


def human_interrupt_payload(tool_call: dict[str, Any]) -> dict[str, Any]:
    args = tool_call.get("args", {})
    payload = dict(args) if isinstance(args, dict) else {"question": str(args)}
    if not payload.get("question"):
        payload["question"] = "The agent needs your input."
    payload.update(
        {
            "tool_name": str(tool_call.get("name", "ask_human")),
            "tool_call_id": str(tool_call.get("id", "")),
        }
    )
    return payload


def human_answer_payload(answer: Any) -> dict[str, Any]:
    if isinstance(answer, dict):
        return dict(answer)
    return {"kind": "answer", "value": str(answer)}


def audit_human_interrupt(
    audit_log: AgentAuditLog,
    state: AgentState,
    payload: dict[str, Any],
    exc: GraphInterrupt,
) -> None:
    question: dict[str, Any] = dict(payload)
    interrupt_values = interrupt_values_from_exception(exc)
    if interrupt_values:
        question["interrupts"] = interrupt_values
    audit_log.interrupt(state["run_id"], state["thread_id"], question)


def audit_policy_evaluation(
    audit_log: AgentAuditLog,
    state: AgentState,
    tool_call: dict[str, Any],
    result: PolicyResult,
) -> None:
    audit_log.event(
        state["run_id"],
        state["thread_id"],
        "policy_evaluated",
        node_name="policy_engine",
        payload={
            "tool_name": tool_call.get("name", ""),
            "tool_call_id": tool_call.get("id", ""),
            "decision": result.decision.value,
            "rule_id": result.rule_id,
            "reason": result.reason,
        },
    )


def tool_call_requires_human(
    tool_call: Any,
    tools_by_name: dict[str, BaseTool | Any],
) -> bool:
    tool_name = str(tool_call.get("name", ""))
    tool = tools_by_name.get(tool_name)
    metadata = getattr(tool, "metadata", None)
    if isinstance(metadata, dict) and metadata.get("requires_human"):
        return True
    return tool_name == "ask_human"


def latest_human_tool_call(
    state: AgentState,
    tools_by_name: dict[str, BaseTool | Any],
) -> dict[str, Any] | None:
    latest = latest_message_from_state(state)
    if not isinstance(latest, AIMessage) or not latest.tool_calls:
        return None
    for tool_call in latest.tool_calls:
        if tool_call_requires_human(tool_call, tools_by_name):
            return cast(dict[str, Any], tool_call)
    return None


def interrupt_values_from_exception(exc: GraphInterrupt) -> list[dict[str, Any]]:
    interrupts = exc.args[0] if exc.args else ()
    values: list[dict[str, Any]] = []
    if not isinstance(interrupts, Sequence):
        return values
    for item in interrupts:
        values.append(
            {
                "id": str(getattr(item, "id", "")),
                "value": getattr(item, "value", None),
            }
        )
    return values


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


@asynccontextmanager
async def build_async_sqlite_checkpointer(
    checkpoint_db_path: Path,
) -> AsyncIterator[Any]:
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    checkpoint_db_path.parent.mkdir(parents=True, exist_ok=True)
    async with AsyncSqliteSaver.from_conn_string(str(checkpoint_db_path)) as checkpointer:
        await checkpointer.setup()
        yield checkpointer


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
    resolved_settings = settings or AgentAppSettings()
    resolved_settings.ensure_data_dir()
    audit_log = AgentAuditLog(resolved_settings.audit_db_path)
    audit_log.setup()
    async with build_async_sqlite_checkpointer(
        resolved_settings.checkpoint_db_path
    ) as checkpointer:
        yield build_agent_graph(
            model,
            tools,
            audit_log,
            checkpointer=checkpointer,
            allow_sync=False,
        )
