from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.sse import EventSourceResponse, ServerSentEvent

from apps.todo_app.api.dependencies import (
    get_task_command_runner,
    get_task_event_bus,
    get_task_service,
)
from apps.todo_app.command_runner import TaskCommandRunner
from apps.todo_app.events import TaskEventBus
from apps.todo_app.models import TaskPriority, TaskStatus
from apps.todo_app.repositories import TaskSearch
from apps.todo_app.schemas import TaskCreate, TaskRead, TaskUpdate
from apps.todo_app.services import TaskService

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
def create_task(
    payload: TaskCreate,
    command_runner: Annotated[TaskCommandRunner, Depends(get_task_command_runner)],
) -> TaskRead:
    return command_runner.run(lambda service: service.create(payload))


@router.get("", response_model=list[TaskRead])
def list_tasks(
    service: Annotated[TaskService, Depends(get_task_service)],
    query: Annotated[str | None, Query(max_length=300)] = None,
    status_filter: Annotated[TaskStatus | None, Query(alias="status")] = None,
    priority: TaskPriority | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[TaskRead]:
    return service.list(
        TaskSearch(
            query=query,
            status=status_filter,
            priority=priority,
            limit=limit,
            offset=offset,
        )
    )


@router.get("/events", response_class=EventSourceResponse)
async def stream_task_events(
    request: Request,
    event_bus: Annotated[TaskEventBus, Depends(get_task_event_bus)],
) -> AsyncIterator[ServerSentEvent]:
    subscription = event_bus.subscribe()
    try:
        yield ServerSentEvent(event="connected", data={"status": "ok"})
        while True:
            event = await subscription.get()
            if await request.is_disconnected():
                break
            yield ServerSentEvent(event="tasks_changed", data=event.as_dict())
    finally:
        event_bus.unsubscribe(subscription)


@router.get("/{task_id}", response_model=TaskRead)
def get_task(
    task_id: str,
    service: Annotated[TaskService, Depends(get_task_service)],
) -> TaskRead:
    return service.get(task_id)


@router.patch("/{task_id}", response_model=TaskRead)
def update_task(
    task_id: str,
    payload: TaskUpdate,
    command_runner: Annotated[TaskCommandRunner, Depends(get_task_command_runner)],
) -> TaskRead:
    return command_runner.run(lambda service: service.update(task_id, payload))


@router.post("/{task_id}/complete", response_model=TaskRead)
def complete_task(
    task_id: str,
    command_runner: Annotated[TaskCommandRunner, Depends(get_task_command_runner)],
) -> TaskRead:
    return command_runner.run(lambda service: service.complete(task_id))


@router.post("/{task_id}/reopen", response_model=TaskRead)
def reopen_task(
    task_id: str,
    command_runner: Annotated[TaskCommandRunner, Depends(get_task_command_runner)],
) -> TaskRead:
    return command_runner.run(lambda service: service.reopen(task_id))


@router.post("/{task_id}/cancel", response_model=TaskRead)
def cancel_task(
    task_id: str,
    command_runner: Annotated[TaskCommandRunner, Depends(get_task_command_runner)],
) -> TaskRead:
    return command_runner.run(lambda service: service.cancel(task_id))
