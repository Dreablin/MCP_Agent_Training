from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from apps.calendar_app.database import Base, build_engine, build_session_factory
from apps.calendar_app.models import CalendarEventStatus
from apps.calendar_app.repositories import CalendarEventRepository, EventSearch
from apps.calendar_app.schemas import CalendarEventCreate, Participant
from shared.datetime import UTC


@pytest.fixture
def session(tmp_path: Path) -> Iterator[Session]:
    engine = build_engine(f"sqlite:///{(tmp_path / 'calendar.db').as_posix()}")
    Base.metadata.create_all(engine)
    session_factory = build_session_factory(engine)
    db_session = session_factory()
    try:
        yield db_session
    finally:
        db_session.close()
        engine.dispose()


def event_payload(
    *,
    title: str = "Meeting with Anna",
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    participants: list[Participant] | None = None,
) -> CalendarEventCreate:
    start = start_at or datetime(2026, 8, 12, 14, 30, tzinfo=ZoneInfo("America/Chicago"))
    end = end_at or datetime(2026, 8, 12, 15, 30, tzinfo=ZoneInfo("America/Chicago"))
    return CalendarEventCreate(
        title=title,
        description="Discuss training project",
        start_at=start,
        end_at=end,
        location="Office",
        participants=participants
        or [Participant(name="Anna", email="anna@example.test")],
    )


def test_create_and_get_event(session: Session) -> None:
    repository = CalendarEventRepository(session)

    event = repository.create(event_payload())
    session.commit()

    found = repository.get(event.id)
    assert found is not None
    assert found.title == "Meeting with Anna"
    assert found.status == CalendarEventStatus.CONFIRMED.value
    assert found.timezone == "local"
    assert found.start_at.tzinfo == UTC
    assert found.participants == [{"name": "Anna", "email": "anna@example.test"}]


def test_event_requires_end_after_start() -> None:
    start = datetime(2026, 8, 12, 15, 30, tzinfo=ZoneInfo("America/Chicago"))
    end = datetime(2026, 8, 12, 14, 30, tzinfo=ZoneInfo("America/Chicago"))

    with pytest.raises(ValidationError):
        event_payload(start_at=start, end_at=end)


def test_search_by_title_and_participant(session: Session) -> None:
    repository = CalendarEventRepository(session)
    repository.create(event_payload(title="Meeting with Anna"))
    repository.create(
        event_payload(
            title="Planning",
            participants=[Participant(name="Sergey", email="sergey@example.test")],
        )
    )
    session.commit()

    title_results = repository.list(EventSearch(query="anna"))
    participant_results = repository.list(EventSearch(query="sergey"))

    assert [event.title for event in title_results] == ["Meeting with Anna"]
    assert [event.title for event in participant_results] == ["Planning"]


def test_period_query_returns_overlapping_events(session: Session) -> None:
    repository = CalendarEventRepository(session)
    repository.create(event_payload(title="Inside period"))
    repository.create(
        event_payload(
            title="Outside period",
            start_at=datetime(2026, 9, 1, 9, 0, tzinfo=ZoneInfo("America/Chicago")),
            end_at=datetime(2026, 9, 1, 10, 0, tzinfo=ZoneInfo("America/Chicago")),
        )
    )
    session.commit()

    results = repository.list(
        EventSearch(
            starts_before=datetime(2026, 8, 13, 0, 0, tzinfo=ZoneInfo("America/Chicago")),
            ends_after=datetime(2026, 8, 12, 0, 0, tzinfo=ZoneInfo("America/Chicago")),
        )
    )

    assert [event.title for event in results] == ["Inside period"]


def test_cancelled_events_can_be_excluded(session: Session) -> None:
    repository = CalendarEventRepository(session)
    cancelled = repository.create(event_payload(title="Cancelled"))
    active = repository.create(event_payload(title="Active"))
    repository.update(cancelled.id, {"status": CalendarEventStatus.CANCELLED})
    session.commit()

    results = repository.list(EventSearch(include_cancelled=False))

    assert [event.id for event in results] == [active.id]
