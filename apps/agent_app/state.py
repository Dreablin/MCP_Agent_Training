from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

AgentStatus = Literal["running", "waiting_for_human", "completed", "failed"]
HumanDecisionKind = Literal["answer", "choose", "edit", "reject"]


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


class AgentState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    run_id: str
    thread_id: str
    user_input: str
    human_question: HumanQuestion
    human_answer: HumanAnswer
    status: AgentStatus
    final_response: str
    error: str
