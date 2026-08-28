from pathlib import Path

import pytest

from apps.todo_app.command_runner import TaskCommandRunner
from apps.todo_app.database import Base, build_engine, build_session_factory
from apps.todo_app.events import TaskEvent, TaskEventBus
from apps.todo_app.models import TaskPriority, TaskStatus
from apps.todo_app.schemas import TaskCreate, TaskUpdate


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_task_event_bus_publishes_to_subscription() -> None:
    event_bus = TaskEventBus()
    subscription = event_bus.subscribe()
    event = TaskEvent(
        action="completed",
        task_id="task-1",
        status=TaskStatus.COMPLETED,
        priority=TaskPriority.HIGH,
    )

    event_bus.publish(event)

    assert await subscription.get() == event
    assert event.as_dict() == {
        "action": "completed",
        "task_id": "task-1",
        "status": "completed",
        "priority": "high",
    }
    event_bus.unsubscribe(subscription)


@pytest.mark.anyio
async def test_task_command_runner_publishes_mutations_after_commit(tmp_path: Path) -> None:
    engine = build_engine(f"sqlite:///{(tmp_path / 'todo.db').as_posix()}")
    Base.metadata.create_all(engine)
    session_factory = build_session_factory(engine)
    event_bus = TaskEventBus()
    command_runner = TaskCommandRunner(session_factory, event_bus)
    subscription = event_bus.subscribe()

    try:
        created = command_runner.run(lambda service: service.create(TaskCreate(title="Task")))
        assert await subscription.get() == TaskEvent(
            action="created",
            task_id=created.id,
            status=TaskStatus.OPEN,
            priority=TaskPriority.NORMAL,
        )

        updated = command_runner.run(
            lambda service: service.update(
                created.id,
                TaskUpdate(title="Updated task", priority=TaskPriority.HIGH),
            )
        )
        assert updated.title == "Updated task"
        assert await subscription.get() == TaskEvent(
            action="updated",
            task_id=created.id,
            status=TaskStatus.OPEN,
            priority=TaskPriority.HIGH,
        )

        completed = command_runner.run(lambda service: service.complete(created.id))
        assert completed.status == TaskStatus.COMPLETED
        assert await subscription.get() == TaskEvent(
            action="completed",
            task_id=created.id,
            status=TaskStatus.COMPLETED,
            priority=TaskPriority.HIGH,
        )

        reopened = command_runner.run(lambda service: service.reopen(created.id))
        assert reopened.status == TaskStatus.OPEN
        assert await subscription.get() == TaskEvent(
            action="reopened",
            task_id=created.id,
            status=TaskStatus.OPEN,
            priority=TaskPriority.HIGH,
        )

        cancelled = command_runner.run(lambda service: service.cancel(created.id))
        assert cancelled.status == TaskStatus.CANCELLED
        assert await subscription.get() == TaskEvent(
            action="cancelled",
            task_id=created.id,
            status=TaskStatus.CANCELLED,
            priority=TaskPriority.HIGH,
        )
    finally:
        event_bus.unsubscribe(subscription)
        engine.dispose()
