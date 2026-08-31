from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

AgentStatus = Literal["running", "waiting_for_human", "completed", "failed"]
HumanDecisionKind = Literal["answer", "approve", "choose", "edit", "reject"]
PolicyDecisionValue = Literal["allow", "confirm", "deny"]


class HumanQuestion(TypedDict, total=False):
    question: str
    reason: str
    candidates: list[dict[str, Any]]
    conflicts: list[dict[str, Any]]


class HumanAnswer(TypedDict, total=False):
    kind: HumanDecisionKind
    value: str
    selected_id: str
    edited_args: dict[str, Any]


class PendingToolPolicy(TypedDict, total=False):
    decision: PolicyDecisionValue
    rule_id: str
    reason: str
    tool_call_id: str
    tool_name: str
    display_payload: dict[str, Any]


class AgentState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    run_id: str
    thread_id: str
    user_input: str
    human_question: HumanQuestion
    human_answer: HumanAnswer
    pending_tool_policy: PendingToolPolicy | None
    approval_outcome: Literal["approved", "rejected"] | None
    rejected_tool_names: list[str]
    status: AgentStatus
    final_response: str
    error: str
