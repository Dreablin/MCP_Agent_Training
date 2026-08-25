from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from apps.calendar_app.api.dependencies import get_event_service
from apps.calendar_app.models import CalendarEventStatus
from apps.calendar_app.repositories import EventSearch
from apps.calendar_app.schemas import CalendarEventCreate, CalendarEventRead, CalendarEventUpdate
from apps.calendar_app.services import CalendarEventService

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
