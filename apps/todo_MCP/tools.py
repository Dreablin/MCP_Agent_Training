import json
from collections.abc import Callable, Generator
from contextlib import contextmanager
from datetime import datetime
from typing import TypedDict

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from sqlalchemy.orm import Session, sessionmaker

from apps.todo_app.database import session_scope
from apps.todo_app.models import TaskPriority, TaskStatus
from apps.todo_app.repositories import TaskRepository, TaskSearch
from apps.todo_app.schemas import TaskCreate, TaskRead
from apps.todo_app.services import TaskService
from shared.errors import AppError


class TodoTaskInfo(TypedDict):
    id: str
    title: str
    description: str
    status: str
    priority: str
    completed_at: str | None
    created_at: str
    updated_at: str


def register_tools(mcp: MCPServer, session_factory: sessionmaker[Session]) -> None:
    """Register Todo MCP tools here as they are added."""
    mcp.add_tool(
        list_todo_tasks_tool(session_factory),
        name="list_todo_tasks",
        title="List todo tasks",
        annotations=ToolAnnotations(
            read_only_hint=True,
            open_world_hint=False,
        ),
    )
    mcp.add_tool(
        create_todo_task_tool(session_factory),
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
        cancel_todo_task_tool(session_factory),
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
        complete_todo_task_tool(session_factory),
        name="complete_todo_task",
        title="Complete todo task",
        annotations=ToolAnnotations(
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        ),
    )


def list_todo_tasks_tool(
    session_factory: sessionmaker[Session],
) -> Callable[..., list[TodoTaskInfo]]:
    def list_todo_tasks(
        status: TaskStatus | None = None,
        priority: TaskPriority | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[TodoTaskInfo]:
        """List todo tasks, optionally filtered by status and priority."""
        return list_todo_tasks_with_service(
            session_factory,
            status=status,
            priority=priority,
            limit=limit,
            offset=offset,
        )

    return list_todo_tasks


def create_todo_task_tool(
    session_factory: sessionmaker[Session],
) -> Callable[..., TodoTaskInfo]:
    def create_todo_task(
        title: str,
        description: str = "",
        priority: TaskPriority = TaskPriority.NORMAL,
    ) -> TodoTaskInfo:
        """Create a new todo task."""
        return create_todo_task_with_service(
            session_factory,
            title=title,
            description=description,
            priority=priority,
        )

    return create_todo_task


def cancel_todo_task_tool(
    session_factory: sessionmaker[Session],
) -> Callable[..., TodoTaskInfo]:
    def cancel_todo_task(task_id: str) -> TodoTaskInfo:
        """Cancel an existing todo task by ID."""
        return cancel_todo_task_with_service(session_factory, task_id=task_id)

    return cancel_todo_task


def complete_todo_task_tool(
    session_factory: sessionmaker[Session],
) -> Callable[..., TodoTaskInfo]:
    def complete_todo_task(task_id: str) -> TodoTaskInfo:
        """Complete an existing todo task by ID."""
        return complete_todo_task_with_service(session_factory, task_id=task_id)

    return complete_todo_task


def list_todo_tasks_with_service(
    session_factory: sessionmaker[Session],
    *,
    status: TaskStatus | None = None,
    priority: TaskPriority | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[TodoTaskInfo]:
    validate_pagination(limit, offset)

    with todo_task_service_scope(session_factory) as service:
        tasks = service.list(
            TaskSearch(
                status=status,
                priority=priority,
                limit=limit,
                offset=offset,
            )
        )

    return [todo_task_to_info(task) for task in tasks]


def create_todo_task_with_service(
    session_factory: sessionmaker[Session],
    *,
    title: str,
    description: str = "",
    priority: TaskPriority = TaskPriority.NORMAL,
) -> TodoTaskInfo:
    payload = TaskCreate(
        title=title,
        description=description,
        priority=priority,
    )

    try:
        with todo_task_service_scope(session_factory) as service:
            created = service.create(payload)
    except AppError as exc:
        raise ToolError(format_app_error(exc)) from exc

    return todo_task_to_info(created)


def cancel_todo_task_with_service(
    session_factory: sessionmaker[Session],
    *,
    task_id: str,
) -> TodoTaskInfo:
    try:
        with todo_task_service_scope(session_factory) as service:
            current = service.get(task_id)
            if current.status == TaskStatus.CANCELLED:
                return todo_task_to_info(current)
            cancelled = service.cancel(task_id)
    except AppError as exc:
        raise ToolError(format_app_error(exc)) from exc

    return todo_task_to_info(cancelled)


def complete_todo_task_with_service(
    session_factory: sessionmaker[Session],
    *,
    task_id: str,
) -> TodoTaskInfo:
    try:
        with todo_task_service_scope(session_factory) as service:
            current = service.get(task_id)
            if current.status == TaskStatus.COMPLETED:
                return todo_task_to_info(current)
            completed = service.complete(task_id)
    except AppError as exc:
        raise ToolError(format_app_error(exc)) from exc

    return todo_task_to_info(completed)


@contextmanager
def todo_task_service_scope(
    session_factory: sessionmaker[Session],
) -> Generator[TaskService]:
    with session_scope(session_factory) as session:
        yield TaskService(TaskRepository(session))


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


def format_app_error(exc: AppError) -> str:
    return (
        f"{exc.code.value}: {exc.message}. "
        f"details={json.dumps(exc.details, sort_keys=True)}"
    )


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
