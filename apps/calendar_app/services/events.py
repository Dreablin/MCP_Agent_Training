from __future__ import annotations

from datetime import datetime

from apps.calendar_app.models import CalendarEventStatus
from apps.calendar_app.repositories import CalendarEventRepository, EventSearch
from apps.calendar_app.schemas import CalendarEventCreate, CalendarEventRead, CalendarEventUpdate
from shared.errors import NotFoundError, ValidationAppError


class CalendarEventService:
    def __init__(self, repository: CalendarEventRepository) -> None:
        self._repository = repository

    def create(self, payload: CalendarEventCreate) -> CalendarEventRead:
        return self._to_read_model(self._repository.create(payload))

    def list_events(self, search: EventSearch | None = None) -> list[CalendarEventRead]:
        return [self._to_read_model(event) for event in self._repository.list(search)]

    def get(self, event_id: str) -> CalendarEventRead:
        event = self._repository.get(event_id)
        if event is None:
            raise NotFoundError("Calendar event not found", details={"id": event_id})
        return self._to_read_model(event)

    def update(self, event_id: str, payload: CalendarEventUpdate) -> CalendarEventRead:
        current = self.get(event_id)
        values = payload.model_dump(exclude_unset=True)
        start_at = values.get("start_at", current.start_at)
        end_at = values.get("end_at", current.end_at)
        if isinstance(start_at, datetime) and isinstance(end_at, datetime) and end_at <= start_at:
            raise ValidationAppError(
                "Event end time must be later than start time",
                details={"field": "end_at"},
            )
        event = self._repository.update(event_id, values)
        if event is None:
            raise NotFoundError("Calendar event not found", details={"id": event_id})
        return self._to_read_model(event)

    def reschedule(self, event_id: str, start_at: datetime, end_at: datetime) -> CalendarEventRead:
        return self.update(event_id, CalendarEventUpdate(start_at=start_at, end_at=end_at))

    def cancel(self, event_id: str) -> CalendarEventRead:
        return self.update(event_id, CalendarEventUpdate(status=CalendarEventStatus.CANCELLED))

    def restore(self, event_id: str) -> CalendarEventRead:
        return self.update(event_id, CalendarEventUpdate(status=CalendarEventStatus.CONFIRMED))

    def delete(self, event_id: str) -> None:
        deleted = self._repository.delete(event_id)
        if not deleted:
            raise NotFoundError("Calendar event not found", details={"id": event_id})

    def find_overlaps(
        self,
        start_at: datetime,
        end_at: datetime,
        *,
        exclude_event_id: str | None = None,
    ) -> list[CalendarEventRead]:
        if end_at <= start_at:
            raise ValidationAppError(
                "Range end time must be later than range start time",
                details={"field": "end_at"},
            )
        events = self.list_events(
            EventSearch(
                starts_before=end_at,
                ends_after=start_at,
                include_cancelled=False,
                limit=500,
            )
        )
        if exclude_event_id is None:
            return events
        return [event for event in events if event.id != exclude_event_id]

    @staticmethod
    def _to_read_model(event: object) -> CalendarEventRead:
        return CalendarEventRead.model_validate(event)
