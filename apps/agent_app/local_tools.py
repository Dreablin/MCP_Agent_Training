from collections.abc import Callable, Sequence
from datetime import datetime

from langchain_core.tools import BaseTool, StructuredTool


def build_local_tools() -> list[BaseTool]:
    return [build_current_datetime_tool()]


def combine_agent_tools(mcp_tools: Sequence[BaseTool]) -> list[BaseTool]:
    return [*mcp_tools, *build_local_tools()]


def build_current_datetime_tool(
    now_factory: Callable[[], datetime] | None = None,
) -> BaseTool:
    resolved_now_factory = now_factory or current_local_datetime

    def get_current_datetime() -> dict[str, str]:
        """Return the current local date and time from this computer."""
        return current_datetime_payload(resolved_now_factory())

    return StructuredTool.from_function(
        get_current_datetime,
        name="get_current_datetime",
        description=(
            "Return the current local date and time from this computer. Use this before "
            "resolving relative date/time requests such as tomorrow, today, next week, "
            "or in one hour."
        ),
        metadata={"source": "agent_local", "read_only": True},
    )


def current_local_datetime() -> datetime:
    return datetime.now()


def current_datetime_payload(value: datetime) -> dict[str, str]:
    local_value = value.replace(tzinfo=None)
    return {
        "datetime": local_value.isoformat(timespec="seconds"),
        "date": local_value.date().isoformat(),
        "time": local_value.time().isoformat(timespec="seconds"),
        "weekday": local_value.strftime("%A"),
    }
