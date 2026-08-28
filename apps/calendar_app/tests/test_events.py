import pytest

from apps.calendar_app.events import CalendarEvent, CalendarEventBus
from apps.calendar_app.models import CalendarEventStatus


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_calendar_event_bus_publishes_to_subscription() -> None:
    event_bus = CalendarEventBus()
    subscription = event_bus.subscribe()
    event = CalendarEvent(
        action="cancelled",
        event_id="event-1",
        status=CalendarEventStatus.CANCELLED,
    )

    event_bus.publish(event)

    assert await subscription.get() == event
    assert event.as_dict() == {
        "action": "cancelled",
        "event_id": "event-1",
        "status": "cancelled",
    }
    event_bus.unsubscribe(subscription)
