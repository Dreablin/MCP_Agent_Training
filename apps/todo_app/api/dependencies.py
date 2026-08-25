from collections.abc import Generator

from fastapi import Request
from sqlalchemy.orm import Session, sessionmaker

from apps.todo_app.database import session_scope
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
