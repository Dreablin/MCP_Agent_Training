import json
from collections.abc import Callable, Generator
from contextlib import contextmanager
from datetime import datetime
from typing import TypedDict

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from sqlalchemy.orm import Session, sessionmaker

from apps.calendar_app.database import session_scope
from apps.calendar_app.repositories import CalendarEventRepository, EventSearch
from apps.calendar_app.schemas import (
    CalendarEventCreate,
    CalendarEventRead,
    CalendarEventUpdate,
    Participant,
)
from apps.calendar_app.services import CalendarEventService
from shared.datetime import require_naive
from shared.errors import ConflictError


class CalendarParticipantInfo(TypedDict):
    name: str
    email: str


class CalendarEventInfo(TypedDict):
    id: str
    title: str
    description: str
    start_at: str
    end_at: str
    status: str
    location: str
    participants: list[CalendarParticipantInfo]
    created_at: str
    updated_at: str


def register_tools(mcp: MCPServer, session_factory: sessionmaker[Session]) -> None:
    """Register Calendar MCP tools here as they are added."""
    mcp.add_tool(
        get_list_calendar_events_tool(session_factory),
        name="list_calendar_events",
        title="List calendar events",
        annotations=ToolAnnotations(
            read_only_hint=True,
            open_world_hint=False,
        ),
    )
    mcp.add_tool(
        search_calendar_events_tool(session_factory),
        name="search_calendar_events",
        title="Search calendar events",
        annotations=ToolAnnotations(
            read_only_hint=True,
            open_world_hint=False,
        ),
    )
    mcp.add_tool(
        create_calendar_event_tool(session_factory),
        name="create_calendar_event",
        title="Create calendar event",
        annotations=ToolAnnotations(
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=False,
            open_world_hint=False,
        ),
    )
    mcp.add_tool(
        update_calendar_event_tool(session_factory),
        name="update_calendar_event",
        title="Update calendar event",
        annotations=ToolAnnotations(
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=False,
            open_world_hint=False,
        ),
    )
    mcp.add_tool(
        cancel_calendar_event_tool(session_factory),
        name="cancel_calendar_event",
        title="Cancel calendar event",
        annotations=ToolAnnotations(
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=False,
            open_world_hint=False,
        ),
    )


def get_list_calendar_events_tool(
    session_factory: sessionmaker[Session],
) -> Callable[..., list[CalendarEventInfo]]:
    def list_calendar_events(
        start_at: datetime,
        end_at: datetime,
        include_cancelled: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[CalendarEventInfo]:
        """List calendar events that overlap the given local datetime range."""
        return list_calendar_events_with_service(
            session_factory,
            start_at=start_at,
            end_at=end_at,
            include_cancelled=include_cancelled,
            limit=limit,
            offset=offset,
        )

    return list_calendar_events


def search_calendar_events_tool(
    session_factory: sessionmaker[Session],
) -> Callable[..., list[CalendarEventInfo]]:
    def search_calendar_events(
        query: str,
        include_cancelled: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[CalendarEventInfo]:
        """Search calendar events by title, description, location, or participants."""
        return search_calendar_events_with_service(
            session_factory,
            query=query,
            include_cancelled=include_cancelled,
            limit=limit,
            offset=offset,
        )

    return search_calendar_events


def create_calendar_event_tool(
    session_factory: sessionmaker[Session],
) -> Callable[..., CalendarEventInfo]:
    def create_calendar_event(
        title: str,
        start_at: datetime,
        end_at: datetime,
        description: str = "",
        participants: list[dict[str, str]] | None = None,
    ) -> CalendarEventInfo:
        """Create a new calendar event with optional description and participants."""
        return create_calendar_event_with_service(
            session_factory,
            title=title,
            start_at=start_at,
            end_at=end_at,
            description=description,
            participants=participants,
        )

    return create_calendar_event


def update_calendar_event_tool(
    session_factory: sessionmaker[Session],
) -> Callable[..., CalendarEventInfo]:
    def update_calendar_event(
        event_id: str,
        title: str | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        description: str | None = None,
        location: str | None = None,
        participants: list[dict[str, str]] | None = None,
    ) -> CalendarEventInfo:
        """Update an existing calendar event by ID."""
        return update_calendar_event_with_service(
            session_factory,
            event_id=event_id,
            title=title,
            start_at=start_at,
            end_at=end_at,
            description=description,
            location=location,
            participants=participants,
        )

    return update_calendar_event


def cancel_calendar_event_tool(
    session_factory: sessionmaker[Session],
) -> Callable[..., CalendarEventInfo]:
    def cancel_calendar_event(event_id: str) -> CalendarEventInfo:
        """Cancel an existing calendar event by ID."""
        return cancel_calendar_event_with_service(session_factory, event_id=event_id)

    return cancel_calendar_event


def list_calendar_events_with_service(
    session_factory: sessionmaker[Session],
    *,
    start_at: datetime,
    end_at: datetime,
    include_cancelled: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> list[CalendarEventInfo]:
    validate_local_datetime_range(start_at, end_at)
    validate_pagination(limit, offset)

    with calendar_event_service_scope(session_factory) as service:
        events = service.list_events(
            EventSearch(
                starts_before=end_at,
                ends_after=start_at,
                include_cancelled=include_cancelled,
                limit=limit,
                offset=offset,
            )
        )

    return [calendar_event_to_info(event) for event in events]


def search_calendar_events_with_service(
    session_factory: sessionmaker[Session],
    *,
    query: str,
    include_cancelled: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> list[CalendarEventInfo]:
    query = query.strip()
    if not query:
        msg = "query must not be empty"
        raise ValueError(msg)
    validate_pagination(limit, offset)

    with calendar_event_service_scope(session_factory) as service:
        events = service.list_events(
            EventSearch(
                query=query,
                include_cancelled=include_cancelled,
                limit=limit,
                offset=offset,
            )
        )

    return [calendar_event_to_info(event) for event in events]


def create_calendar_event_with_service(
    session_factory: sessionmaker[Session],
    *,
    title: str,
    start_at: datetime,
    end_at: datetime,
    description: str = "",
    participants: list[dict[str, str]] | None = None,
) -> CalendarEventInfo:
    payload = CalendarEventCreate(
        title=title,
        description=description,
        start_at=start_at,
        end_at=end_at,
        participants=[
            Participant(name=participant["name"], email=participant["email"])
            for participant in participants or []
        ],
    )

    try:
        with calendar_event_service_scope(session_factory) as service:
            created = service.create(payload)
    except ConflictError as exc:
        raise ToolError(format_calendar_conflict_error(exc)) from exc

    return calendar_event_to_info(created)


def update_calendar_event_with_service(
    session_factory: sessionmaker[Session],
    *,
    event_id: str,
    title: str | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    description: str | None = None,
    location: str | None = None,
    participants: list[dict[str, str]] | None = None,
) -> CalendarEventInfo:
    update_values: dict[str, object] = {}
    if title is not None:
        update_values["title"] = title
    if start_at is not None:
        update_values["start_at"] = start_at
    if end_at is not None:
        update_values["end_at"] = end_at
    if description is not None:
        update_values["description"] = description
    if location is not None:
        update_values["location"] = location
    if participants is not None:
        update_values["participants"] = [
            Participant(name=participant["name"], email=participant["email"])
            for participant in participants
        ]
    if not update_values:
        msg = "At least one event field must be provided"
        raise ValueError(msg)

    payload = CalendarEventUpdate.model_validate(update_values)

    try:
        with calendar_event_service_scope(session_factory) as service:
            updated = service.update(event_id, payload)
    except ConflictError as exc:
        raise ToolError(format_calendar_conflict_error(exc)) from exc

    return calendar_event_to_info(updated)


def cancel_calendar_event_with_service(
    session_factory: sessionmaker[Session],
    *,
    event_id: str,
) -> CalendarEventInfo:
    with calendar_event_service_scope(session_factory) as service:
        cancelled = service.cancel(event_id)

    return calendar_event_to_info(cancelled)


@contextmanager
def calendar_event_service_scope(
    session_factory: sessionmaker[Session],
) -> Generator[CalendarEventService]:
    with session_scope(session_factory) as session:
        yield CalendarEventService(CalendarEventRepository(session))


def validate_local_datetime_range(start_at: datetime, end_at: datetime) -> None:
    require_naive(start_at, "start_at")
    require_naive(end_at, "end_at")
    if end_at <= start_at:
        msg = "Range end time must be later than range start time"
        raise ValueError(msg)


def validate_pagination(limit: int, offset: int) -> None:
    if limit < 1 or limit > 500:
        msg = "limit must be between 1 and 500"
        raise ValueError(msg)
    if offset < 0:
        msg = "offset must be greater than or equal to 0"
        raise ValueError(msg)


def format_calendar_conflict_error(exc: ConflictError) -> str:
    raw_ids = exc.details.get("conflicting_event_ids", [])
    conflicting_event_ids = (
        [str(event_id) for event_id in raw_ids] if isinstance(raw_ids, list) else []
    )
    return (
        f"{exc.code.value}: {exc.message}. "
        f"conflicting_event_ids={json.dumps(conflicting_event_ids)}"
    )


def calendar_event_to_info(event: CalendarEventRead) -> CalendarEventInfo:
    return {
        "id": event.id,
        "title": event.title,
        "description": event.description,
        "start_at": event.start_at.isoformat(),
        "end_at": event.end_at.isoformat(),
        "status": event.status.value,
        "location": event.location,
        "participants": [
            {"name": participant.name, "email": participant.email}
            for participant in event.participants
        ],
        "created_at": event.created_at.isoformat(),
        "updated_at": event.updated_at.isoformat(),
    }
