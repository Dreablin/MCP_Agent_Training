from collections.abc import Generator
from typing import cast

from fastapi import Request
from sqlalchemy.orm import Session, sessionmaker

from apps.calendar_app.database import session_scope
from apps.calendar_app.events import CalendarEventBus
from apps.calendar_app.repositories import CalendarEventRepository
from apps.calendar_app.services import CalendarEventService


def get_session(request: Request) -> Generator[Session]:
    session_factory: sessionmaker[Session] = request.app.state.session_factory
    with session_scope(session_factory) as session:
        yield session


def get_event_service(request: Request) -> Generator[CalendarEventService]:
    session_factory: sessionmaker[Session] = request.app.state.session_factory
    event_bus: CalendarEventBus = request.app.state.calendar_event_bus
    service: CalendarEventService | None = None
    with session_scope(session_factory) as session:
        service = CalendarEventService(CalendarEventRepository(session))
        yield service
    assert service is not None
    for event in service.pull_events():
        event_bus.publish(event)


def get_calendar_event_bus(request: Request) -> CalendarEventBus:
    return cast(CalendarEventBus, request.app.state.calendar_event_bus)
