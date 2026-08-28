from __future__ import annotations

import builtins

from apps.todo_app.events import TaskEvent
from apps.todo_app.models import TaskStatus
from apps.todo_app.repositories import TaskRepository, TaskSearch
from apps.todo_app.schemas import TaskCreate, TaskRead, TaskUpdate
from shared.datetime import now_utc
from shared.errors import NotFoundError


class TaskService:
    def __init__(self, repository: TaskRepository) -> None:
        self._repository = repository
        self._events: list[TaskEvent] = []

    def create(self, payload: TaskCreate) -> TaskRead:
        task = self._to_read_model(self._repository.create(payload))
        self._record_event("created", task)
        return task

    def list(self, search: TaskSearch | None = None) -> list[TaskRead]:
        return [self._to_read_model(task) for task in self._repository.list(search)]

    def get(self, task_id: str) -> TaskRead:
        task = self._repository.get(task_id)
        if task is None:
            raise NotFoundError("Task not found", details={"id": task_id})
        return self._to_read_model(task)

    def update(self, task_id: str, payload: TaskUpdate) -> TaskRead:
        values = payload.model_dump(exclude_unset=True)
        self._apply_status_rules(values)
        task = self._repository.update(task_id, values)
        if task is None:
            raise NotFoundError("Task not found", details={"id": task_id})
        updated_task = self._to_read_model(task)
        self._record_event("updated", updated_task)
        return updated_task

    def complete(self, task_id: str) -> TaskRead:
        task = self.update(task_id, TaskUpdate(status=TaskStatus.COMPLETED))
        self._events[-1] = TaskEvent(
            action="completed",
            task_id=task.id,
            status=task.status,
            priority=task.priority,
        )
        return task

    def reopen(self, task_id: str) -> TaskRead:
        task = self.update(task_id, TaskUpdate(status=TaskStatus.OPEN))
        self._events[-1] = TaskEvent(
            action="reopened",
            task_id=task.id,
            status=task.status,
            priority=task.priority,
        )
        return task

    def cancel(self, task_id: str) -> TaskRead:
        task = self.update(task_id, TaskUpdate(status=TaskStatus.CANCELLED))
        self._events[-1] = TaskEvent(
            action="cancelled",
            task_id=task.id,
            status=task.status,
            priority=task.priority,
        )
        return task

    def pull_events(self) -> builtins.list[TaskEvent]:
        events = list(self._events)
        self._events.clear()
        return events

    @staticmethod
    def _apply_status_rules(values: dict[str, object]) -> None:
        status = values.get("status")
        if status == TaskStatus.COMPLETED:
            values.setdefault("completed_at", now_utc())
        elif status in {TaskStatus.OPEN, TaskStatus.IN_PROGRESS, TaskStatus.CANCELLED}:
            values["completed_at"] = None

    @staticmethod
    def _to_read_model(task: object) -> TaskRead:
        return TaskRead.model_validate(task)

    def _record_event(self, action: str, task: TaskRead) -> None:
        self._events.append(
            TaskEvent(
                action=action,
                task_id=task.id,
                status=task.status,
                priority=task.priority,
            )
        )
