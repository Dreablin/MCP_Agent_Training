from __future__ import annotations

import asyncio
from dataclasses import dataclass
from threading import Lock
from typing import Any

from apps.calendar_app.models import CalendarEventStatus


@dataclass(frozen=True)
class CalendarEvent:
    action: str
    event_id: str | None = None
    status: CalendarEventStatus | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "event_id": self.event_id,
            "status": self.status.value if self.status is not None else None,
        }


class CalendarEventSubscription:
    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        self._queue: asyncio.Queue[CalendarEvent] = asyncio.Queue()

    async def get(self) -> CalendarEvent:
        return await self._queue.get()

    def publish(self, event: CalendarEvent) -> None:
        self._loop.call_soon_threadsafe(self._queue.put_nowait, event)


class CalendarEventBus:
    def __init__(self) -> None:
        self._lock = Lock()
        self._subscriptions: set[CalendarEventSubscription] = set()

    def subscribe(self) -> CalendarEventSubscription:
        subscription = CalendarEventSubscription(asyncio.get_running_loop())
        with self._lock:
            self._subscriptions.add(subscription)
        return subscription

    def unsubscribe(self, subscription: CalendarEventSubscription) -> None:
        with self._lock:
            self._subscriptions.discard(subscription)

    def publish(self, event: CalendarEvent) -> None:
        with self._lock:
            subscriptions = list(self._subscriptions)
        for subscription in subscriptions:
            subscription.publish(event)
