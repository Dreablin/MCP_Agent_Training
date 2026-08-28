from typing import Any, TypedDict

from langchain_core.tools import BaseTool, StructuredTool
from langgraph.types import interrupt


class HumanOption(TypedDict, total=False):
    id: str
    label: str
    description: str


class AskHumanPayload(TypedDict, total=False):
    question: str
    reason: str
    options: list[HumanOption]


async def ask_human(
    question: str,
    reason: str = "",
    options: list[HumanOption] | None = None,
) -> dict[str, Any]:
    """Ask the human for clarification and pause the graph until they answer."""
    payload: AskHumanPayload = {"question": question}
    if reason:
        payload["reason"] = reason
    if options:
        payload["options"] = options

    answer = interrupt(payload)
    if isinstance(answer, dict):
        return answer
    return {"kind": "answer", "value": str(answer)}


def build_ask_human_tool() -> BaseTool:
    return StructuredTool.from_function(
        coroutine=ask_human,
        name="ask_human",
        description=(
            "Ask the human for clarification when the next correct action is ambiguous, "
            "missing required information, risky, or unrecoverable without a decision. "
            "Calling this tool pauses the graph until the human answers."
        ),
        metadata={
            "source": "agent_local",
            "read_only": False,
            "requires_human": True,
            "batchable": False,
        },
    )
