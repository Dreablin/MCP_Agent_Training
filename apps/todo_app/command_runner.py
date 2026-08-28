from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from sqlalchemy.orm import Session, sessionmaker

from apps.todo_app.database import session_scope
from apps.todo_app.events import TaskEventBus
from apps.todo_app.repositories import TaskRepository
from apps.todo_app.services import TaskService

T = TypeVar("T")


class TaskCommandRunner:
    """Execute task commands and publish their events after commit."""

    def __init__(self, session_factory: sessionmaker[Session], event_bus: TaskEventBus) -> None:
        self._session_factory = session_factory
        self._event_bus = event_bus

    def run(self, action: Callable[[TaskService], T]) -> T:
        service: TaskService | None = None
        with session_scope(self._session_factory) as session:
            service = TaskService(TaskRepository(session))
            result = action(service)

        assert service is not None
        for event in service.pull_events():
            self._event_bus.publish(event)
        return result
