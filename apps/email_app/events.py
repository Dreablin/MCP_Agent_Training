from __future__ import annotations

import asyncio
from dataclasses import dataclass
from threading import Lock
from typing import Any

from apps.email_app.models import EmailFolder


@dataclass(frozen=True)
class EmailEvent:
    action: str
    message_id: str | None = None
    folder: EmailFolder | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "message_id": self.message_id,
            "folder": self.folder.value if self.folder is not None else None,
        }


class EmailEventSubscription:
    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        self._queue: asyncio.Queue[EmailEvent] = asyncio.Queue()

    async def get(self) -> EmailEvent:
        return await self._queue.get()

    def publish(self, event: EmailEvent) -> None:
        self._loop.call_soon_threadsafe(self._queue.put_nowait, event)


class EmailEventBus:
    def __init__(self) -> None:
        self._lock = Lock()
        self._subscriptions: set[EmailEventSubscription] = set()

    def subscribe(self) -> EmailEventSubscription:
        subscription = EmailEventSubscription(asyncio.get_running_loop())
        with self._lock:
            self._subscriptions.add(subscription)
        return subscription

    def unsubscribe(self, subscription: EmailEventSubscription) -> None:
        with self._lock:
            self._subscriptions.discard(subscription)

    def publish(self, event: EmailEvent) -> None:
        with self._lock:
            subscriptions = list(self._subscriptions)
        for subscription in subscriptions:
            subscription.publish(event)
