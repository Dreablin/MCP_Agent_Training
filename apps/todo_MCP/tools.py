import json
from collections.abc import Callable
from datetime import datetime
from typing import Any, TypedDict

import httpx
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import ValidationError

from apps.todo_app.models import TaskPriority, TaskStatus
from apps.todo_app.schemas import TaskRead
from apps.todo_MCP.config import TodoMCPSettings


class TodoTaskInfo(TypedDict):
    id: str
    title: str
    description: str
    status: str
    priority: str
    completed_at: str | None
    created_at: str
    updated_at: str


def register_tools(mcp: MCPServer, settings: TodoMCPSettings) -> None:
    """Register Todo MCP tools backed by the Todo App HTTP API."""
    mcp.add_tool(
        list_todo_tasks_tool(settings),
        name="list_todo_tasks",
        title="List todo tasks",
        annotations=ToolAnnotations(
            read_only_hint=True,
            open_world_hint=False,
        ),
    )
    mcp.add_tool(
        create_todo_task_tool(settings),
        name="create_todo_task",
        title="Create todo task",
        annotations=ToolAnnotations(
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=False,
            open_world_hint=False,
        ),
    )
    mcp.add_tool(
        cancel_todo_task_tool(settings),
        name="cancel_todo_task",
        title="Cancel todo task",
        annotations=ToolAnnotations(
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        ),
    )
    mcp.add_tool(
        complete_todo_task_tool(settings),
        name="complete_todo_task",
        title="Complete todo task",
        annotations=ToolAnnotations(
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        ),
    )


def list_todo_tasks_tool(settings: TodoMCPSettings) -> Callable[..., list[TodoTaskInfo]]:
    def list_todo_tasks(
        status: TaskStatus | None = None,
        priority: TaskPriority | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[TodoTaskInfo]:
        """List todo tasks, optionally filtered by status and priority."""
        return list_todo_tasks_via_api(
            settings,
            status=status,
            priority=priority,
            limit=limit,
            offset=offset,
        )

    return list_todo_tasks


def create_todo_task_tool(settings: TodoMCPSettings) -> Callable[..., TodoTaskInfo]:
    def create_todo_task(
        title: str,
        description: str = "",
        priority: TaskPriority = TaskPriority.NORMAL,
    ) -> TodoTaskInfo:
        """Create a new todo task through the Todo App API."""
        return create_todo_task_via_api(
            settings,
            title=title,
            description=description,
            priority=priority,
        )

    return create_todo_task


def cancel_todo_task_tool(settings: TodoMCPSettings) -> Callable[[str], TodoTaskInfo]:
    def cancel_todo_task(task_id: str) -> TodoTaskInfo:
        """Cancel an existing todo task by ID through the Todo App API."""
        return cancel_todo_task_via_api(settings, task_id=task_id)

    return cancel_todo_task


def complete_todo_task_tool(settings: TodoMCPSettings) -> Callable[[str], TodoTaskInfo]:
    def complete_todo_task(task_id: str) -> TodoTaskInfo:
        """Complete an existing todo task by ID through the Todo App API."""
        return complete_todo_task_via_api(settings, task_id=task_id)

    return complete_todo_task


def list_todo_tasks_via_api(
    settings: TodoMCPSettings,
    *,
    status: TaskStatus | None = None,
    priority: TaskPriority | None = None,
    limit: int = 100,
    offset: int = 0,
    transport: httpx.BaseTransport | None = None,
) -> list[TodoTaskInfo]:
    validate_pagination(limit, offset)
    params: dict[str, str | int] = {"limit": limit, "offset": offset}
    if status is not None:
        params["status"] = status.value
    if priority is not None:
        params["priority"] = priority.value

    payload = request_todo_api(
        settings,
        "GET",
        settings.todo_api_tasks_url,
        params=params,
        transport=transport,
    )
    if not isinstance(payload, list):
        msg = "Todo API tasks response must be a list."
        raise ValueError(msg)
    return [parse_todo_task_response(item) for item in payload]


def get_todo_task_via_api(
    settings: TodoMCPSettings,
    task_id: str,
    *,
    transport: httpx.BaseTransport | None = None,
) -> TodoTaskInfo:
    payload = request_todo_api(
        settings,
        "GET",
        f"{settings.todo_api_tasks_url}/{task_id}",
        transport=transport,
    )
    return parse_todo_task_response(payload)


def create_todo_task_via_api(
    settings: TodoMCPSettings,
    *,
    title: str,
    description: str = "",
    priority: TaskPriority = TaskPriority.NORMAL,
    transport: httpx.BaseTransport | None = None,
) -> TodoTaskInfo:
    payload = request_todo_api(
        settings,
        "POST",
        settings.todo_api_tasks_url,
        json_body={
            "title": title,
            "description": description,
            "priority": priority.value,
        },
        transport=transport,
    )
    return parse_todo_task_response(payload)


def cancel_todo_task_via_api(
    settings: TodoMCPSettings,
    *,
    task_id: str,
    transport: httpx.BaseTransport | None = None,
) -> TodoTaskInfo:
    current = get_todo_task_via_api(settings, task_id, transport=transport)
    if current["status"] == TaskStatus.CANCELLED.value:
        return current
    payload = request_todo_api(
        settings,
        "POST",
        f"{settings.todo_api_tasks_url}/{task_id}/cancel",
        transport=transport,
    )
    return parse_todo_task_response(payload)


def complete_todo_task_via_api(
    settings: TodoMCPSettings,
    *,
    task_id: str,
    transport: httpx.BaseTransport | None = None,
) -> TodoTaskInfo:
    current = get_todo_task_via_api(settings, task_id, transport=transport)
    if current["status"] == TaskStatus.COMPLETED.value:
        return current
    payload = request_todo_api(
        settings,
        "POST",
        f"{settings.todo_api_tasks_url}/{task_id}/complete",
        transport=transport,
    )
    return parse_todo_task_response(payload)


def request_todo_api(
    settings: TodoMCPSettings,
    method: str,
    url: str,
    *,
    json_body: dict[str, object] | None = None,
    params: dict[str, str | int] | None = None,
    transport: httpx.BaseTransport | None = None,
) -> Any:
    try:
        with httpx.Client(
            timeout=settings.todo_api_timeout_seconds,
            transport=transport,
        ) as client:
            response = client.request(method, url, json=json_body, params=params)
    except httpx.RequestError as exc:
        raise ToolError(f"Todo API is unavailable: {exc}") from exc

    if response.is_error:
        raise ToolError(format_todo_api_error(response))

    try:
        return response.json()
    except ValueError as exc:
        raise ToolError("Todo API returned an invalid JSON response.") from exc


def parse_todo_task_response(payload: Any) -> TodoTaskInfo:
    if not isinstance(payload, dict):
        msg = "Todo API task response must be an object."
        raise ValueError(msg)
    try:
        task = TaskRead.model_validate(payload)
    except ValidationError as exc:
        raise ValueError("Todo API task response is invalid.") from exc

    return todo_task_to_info(task)


def todo_task_to_info(task: TaskRead) -> TodoTaskInfo:
    return {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "status": task.status.value,
        "priority": task.priority.value,
        "completed_at": datetime_to_isoformat(task.completed_at),
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
    }


def format_todo_api_error(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return f"TODO_API_ERROR: Todo API returned HTTP {response.status_code}."

    error = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(error, dict):
        return f"TODO_API_ERROR: Todo API returned HTTP {response.status_code}."

    code = error.get("code")
    message = error.get("message")
    details = error.get("details", {})
    if not isinstance(code, str) or not isinstance(message, str):
        return f"TODO_API_ERROR: Todo API returned HTTP {response.status_code}."
    if not isinstance(details, dict):
        details = {}
    return f"{code}: {message}. details={json.dumps(details, sort_keys=True)}"


def validate_pagination(limit: int, offset: int) -> None:
    if limit < 1 or limit > 500:
        msg = "limit must be between 1 and 500"
        raise ValueError(msg)
    if offset < 0:
        msg = "offset must be greater than or equal to 0"
        raise ValueError(msg)


def datetime_to_isoformat(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()
