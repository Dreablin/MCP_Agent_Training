from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from apps.calendar_app.models import CalendarEvent, CalendarEventStatus
from apps.calendar_app.schemas import CalendarEventCreate
from shared.datetime import now_local_naive


@dataclass(frozen=True)
class EventSearch:
    query: str | None = None
    status: CalendarEventStatus | None = None
    starts_before: datetime | None = None
    ends_after: datetime | None = None
    include_cancelled: bool = True
    limit: int = 100
    offset: int = 0


class CalendarEventRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, event: CalendarEventCreate) -> CalendarEvent:
        db_event = CalendarEvent(
            id=event.id,
            title=event.title,
            description=event.description,
            start_at=event.start_at,
            end_at=event.end_at,
            timezone=event.timezone,
            status=event.status.value,
            location=event.location,
            participants=[participant.model_dump() for participant in event.participants],
        )
        self._session.add(db_event)
        self._session.flush()
        self._session.refresh(db_event)
        return db_event

    def get(self, event_id: str) -> CalendarEvent | None:
        return self._session.get(CalendarEvent, event_id)

    def list(self, search: EventSearch | None = None) -> list[CalendarEvent]:
        criteria = search or EventSearch()
        statement = self._apply_search(select(CalendarEvent), criteria)
        statement = statement.order_by(
            CalendarEvent.start_at.asc(),
            CalendarEvent.created_at.desc(),
        )
        statement = statement.offset(criteria.offset).limit(criteria.limit)
        return list(self._session.scalars(statement).all())

    def update(self, event_id: str, values: dict[str, Any]) -> CalendarEvent | None:
        db_event = self.get(event_id)
        if db_event is None:
            return None

        allowed_fields = {
            "title",
            "description",
            "start_at",
            "end_at",
            "timezone",
            "status",
            "location",
            "participants",
        }
        for field_name, value in values.items():
            if field_name not in allowed_fields:
                continue
            if isinstance(value, CalendarEventStatus):
                value = value.value
            if field_name == "participants" and value is not None:
                value = [
                    participant.model_dump() if hasattr(participant, "model_dump") else participant
                    for participant in value
                ]
            setattr(db_event, field_name, value)
        db_event.updated_at = now_local_naive()
        self._session.flush()
        self._session.refresh(db_event)
        return db_event

    def delete(self, event_id: str) -> bool:
        db_event = self.get(event_id)
        if db_event is None:
            return False
        self._session.delete(db_event)
        self._session.flush()
        return True

    def count(self) -> int:
        return self._session.scalar(select(func.count()).select_from(CalendarEvent)) or 0

    def _apply_search(
        self,
        statement: Select[tuple[CalendarEvent]],
        search: EventSearch,
    ) -> Select[tuple[CalendarEvent]]:
        if not search.include_cancelled:
            statement = statement.where(CalendarEvent.status != CalendarEventStatus.CANCELLED.value)
        if search.status is not None:
            statement = statement.where(CalendarEvent.status == search.status.value)
        if search.starts_before is not None:
            statement = statement.where(CalendarEvent.start_at < search.starts_before)
        if search.ends_after is not None:
            statement = statement.where(CalendarEvent.end_at > search.ends_after)
        if search.query:
            query_pattern = self._like(search.query)
            statement = statement.where(
                or_(
                    func.lower(CalendarEvent.title).like(query_pattern),
                    func.lower(CalendarEvent.description).like(query_pattern),
                    func.lower(CalendarEvent.location).like(query_pattern),
                    func.lower(
                        func.json_extract(CalendarEvent.participants, "$")
                    ).like(query_pattern),
                )
            )
        return statement

    @staticmethod
    def _like(value: str) -> str:
        return f"%{value.lower()}%"
