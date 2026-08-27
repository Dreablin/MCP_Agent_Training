from datetime import datetime, timedelta

import pytest
from mcp.server.mcpserver.exceptions import ToolError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from apps.calendar_app.database import Base
from apps.calendar_app.mcp_server import create_mcp_server
from apps.calendar_app.mcp_tools import (
    calendar_event_service_scope,
    cancel_calendar_event_with_service,
    create_calendar_event_with_service,
    list_calendar_events_with_service,
    search_calendar_events_with_service,
    update_calendar_event_with_service,
)
from apps.calendar_app.models import CalendarEventStatus
from apps.calendar_app.schemas import CalendarEventCreate, Participant


@pytest.mark.anyio
async def test_calendar_mcp_server_registers_tools() -> None:
    engine = create_engine("sqlite:///:memory:")
    session_factory: sessionmaker[Session] = sessionmaker(bind=engine, expire_on_commit=False)

    mcp = create_mcp_server(session_factory)
    tools = await mcp.list_tools()

    assert mcp.name == "Calendar MCP server"
    tools_by_name = {tool.name: tool for tool in tools}

    list_tool = tools_by_name["list_calendar_events"]
    assert list_tool.title == "List calendar events"
    assert list_tool.annotations is not None
    assert list_tool.annotations.read_only_hint is True
    assert list_tool.annotations.open_world_hint is False

    search_tool = tools_by_name["search_calendar_events"]
    assert search_tool.title == "Search calendar events"
    assert search_tool.annotations is not None
    assert search_tool.annotations.read_only_hint is True
    assert search_tool.annotations.open_world_hint is False

    create_tool = tools_by_name["create_calendar_event"]
    assert create_tool.title == "Create calendar event"
    assert create_tool.annotations is not None
    assert create_tool.annotations.read_only_hint is False
    assert create_tool.annotations.destructive_hint is False
    assert create_tool.annotations.idempotent_hint is False
    assert create_tool.annotations.open_world_hint is False

    update_tool = tools_by_name["update_calendar_event"]
    assert update_tool.title == "Update calendar event"
    assert update_tool.annotations is not None
    assert update_tool.annotations.read_only_hint is False
    assert update_tool.annotations.destructive_hint is False
    assert update_tool.annotations.idempotent_hint is False
    assert update_tool.annotations.open_world_hint is False

    cancel_tool = tools_by_name["cancel_calendar_event"]
    assert cancel_tool.title == "Cancel calendar event"
    assert cancel_tool.annotations is not None
    assert cancel_tool.annotations.read_only_hint is False
    assert cancel_tool.annotations.destructive_hint is False
    assert cancel_tool.annotations.idempotent_hint is False
    assert cancel_tool.annotations.open_world_hint is False


def test_calendar_mcp_service_scope_uses_session_factory_per_call() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory: sessionmaker[Session] = sessionmaker(bind=engine, expire_on_commit=False)
    start_at = datetime(2026, 8, 26, 10, 0)

    with calendar_event_service_scope(session_factory) as service:
        created = service.create(
            CalendarEventCreate(
                title="Planning",
                start_at=start_at,
                end_at=start_at + timedelta(hours=1),
            )
        )

    with calendar_event_service_scope(session_factory) as service:
        events = service.list_events()

    assert [event.id for event in events] == [created.id]


def test_create_calendar_event_tool_uses_service_layer() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory: sessionmaker[Session] = sessionmaker(bind=engine, expire_on_commit=False)

    event = create_calendar_event_with_service(
        session_factory,
        title="Planning",
        description="Discuss next steps.",
        start_at=datetime(2026, 8, 26, 10, 0),
        end_at=datetime(2026, 8, 26, 11, 0),
        participants=[
            {"name": "Anna", "email": "anna@example.test"},
            {"name": "Dmitry", "email": "dmitry@example.test"},
        ],
    )

    assert event["title"] == "Planning"
    assert event["description"] == "Discuss next steps."
    assert "timezone" not in event
    assert event["status"] == "confirmed"
    assert event["location"] == ""
    assert event["participants"] == [
        {"name": "Anna", "email": "anna@example.test"},
        {"name": "Dmitry", "email": "dmitry@example.test"},
    ]

    with calendar_event_service_scope(session_factory) as service:
        stored = service.get(event["id"])

    assert stored.title == "Planning"
    assert stored.start_at == datetime(2026, 8, 26, 10, 0)
    assert event["start_at"] == "2026-08-26T10:00:00"


def test_create_calendar_event_tool_reports_overlap_conflict() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory: sessionmaker[Session] = sessionmaker(bind=engine, expire_on_commit=False)

    existing = create_calendar_event_with_service(
        session_factory,
        title="Planning",
        start_at=datetime(2026, 8, 26, 10, 0),
        end_at=datetime(2026, 8, 26, 11, 0),
    )

    with pytest.raises(ToolError) as exc_info:
        create_calendar_event_with_service(
            session_factory,
            title="Overlapping planning",
            start_at=datetime(2026, 8, 26, 10, 30),
            end_at=datetime(2026, 8, 26, 11, 30),
        )

    message = str(exc_info.value)
    assert "CONFLICT: Calendar event overlaps with an existing event." in message
    assert f'conflicting_event_ids=["{existing["id"]}"]' in message


def test_list_calendar_events_tool_returns_events_overlapping_range() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory: sessionmaker[Session] = sessionmaker(bind=engine, expire_on_commit=False)

    with calendar_event_service_scope(session_factory) as service:
        service.create(
            CalendarEventCreate(
                title="Morning",
                start_at=datetime(2026, 8, 26, 9, 0),
                end_at=datetime(2026, 8, 26, 10, 0),
            )
        )
        service.create(
            CalendarEventCreate(
                title="Planning",
                start_at=datetime(2026, 8, 26, 10, 0),
                end_at=datetime(2026, 8, 26, 11, 0),
            )
        )
        service.create(
            CalendarEventCreate(
                title="Cancelled",
                start_at=datetime(2026, 8, 26, 10, 30),
                end_at=datetime(2026, 8, 26, 11, 30),
                status=CalendarEventStatus.CANCELLED,
            )
        )
        service.create(
            CalendarEventCreate(
                title="Lunch",
                start_at=datetime(2026, 8, 26, 12, 0),
                end_at=datetime(2026, 8, 26, 13, 0),
            )
        )
        service.create(
            CalendarEventCreate(
                title="Outside",
                start_at=datetime(2026, 8, 26, 16, 0),
                end_at=datetime(2026, 8, 26, 17, 0),
            )
        )

    events = list_calendar_events_with_service(
        session_factory,
        start_at=datetime(2026, 8, 26, 9, 30),
        end_at=datetime(2026, 8, 26, 12, 30),
    )
    paged_events = list_calendar_events_with_service(
        session_factory,
        start_at=datetime(2026, 8, 26, 9, 30),
        end_at=datetime(2026, 8, 26, 12, 30),
        limit=2,
        offset=1,
    )
    events_with_cancelled = list_calendar_events_with_service(
        session_factory,
        start_at=datetime(2026, 8, 26, 9, 30),
        end_at=datetime(2026, 8, 26, 12, 30),
        include_cancelled=True,
    )

    assert [event["title"] for event in events] == ["Morning", "Planning", "Lunch"]
    assert [event["title"] for event in paged_events] == ["Planning", "Lunch"]
    assert [event["title"] for event in events_with_cancelled] == [
        "Morning",
        "Planning",
        "Cancelled",
        "Lunch",
    ]
    assert all("timezone" not in event for event in events)


def test_search_calendar_events_tool_searches_text_and_participants() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory: sessionmaker[Session] = sessionmaker(bind=engine, expire_on_commit=False)

    with calendar_event_service_scope(session_factory) as service:
        service.create(
            CalendarEventCreate(
                title="Planning",
                description="Discuss project next steps.",
                start_at=datetime(2026, 8, 26, 10, 0),
                end_at=datetime(2026, 8, 26, 11, 0),
                participants=[Participant(name="Anna", email="anna@example.test")],
            )
        )
        service.create(
            CalendarEventCreate(
                title="Veterinary appointment",
                description="Meeting about dogs and training.",
                start_at=datetime(2026, 8, 27, 12, 0),
                end_at=datetime(2026, 8, 27, 13, 0),
            )
        )
        cancelled = service.create(
            CalendarEventCreate(
                title="Cancelled Anna call",
                start_at=datetime(2026, 8, 28, 12, 0),
                end_at=datetime(2026, 8, 28, 13, 0),
                participants=[Participant(name="Anna", email="anna@example.test")],
            )
        )
        service.cancel(cancelled.id)

    anna_events = search_calendar_events_with_service(session_factory, query="anna")
    email_events = search_calendar_events_with_service(session_factory, query="anna@example.test")
    description_events = search_calendar_events_with_service(session_factory, query="dogs")
    anna_events_with_cancelled = search_calendar_events_with_service(
        session_factory,
        query="anna",
        include_cancelled=True,
    )

    assert [event["title"] for event in anna_events] == ["Planning"]
    assert [event["title"] for event in email_events] == ["Planning"]
    assert [event["title"] for event in description_events] == ["Veterinary appointment"]
    assert [event["title"] for event in anna_events_with_cancelled] == [
        "Planning",
        "Cancelled Anna call",
    ]
    assert all("timezone" not in event for event in anna_events_with_cancelled)


def test_search_calendar_events_tool_rejects_empty_query() -> None:
    engine = create_engine("sqlite:///:memory:")
    session_factory: sessionmaker[Session] = sessionmaker(bind=engine, expire_on_commit=False)

    with pytest.raises(ValueError, match="query must not be empty"):
        search_calendar_events_with_service(session_factory, query="   ")


def test_update_calendar_event_tool_updates_existing_event() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory: sessionmaker[Session] = sessionmaker(bind=engine, expire_on_commit=False)

    created = create_calendar_event_with_service(
        session_factory,
        title="Planning",
        start_at=datetime(2026, 8, 26, 10, 0),
        end_at=datetime(2026, 8, 26, 11, 0),
    )

    updated = update_calendar_event_with_service(
        session_factory,
        event_id=created["id"],
        title="Updated planning",
        description="Discuss calendar MCP tools.",
        start_at=datetime(2026, 8, 26, 12, 0),
        end_at=datetime(2026, 8, 26, 13, 0),
        location="Office",
        participants=[{"name": "Anna", "email": "anna@example.test"}],
    )

    assert updated["id"] == created["id"]
    assert updated["title"] == "Updated planning"
    assert updated["description"] == "Discuss calendar MCP tools."
    assert updated["start_at"] == "2026-08-26T12:00:00"
    assert updated["end_at"] == "2026-08-26T13:00:00"
    assert updated["location"] == "Office"
    assert updated["participants"] == [{"name": "Anna", "email": "anna@example.test"}]
    assert "timezone" not in updated

    with calendar_event_service_scope(session_factory) as service:
        stored = service.get(created["id"])

    assert stored.title == "Updated planning"
    assert stored.start_at == datetime(2026, 8, 26, 12, 0)


def test_update_calendar_event_tool_reports_overlap_conflict() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory: sessionmaker[Session] = sessionmaker(bind=engine, expire_on_commit=False)

    existing = create_calendar_event_with_service(
        session_factory,
        title="Planning",
        start_at=datetime(2026, 8, 26, 10, 0),
        end_at=datetime(2026, 8, 26, 11, 0),
    )
    moving = create_calendar_event_with_service(
        session_factory,
        title="Sales call",
        start_at=datetime(2026, 8, 26, 12, 0),
        end_at=datetime(2026, 8, 26, 13, 0),
    )

    with pytest.raises(ToolError) as exc_info:
        update_calendar_event_with_service(
            session_factory,
            event_id=moving["id"],
            start_at=datetime(2026, 8, 26, 10, 30),
            end_at=datetime(2026, 8, 26, 11, 30),
        )

    message = str(exc_info.value)
    assert "CONFLICT: Calendar event overlaps with an existing event." in message
    assert f'conflicting_event_ids=["{existing["id"]}"]' in message


def test_update_calendar_event_tool_requires_at_least_one_field() -> None:
    engine = create_engine("sqlite:///:memory:")
    session_factory: sessionmaker[Session] = sessionmaker(bind=engine, expire_on_commit=False)

    with pytest.raises(ValueError, match="At least one event field"):
        update_calendar_event_with_service(session_factory, event_id="missing")


def test_cancel_calendar_event_tool_cancels_existing_event() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory: sessionmaker[Session] = sessionmaker(bind=engine, expire_on_commit=False)

    created = create_calendar_event_with_service(
        session_factory,
        title="Planning",
        start_at=datetime(2026, 8, 26, 10, 0),
        end_at=datetime(2026, 8, 26, 11, 0),
    )

    cancelled = cancel_calendar_event_with_service(
        session_factory,
        event_id=created["id"],
    )

    assert cancelled["id"] == created["id"]
    assert cancelled["status"] == "cancelled"
    assert "timezone" not in cancelled

    with calendar_event_service_scope(session_factory) as service:
        stored = service.get(created["id"])

    assert stored.status.value == "cancelled"
