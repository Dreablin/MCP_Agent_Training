from pathlib import Path

import pytest
from mcp.server.mcpserver.exceptions import ToolError
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session, sessionmaker

from apps.todo_app.config import TodoAppSettings
from apps.todo_app.database import Base
from apps.todo_app.models import Task, TaskPriority, TaskStatus  # noqa: F401
from apps.todo_app.schemas import TaskCreate
from apps.todo_MCP.main import create_runtime
from apps.todo_MCP.server import create_mcp_server
from apps.todo_MCP.tools import (
    cancel_todo_task_with_service,
    complete_todo_task_with_service,
    create_todo_task_with_service,
    list_todo_tasks_with_service,
    todo_task_service_scope,
)


@pytest.mark.anyio
async def test_todo_mcp_server_registers_tools() -> None:
    engine = create_engine("sqlite:///:memory:")
    session_factory: sessionmaker[Session] = sessionmaker(bind=engine, expire_on_commit=False)

    mcp = create_mcp_server(session_factory)
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


def test_todo_mcp_runtime_initializes_todo_database(tmp_path: Path) -> None:
    settings = TodoAppSettings(db_path=tmp_path / "todo.db")

    runtime = create_runtime(settings)
    try:
        assert settings.db_path.exists()
        assert inspect(runtime.engine).has_table("tasks")
        assert runtime.mcp.name == "Todo MCP server"
    finally:
        runtime.engine.dispose()


def test_todo_mcp_service_scope_uses_session_factory_per_call() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory: sessionmaker[Session] = sessionmaker(bind=engine, expire_on_commit=False)

    with todo_task_service_scope(session_factory) as service:
        created = service.create(TaskCreate(title="Write Todo MCP skeleton"))

    with todo_task_service_scope(session_factory) as service:
        tasks = service.list()

    assert [task.id for task in tasks] == [created.id]


def test_list_todo_tasks_tool_filters_by_status_and_priority() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory: sessionmaker[Session] = sessionmaker(bind=engine, expire_on_commit=False)

    high = create_todo_task_with_service(
        session_factory,
        title="High open",
        priority=TaskPriority.HIGH,
    )
    normal = create_todo_task_with_service(
        session_factory,
        title="Normal open",
        priority=TaskPriority.NORMAL,
    )
    completed = create_todo_task_with_service(
        session_factory,
        title="High completed",
        priority=TaskPriority.HIGH,
    )
    with todo_task_service_scope(session_factory) as service:
        service.complete(completed["id"])

    high_tasks = list_todo_tasks_with_service(session_factory, priority=TaskPriority.HIGH)
    open_tasks = list_todo_tasks_with_service(session_factory, status=TaskStatus.OPEN)
    completed_high_tasks = list_todo_tasks_with_service(
        session_factory,
        status=TaskStatus.COMPLETED,
        priority=TaskPriority.HIGH,
    )
    paged_tasks = list_todo_tasks_with_service(session_factory, limit=1, offset=1)

    assert [task["id"] for task in high_tasks] == [completed["id"], high["id"]]
    assert [task["id"] for task in open_tasks] == [normal["id"], high["id"]]
    assert [task["id"] for task in completed_high_tasks] == [completed["id"]]
    assert len(paged_tasks) == 1


def test_list_todo_tasks_tool_validates_pagination() -> None:
    engine = create_engine("sqlite:///:memory:")
    session_factory: sessionmaker[Session] = sessionmaker(bind=engine, expire_on_commit=False)

    with pytest.raises(ValueError, match="limit must be between 1 and 500"):
        list_todo_tasks_with_service(session_factory, limit=0)
    with pytest.raises(ValueError, match="offset must be greater than or equal to 0"):
        list_todo_tasks_with_service(session_factory, offset=-1)


def test_create_todo_task_tool_uses_service_layer() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory: sessionmaker[Session] = sessionmaker(bind=engine, expire_on_commit=False)

    task = create_todo_task_with_service(
        session_factory,
        title="Write first Todo MCP tool",
        description="Create tasks through the service layer.",
        priority=TaskPriority.HIGH,
    )

    assert task["title"] == "Write first Todo MCP tool"
    assert task["description"] == "Create tasks through the service layer."
    assert task["status"] == "open"
    assert task["priority"] == "high"
    assert task["completed_at"] is None
    assert task["created_at"]
    assert task["updated_at"]

    with todo_task_service_scope(session_factory) as service:
        stored = service.get(task["id"])

    assert stored.title == "Write first Todo MCP tool"
    assert stored.priority == TaskPriority.HIGH


def test_cancel_todo_task_tool_cancels_existing_task() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory: sessionmaker[Session] = sessionmaker(bind=engine, expire_on_commit=False)

    task = create_todo_task_with_service(
        session_factory,
        title="Cancel me",
    )

    cancelled = cancel_todo_task_with_service(session_factory, task_id=task["id"])

    assert cancelled["id"] == task["id"]
    assert cancelled["status"] == "cancelled"
    assert cancelled["completed_at"] is None

    with todo_task_service_scope(session_factory) as service:
        stored = service.get(task["id"])

    assert stored.status.value == "cancelled"


def test_cancel_todo_task_tool_is_idempotent() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory: sessionmaker[Session] = sessionmaker(bind=engine, expire_on_commit=False)

    task = create_todo_task_with_service(
        session_factory,
        title="Cancel me once",
    )

    first_cancel = cancel_todo_task_with_service(session_factory, task_id=task["id"])
    second_cancel = cancel_todo_task_with_service(session_factory, task_id=task["id"])

    assert first_cancel["status"] == "cancelled"
    assert second_cancel["status"] == "cancelled"
    assert second_cancel["updated_at"] == first_cancel["updated_at"]


def test_cancel_todo_task_tool_reports_missing_task() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory: sessionmaker[Session] = sessionmaker(bind=engine, expire_on_commit=False)

    with pytest.raises(ToolError) as exc_info:
        cancel_todo_task_with_service(session_factory, task_id="missing")

    message = str(exc_info.value)
    assert "NOT_FOUND: Task not found." in message
    assert 'details={"id": "missing"}' in message


def test_complete_todo_task_tool_completes_existing_task() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory: sessionmaker[Session] = sessionmaker(bind=engine, expire_on_commit=False)

    task = create_todo_task_with_service(
        session_factory,
        title="Complete me",
    )

    completed = complete_todo_task_with_service(session_factory, task_id=task["id"])

    assert completed["id"] == task["id"]
    assert completed["status"] == "completed"
    assert completed["completed_at"] is not None

    with todo_task_service_scope(session_factory) as service:
        stored = service.get(task["id"])

    assert stored.status.value == "completed"
    assert stored.completed_at is not None


def test_complete_todo_task_tool_is_idempotent() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory: sessionmaker[Session] = sessionmaker(bind=engine, expire_on_commit=False)

    task = create_todo_task_with_service(
        session_factory,
        title="Complete me once",
    )

    first_complete = complete_todo_task_with_service(session_factory, task_id=task["id"])
    second_complete = complete_todo_task_with_service(session_factory, task_id=task["id"])

    assert first_complete["status"] == "completed"
    assert second_complete["status"] == "completed"
    assert second_complete["completed_at"] == first_complete["completed_at"]
    assert second_complete["updated_at"] == first_complete["updated_at"]


def test_complete_todo_task_tool_reports_missing_task() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory: sessionmaker[Session] = sessionmaker(bind=engine, expire_on_commit=False)

    with pytest.raises(ToolError) as exc_info:
        complete_todo_task_with_service(session_factory, task_id="missing")

    message = str(exc_info.value)
    assert "NOT_FOUND: Task not found." in message
    assert 'details={"id": "missing"}' in message
