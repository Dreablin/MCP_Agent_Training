from __future__ import annotations

import asyncio
from dataclasses import dataclass
from threading import Lock
from typing import Any

from apps.todo_app.models import TaskPriority, TaskStatus


@dataclass(frozen=True)
class TaskEvent:
    action: str
    task_id: str | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "task_id": self.task_id,
            "status": self.status.value if self.status is not None else None,
            "priority": self.priority.value if self.priority is not None else None,
        }


class TaskEventSubscription:
    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        self._queue: asyncio.Queue[TaskEvent] = asyncio.Queue()

    async def get(self) -> TaskEvent:
        return await self._queue.get()

    def publish(self, event: TaskEvent) -> None:
        self._loop.call_soon_threadsafe(self._queue.put_nowait, event)


class TaskEventBus:
    def __init__(self) -> None:
        self._lock = Lock()
        self._subscriptions: set[TaskEventSubscription] = set()

    def subscribe(self) -> TaskEventSubscription:
        subscription = TaskEventSubscription(asyncio.get_running_loop())
        with self._lock:
            self._subscriptions.add(subscription)
        return subscription

    def unsubscribe(self, subscription: TaskEventSubscription) -> None:
        with self._lock:
            self._subscriptions.discard(subscription)

    def publish(self, event: TaskEvent) -> None:
        with self._lock:
            subscriptions = list(self._subscriptions)
        for subscription in subscriptions:
            subscription.publish(event)
