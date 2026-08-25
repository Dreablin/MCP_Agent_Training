from collections.abc import Generator

from fastapi import Request
from sqlalchemy.orm import Session, sessionmaker

from apps.calendar_app.database import session_scope
from apps.calendar_app.repositories import CalendarEventRepository
from apps.calendar_app.services import CalendarEventService


def get_session(request: Request) -> Generator[Session]:
    session_factory: sessionmaker[Session] = request.app.state.session_factory
    with session_scope(session_factory) as session:
        yield session


def get_event_service(request: Request) -> Generator[CalendarEventService]:
    session_factory: sessionmaker[Session] = request.app.state.session_factory
    with session_scope(session_factory) as session:
        yield CalendarEventService(CalendarEventRepository(session))
