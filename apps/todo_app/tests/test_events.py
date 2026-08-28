import pytest

from apps.todo_app.events import TaskEvent, TaskEventBus
from apps.todo_app.models import TaskPriority, TaskStatus


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_task_event_bus_publishes_to_subscription() -> None:
    event_bus = TaskEventBus()
    subscription = event_bus.subscribe()
    event = TaskEvent(
        action="completed",
        task_id="task-1",
        status=TaskStatus.COMPLETED,
        priority=TaskPriority.HIGH,
    )

    event_bus.publish(event)

    assert await subscription.get() == event
    assert event.as_dict() == {
        "action": "completed",
        "task_id": "task-1",
        "status": "completed",
        "priority": "high",
    }
    event_bus.unsubscribe(subscription)
