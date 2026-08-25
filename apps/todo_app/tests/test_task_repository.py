from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from apps.todo_app.database import Base, build_engine, build_session_factory
from apps.todo_app.models import TaskPriority, TaskStatus
from apps.todo_app.repositories import TaskRepository, TaskSearch
from apps.todo_app.schemas import TaskCreate


@pytest.fixture
def session(tmp_path: Path) -> Iterator[Session]:
    engine = build_engine(f"sqlite:///{(tmp_path / 'todo.db').as_posix()}")
    Base.metadata.create_all(engine)
    session_factory = build_session_factory(engine)
    db_session = session_factory()
    try:
        yield db_session
    finally:
        db_session.close()
        engine.dispose()


def create_task(
    repository: TaskRepository,
    *,
    title: str = "Prepare meeting notes",
    description: str = "Collect agenda items",
    priority: TaskPriority = TaskPriority.NORMAL,
) -> str:
    task = repository.create(
        TaskCreate(
            title=title,
            description=description,
            priority=priority,
        )
    )
    return task.id


def test_create_task(session: Session) -> None:
    repository = TaskRepository(session)

    task_id = create_task(repository)
    session.commit()

    task = repository.get(task_id)
    assert task is not None
    assert task.title == "Prepare meeting notes"
    assert task.status == TaskStatus.OPEN.value
    assert task.priority == TaskPriority.NORMAL.value


def test_filter_by_status_priority_and_search(session: Session) -> None:
    repository = TaskRepository(session)
    first_id = create_task(repository, title="Prepare deck", priority=TaskPriority.HIGH)
    create_task(repository, title="Buy milk", priority=TaskPriority.LOW)
    repository.update(first_id, {"status": TaskStatus.IN_PROGRESS})
    session.commit()

    status_results = repository.list(TaskSearch(status=TaskStatus.IN_PROGRESS))
    priority_results = repository.list(TaskSearch(priority=TaskPriority.LOW))
    query_results = repository.list(TaskSearch(query="deck"))

    assert [task.title for task in status_results] == ["Prepare deck"]
    assert [task.title for task in priority_results] == ["Buy milk"]
    assert [task.title for task in query_results] == ["Prepare deck"]


def test_default_list_orders_newest_first(session: Session) -> None:
    repository = TaskRepository(session)
    create_task(repository, title="First")
    create_task(repository, title="Second")
    session.commit()

    results = repository.list()

    assert [task.title for task in results] == ["Second", "First"]
