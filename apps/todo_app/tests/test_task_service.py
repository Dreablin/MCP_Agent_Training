from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from apps.todo_app.database import Base, build_engine, build_session_factory
from apps.todo_app.models import TaskPriority, TaskStatus
from apps.todo_app.repositories import TaskRepository
from apps.todo_app.schemas import TaskCreate, TaskUpdate
from apps.todo_app.services import TaskService
from shared.errors import NotFoundError


@pytest.fixture
def service(tmp_path: Path) -> Iterator[TaskService]:
    engine = build_engine(f"sqlite:///{(tmp_path / 'todo.db').as_posix()}")
    Base.metadata.create_all(engine)
    session_factory = build_session_factory(engine)
    db_session: Session = session_factory()
    try:
        yield TaskService(TaskRepository(db_session))
    finally:
        db_session.close()
        engine.dispose()


def task_payload(title: str = "Prepare meeting notes") -> TaskCreate:
    return TaskCreate(
        title=title,
        description="Collect agenda items",
        priority=TaskPriority.HIGH,
    )


def test_service_complete_and_reopen_updates_completed_at(service: TaskService) -> None:
    created = service.create(task_payload())

    completed = service.complete(created.id)
    reopened = service.reopen(created.id)

    assert completed.status == TaskStatus.COMPLETED
    assert completed.completed_at is not None
    assert reopened.status == TaskStatus.OPEN
    assert reopened.completed_at is None


def test_service_cancel_clears_completed_at(service: TaskService) -> None:
    created = service.create(task_payload())
    service.complete(created.id)

    cancelled = service.cancel(created.id)

    assert cancelled.status == TaskStatus.CANCELLED
    assert cancelled.completed_at is None


def test_service_update_priority(service: TaskService) -> None:
    created = service.create(task_payload())

    updated = service.update(created.id, TaskUpdate(priority=TaskPriority.URGENT))

    assert updated.priority == TaskPriority.URGENT


def test_service_raises_not_found(service: TaskService) -> None:
    with pytest.raises(NotFoundError):
        service.get("missing")
