from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from sqlalchemy.orm import Session, sessionmaker

from apps.calendar_app.database import session_scope
from apps.calendar_app.events import CalendarEventBus
from apps.calendar_app.repositories import CalendarEventRepository
from apps.calendar_app.services import CalendarEventService

T = TypeVar("T")


class CalendarCommandRunner:
    """Execute calendar commands and publish their events after commit."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        event_bus: CalendarEventBus | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._event_bus = event_bus or CalendarEventBus()

    def run(self, action: Callable[[CalendarEventService], T]) -> T:
        service: CalendarEventService | None = None
        with session_scope(self._session_factory) as session:
            service = CalendarEventService(CalendarEventRepository(session))
            result = action(service)

        assert service is not None
        for event in service.pull_events():
            self._event_bus.publish(event)
        return result
