from collections.abc import Generator
from typing import cast

from fastapi import Request
from sqlalchemy.orm import Session, sessionmaker

from apps.todo_app.command_runner import TaskCommandRunner
from apps.todo_app.database import session_scope
from apps.todo_app.events import TaskEventBus
from apps.todo_app.repositories import TaskRepository
from apps.todo_app.services import TaskService


def get_session(request: Request) -> Generator[Session]:
    session_factory: sessionmaker[Session] = request.app.state.session_factory
    with session_scope(session_factory) as session:
        yield session


def get_task_service(request: Request) -> Generator[TaskService]:
    session_factory: sessionmaker[Session] = request.app.state.session_factory
    with session_scope(session_factory) as session:
        yield TaskService(TaskRepository(session))


def get_task_event_bus(request: Request) -> TaskEventBus:
    return cast(TaskEventBus, request.app.state.task_event_bus)


def get_task_command_runner(request: Request) -> TaskCommandRunner:
    return cast(TaskCommandRunner, request.app.state.task_command_runner)
