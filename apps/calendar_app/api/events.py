from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from apps.calendar_app.api.dependencies import get_event_service
from apps.calendar_app.models import CalendarEventStatus
from apps.calendar_app.repositories import EventSearch
from apps.calendar_app.schemas import CalendarEventCreate, CalendarEventRead, CalendarEventUpdate
from apps.calendar_app.services import CalendarEventService
from shared.datetime import require_naive
from shared.errors import ValidationAppError

router = APIRouter(prefix="/api/events", tags=["calendar events"])


@router.post("", response_model=CalendarEventRead, status_code=status.HTTP_201_CREATED)
def create_event(
    payload: CalendarEventCreate,
    service: Annotated[CalendarEventService, Depends(get_event_service)],
) -> CalendarEventRead:
    return service.create(payload)


@router.get("", response_model=list[CalendarEventRead])
def list_events(
    service: Annotated[CalendarEventService, Depends(get_event_service)],
    query: Annotated[str | None, Query(max_length=300)] = None,
    status_filter: Annotated[CalendarEventStatus | None, Query(alias="status")] = None,
    starts_before: datetime | None = None,
    ends_after: datetime | None = None,
    include_cancelled: bool = True,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[CalendarEventRead]:
    starts_before = validate_optional_local_datetime(starts_before, "starts_before")
    ends_after = validate_optional_local_datetime(ends_after, "ends_after")
    return service.list_events(
        EventSearch(
            query=query,
            status=status_filter,
            starts_before=starts_before,
            ends_after=ends_after,
            include_cancelled=include_cancelled,
            limit=limit,
            offset=offset,
        )
    )


@router.get("/overlaps", response_model=list[CalendarEventRead])
def find_overlaps(
    service: Annotated[CalendarEventService, Depends(get_event_service)],
    start_at: datetime,
    end_at: datetime,
    exclude_event_id: str | None = None,
) -> list[CalendarEventRead]:
    start_at = validate_required_local_datetime(start_at, "start_at")
    end_at = validate_required_local_datetime(end_at, "end_at")
    return service.find_overlaps(start_at, end_at, exclude_event_id=exclude_event_id)


@router.get("/{event_id}", response_model=CalendarEventRead)
def get_event(
    event_id: str,
    service: Annotated[CalendarEventService, Depends(get_event_service)],
) -> CalendarEventRead:
    return service.get(event_id)


@router.patch("/{event_id}", response_model=CalendarEventRead)
def update_event(
    event_id: str,
    payload: CalendarEventUpdate,
    service: Annotated[CalendarEventService, Depends(get_event_service)],
) -> CalendarEventRead:
    return service.update(event_id, payload)


@router.post("/{event_id}/cancel", response_model=CalendarEventRead)
def cancel_event(
    event_id: str,
    service: Annotated[CalendarEventService, Depends(get_event_service)],
) -> CalendarEventRead:
    return service.cancel(event_id)


@router.post("/{event_id}/restore", response_model=CalendarEventRead)
def restore_event(
    event_id: str,
    service: Annotated[CalendarEventService, Depends(get_event_service)],
) -> CalendarEventRead:
    return service.restore(event_id)


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_event(
    event_id: str,
    service: Annotated[CalendarEventService, Depends(get_event_service)],
) -> Response:
    service.delete(event_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def validate_optional_local_datetime(value: datetime | None, field_name: str) -> datetime | None:
    if value is None:
        return None
    return validate_required_local_datetime(value, field_name)


def validate_required_local_datetime(value: datetime, field_name: str) -> datetime:
    try:
        return require_naive(value, field_name)
    except ValueError as exc:
        raise ValidationAppError(str(exc), details={"field": field_name}) from exc
