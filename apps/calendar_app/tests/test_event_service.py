from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from apps.calendar_app.database import Base, build_engine, build_session_factory
from apps.calendar_app.events import CalendarEvent
from apps.calendar_app.models import CalendarEventStatus
from apps.calendar_app.repositories import CalendarEventRepository
from apps.calendar_app.schemas import CalendarEventCreate, CalendarEventUpdate, Participant
from apps.calendar_app.services import CalendarEventService
from shared.errors import ConflictError, NotFoundError, ValidationAppError


@pytest.fixture
def service(tmp_path: Path) -> Iterator[CalendarEventService]:
    engine = build_engine(f"sqlite:///{(tmp_path / 'calendar.db').as_posix()}")
    Base.metadata.create_all(engine)
    session_factory = build_session_factory(engine)
    db_session: Session = session_factory()
    try:
        yield CalendarEventService(CalendarEventRepository(db_session))
    finally:
        db_session.close()
        engine.dispose()


def event_payload(title: str = "Meeting with Anna") -> CalendarEventCreate:
    return CalendarEventCreate(
        title=title,
        description="Discuss training project",
        start_at=datetime(2026, 8, 12, 14, 30),
        end_at=datetime(2026, 8, 12, 15, 30),
        location="Office",
        participants=[Participant(name="Anna", email="anna@example.test")],
    )


def test_service_cancel_and_restore(service: CalendarEventService) -> None:
    created = service.create(event_payload())

    cancelled = service.cancel(created.id)
    restored = service.restore(created.id)

    assert cancelled.status == CalendarEventStatus.CANCELLED
    assert restored.status == CalendarEventStatus.CONFIRMED


def test_service_records_events_for_ui_auto_refresh(service: CalendarEventService) -> None:
    created = service.create(event_payload())

    assert service.pull_events() == [
        CalendarEvent(
            action="created",
            event_id=created.id,
            status=CalendarEventStatus.CONFIRMED,
        )
    ]

    service.cancel(created.id)
    assert service.pull_events() == [
        CalendarEvent(
            action="cancelled",
            event_id=created.id,
            status=CalendarEventStatus.CANCELLED,
        )
    ]

    service.restore(created.id)
    assert service.pull_events() == [
        CalendarEvent(
            action="restored",
            event_id=created.id,
            status=CalendarEventStatus.CONFIRMED,
        )
    ]

    service.delete(created.id)
    assert service.pull_events() == [CalendarEvent(action="deleted", event_id=created.id)]


def test_service_rejects_invalid_reschedule(service: CalendarEventService) -> None:
    created = service.create(event_payload())
    start = datetime(2026, 8, 12, 16, 0)
    end = datetime(2026, 8, 12, 15, 0)

    with pytest.raises(ValidationAppError):
        service.update(created.id, CalendarEventUpdate(start_at=start, end_at=end))


def test_service_rejects_overlapping_create(service: CalendarEventService) -> None:
    service.create(event_payload())

    with pytest.raises(ConflictError) as exc_info:
        service.create(
            CalendarEventCreate(
                title="Overlapping",
                start_at=datetime(2026, 8, 12, 15, 0),
                end_at=datetime(2026, 8, 12, 16, 0),
            )
        )

    assert exc_info.value.code == "CONFLICT"


def test_service_allows_adjacent_events(service: CalendarEventService) -> None:
    service.create(event_payload())

    created = service.create(
        CalendarEventCreate(
            title="Adjacent",
            start_at=datetime(2026, 8, 12, 15, 30),
            end_at=datetime(2026, 8, 12, 16, 0),
        )
    )

    assert created.title == "Adjacent"


def test_service_rejects_overlapping_reschedule(service: CalendarEventService) -> None:
    service.create(event_payload(title="First"))
    second = service.create(
        CalendarEventCreate(
            title="Second",
            start_at=datetime(2026, 8, 12, 16, 0),
            end_at=datetime(2026, 8, 12, 17, 0),
        )
    )

    with pytest.raises(ConflictError):
        service.update(
            second.id,
            CalendarEventUpdate(
                start_at=datetime(2026, 8, 12, 15, 0),
                end_at=datetime(2026, 8, 12, 16, 0),
            ),
        )


def test_service_rejects_restore_when_event_would_overlap(service: CalendarEventService) -> None:
    service.create(event_payload(title="First"))
    cancelled = service.create(
        CalendarEventCreate(
            title="Cancelled overlap",
            start_at=datetime(2026, 8, 12, 15, 0),
            end_at=datetime(2026, 8, 12, 16, 0),
            status=CalendarEventStatus.CANCELLED,
        )
    )

    with pytest.raises(ConflictError):
        service.restore(cancelled.id)


def test_service_find_overlaps(service: CalendarEventService) -> None:
    created = service.create(event_payload())

    overlaps = service.find_overlaps(
        datetime(2026, 8, 12, 15, 0),
        datetime(2026, 8, 12, 16, 0),
    )
    excluded = service.find_overlaps(
        datetime(2026, 8, 12, 15, 0),
        datetime(2026, 8, 12, 16, 0),
        exclude_event_id=created.id,
    )

    assert [event.id for event in overlaps] == [created.id]
    assert excluded == []


def test_service_raises_not_found(service: CalendarEventService) -> None:
    with pytest.raises(NotFoundError):
        service.get("missing")
