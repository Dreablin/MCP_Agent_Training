import json
from typing import Any

import httpx
import pytest
from mcp.server.mcpserver.exceptions import ToolError

from apps.todo_app.models import TaskPriority, TaskStatus
from apps.todo_MCP.config import TodoMCPSettings
from apps.todo_MCP.main import create_runtime
from apps.todo_MCP.server import create_mcp_server
from apps.todo_MCP.tools import (
    cancel_todo_task_via_api,
    complete_todo_task_via_api,
    create_todo_task_via_api,
    list_todo_tasks_via_api,
    validate_pagination,
)


@pytest.mark.anyio
async def test_todo_mcp_server_registers_tools() -> None:
    settings = TodoMCPSettings()
    mcp = create_mcp_server(settings)
    tools = await mcp.list_tools()
    tools_by_name = {tool.name: tool for tool in tools}

    assert mcp.name == "Todo MCP server"
    list_tool = tools_by_name["list_todo_tasks"]
    assert list_tool.title == "List todo tasks"
    assert list_tool.annotations is not None
    assert list_tool.annotations.read_only_hint is True
    assert list_tool.annotations.open_world_hint is False

    create_tool = tools_by_name["create_todo_task"]
    assert create_tool.title == "Create todo task"
    assert create_tool.annotations is not None
    assert create_tool.annotations.read_only_hint is False
    assert create_tool.annotations.destructive_hint is False
    assert create_tool.annotations.idempotent_hint is False
    assert create_tool.annotations.open_world_hint is False

    cancel_tool = tools_by_name["cancel_todo_task"]
    assert cancel_tool.title == "Cancel todo task"
    assert cancel_tool.annotations is not None
    assert cancel_tool.annotations.read_only_hint is False
    assert cancel_tool.annotations.destructive_hint is False
    assert cancel_tool.annotations.idempotent_hint is True
    assert cancel_tool.annotations.open_world_hint is False

    complete_tool = tools_by_name["complete_todo_task"]
    assert complete_tool.title == "Complete todo task"
    assert complete_tool.annotations is not None
    assert complete_tool.annotations.read_only_hint is False
    assert complete_tool.annotations.destructive_hint is False
    assert complete_tool.annotations.idempotent_hint is True
    assert complete_tool.annotations.open_world_hint is False


def test_todo_mcp_runtime_does_not_open_todo_database() -> None:
    settings = TodoMCPSettings(todo_api_port=8999)

    runtime = create_runtime(settings)

    assert runtime.settings is settings
    assert runtime.settings.todo_api_tasks_url == "http://127.0.0.1:8999/api/tasks"
    assert not hasattr(runtime, "engine")


def test_todo_mcp_settings_build_api_url() -> None:
    settings = TodoMCPSettings(
        todo_api_scheme="https",
        todo_api_host="todo.example.test",
        todo_api_port=9443,
        todo_api_tasks_path="/v1/tasks",
    )

    assert settings.todo_api_base_url == "https://todo.example.test:9443"
    assert settings.todo_api_tasks_url == "https://todo.example.test:9443/v1/tasks"


def test_list_todo_tasks_calls_todo_api() -> None:
    requested: list[tuple[str, str, dict[str, str]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append((request.method, request.url.path, dict(request.url.params)))
        return httpx.Response(200, json=[task_payload("task-1", priority="high")])

    tasks = list_todo_tasks_via_api(
        TodoMCPSettings(),
        status=TaskStatus.OPEN,
        priority=TaskPriority.HIGH,
        limit=10,
        offset=2,
        transport=httpx.MockTransport(handler),
    )

    assert requested == [
        (
            "GET",
            "/api/tasks",
            {"limit": "10", "offset": "2", "status": "open", "priority": "high"},
        )
    ]
    assert tasks[0]["id"] == "task-1"
    assert tasks[0]["priority"] == "high"


def test_create_todo_task_calls_todo_api() -> None:
    requested: list[tuple[str, str, dict[str, Any]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append((request.method, request.url.path, json.loads(request.content.decode())))
        return httpx.Response(201, json=task_payload("task-1", title="New task"))

    task = create_todo_task_via_api(
        TodoMCPSettings(),
        title="New task",
        description="Task from MCP.",
        priority=TaskPriority.URGENT,
        transport=httpx.MockTransport(handler),
    )

    assert requested == [
        (
            "POST",
            "/api/tasks",
            {"title": "New task", "description": "Task from MCP.", "priority": "urgent"},
        )
    ]
    assert task["id"] == "task-1"
    assert task["title"] == "New task"


def test_cancel_todo_task_calls_get_then_api_and_preserves_idempotence() -> None:
    requested: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append((request.method, request.url.path))
        if request.method == "GET":
            return httpx.Response(200, json=task_payload("task-1"))
        return httpx.Response(200, json=task_payload("task-1", status="cancelled"))

    cancelled = cancel_todo_task_via_api(
        TodoMCPSettings(),
        task_id="task-1",
        transport=httpx.MockTransport(handler),
    )

    assert requested == [("GET", "/api/tasks/task-1"), ("POST", "/api/tasks/task-1/cancel")]
    assert cancelled["status"] == "cancelled"

    requested.clear()
    already_cancelled = cancel_todo_task_via_api(
        TodoMCPSettings(),
        task_id="task-1",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json=task_payload("task-1", status="cancelled"),
            )
        ),
    )

    assert already_cancelled["status"] == "cancelled"


def test_complete_todo_task_calls_get_then_api() -> None:
    requested: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append((request.method, request.url.path))
        if request.method == "GET":
            return httpx.Response(200, json=task_payload("task-1"))
        return httpx.Response(200, json=task_payload("task-1", status="completed"))

    completed = complete_todo_task_via_api(
        TodoMCPSettings(),
        task_id="task-1",
        transport=httpx.MockTransport(handler),
    )

    assert requested == [("GET", "/api/tasks/task-1"), ("POST", "/api/tasks/task-1/complete")]
    assert completed["status"] == "completed"


def test_todo_mcp_formats_todo_api_errors() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404,
            json={
                "error": {
                    "code": "NOT_FOUND",
                    "message": "Task not found",
                    "details": {"id": "missing"},
                }
            },
        )

    with pytest.raises(ToolError, match=r'NOT_FOUND: Task not found\. details=\{"id": "missing"\}'):
        complete_todo_task_via_api(
            TodoMCPSettings(),
            task_id="missing",
            transport=httpx.MockTransport(handler),
        )


def test_todo_mcp_validates_pagination() -> None:
    with pytest.raises(ValueError, match="limit must be between 1 and 500"):
        validate_pagination(0, 0)
    with pytest.raises(ValueError, match="offset must be greater than or equal to 0"):
        validate_pagination(100, -1)


def task_payload(
    task_id: str,
    *,
    title: str = "Task",
    status: str = "open",
    priority: str = "normal",
) -> dict[str, object]:
    return {
        "id": task_id,
        "title": title,
        "description": "Description",
        "status": status,
        "priority": priority,
        "completed_at": None,
        "created_at": "2026-08-28T15:00:00+00:00",
        "updated_at": "2026-08-28T15:00:00+00:00",
    }
