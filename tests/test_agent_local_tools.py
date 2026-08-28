from datetime import datetime

from langchain_core.tools import StructuredTool

from apps.agent_app.local_tools import (
    build_current_datetime_tool,
    build_local_tools,
    combine_agent_tools,
)


def test_current_datetime_tool_returns_local_time_payload() -> None:
    tool = build_current_datetime_tool(lambda: datetime(2026, 8, 28, 14, 30, 5))

    result = tool.invoke({})

    assert result["date"] == "2026-08-28"
    assert result["time"] == "14:30:05"
    assert result["weekday"] == "Friday"
    assert result["datetime"] == "2026-08-28T14:30:05"
    assert set(result) == {"datetime", "date", "time", "weekday"}


def test_local_tools_include_current_datetime_tool() -> None:
    tools = build_local_tools()

    assert [tool.name for tool in tools] == ["get_current_datetime", "ask_human"]
    assert "relative date/time requests" in tools[0].description
    assert "timezone" not in tools[0].description.lower()
    assert tools[0].metadata == {"source": "agent_local", "read_only": True}
    assert "clarification" in tools[1].description
    assert tools[1].metadata == {
        "source": "agent_local",
        "read_only": False,
        "requires_human": True,
        "batchable": False,
    }


def test_combine_agent_tools_appends_local_tools() -> None:
    def fake_mcp_tool() -> str:
        return "ok"

    mcp_tool = StructuredTool.from_function(
        fake_mcp_tool,
        name="fake_mcp_tool",
        description="Fake MCP tool.",
    )

    tools = combine_agent_tools([mcp_tool])

    assert [tool.name for tool in tools] == [
        "fake_mcp_tool",
        "get_current_datetime",
        "ask_human",
    ]
