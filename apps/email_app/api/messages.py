from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.sse import EventSourceResponse, ServerSentEvent

from apps.email_app.api.dependencies import get_email_event_bus, get_email_service
from apps.email_app.events import EmailEventBus
from apps.email_app.models import EmailFolder
from apps.email_app.repositories import EmailSearch
from apps.email_app.schemas import (
    EmailFolderRead,
    EmailMessageCreate,
    EmailMessageMove,
    EmailMessageRead,
)
from apps.email_app.services import EmailMessageService

router = APIRouter(prefix="/api/messages", tags=["email messages"])


@router.post("", response_model=EmailMessageRead, status_code=status.HTTP_201_CREATED)
def create_message(
    payload: EmailMessageCreate,
    service: Annotated[EmailMessageService, Depends(get_email_service)],
) -> EmailMessageRead:
    return service.create(payload)


@router.post("/send", response_model=EmailMessageRead, status_code=status.HTTP_201_CREATED)
def send_message(
    payload: EmailMessageCreate,
    service: Annotated[EmailMessageService, Depends(get_email_service)],
) -> EmailMessageRead:
    return service.create_sent(payload)


@router.get("", response_model=list[EmailMessageRead])
def list_messages(
    service: Annotated[EmailMessageService, Depends(get_email_service)],
    query: Annotated[str | None, Query(max_length=300)] = None,
    folder: EmailFolder | None = None,
    is_read: bool | None = None,
    sender: Annotated[str | None, Query(max_length=320)] = None,
    subject: Annotated[str | None, Query(max_length=300)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[EmailMessageRead]:
    return service.list(
        EmailSearch(
            query=query,
            folder=folder,
            is_read=is_read,
            sender=sender,
            subject=subject,
            limit=limit,
            offset=offset,
        )
    )


@router.delete("/trash", status_code=status.HTTP_200_OK)
def empty_trash(
    service: Annotated[EmailMessageService, Depends(get_email_service)],
) -> dict[str, int]:
    return service.empty_trash()


@router.get("/folders", response_model=list[EmailFolderRead])
def list_folders(
    service: Annotated[EmailMessageService, Depends(get_email_service)],
) -> list[EmailFolderRead]:
    return service.list_folders()


@router.get("/events", response_class=EventSourceResponse)
async def stream_message_events(
    request: Request,
    event_bus: Annotated[EmailEventBus, Depends(get_email_event_bus)],
) -> AsyncIterator[ServerSentEvent]:
    subscription = event_bus.subscribe()
    try:
        yield ServerSentEvent(event="connected", data={"status": "ok"})
        while True:
            event = await subscription.get()
            if await request.is_disconnected():
                break
            yield ServerSentEvent(event="messages_changed", data=event.as_dict())
    finally:
        event_bus.unsubscribe(subscription)


@router.get("/{message_id}", response_model=EmailMessageRead)
def get_message(
    message_id: str,
    service: Annotated[EmailMessageService, Depends(get_email_service)],
) -> EmailMessageRead:
    return service.get(message_id)


@router.post("/{message_id}/read", response_model=EmailMessageRead)
def mark_read(
    message_id: str,
    service: Annotated[EmailMessageService, Depends(get_email_service)],
) -> EmailMessageRead:
    return service.mark_read(message_id, True)


@router.post("/{message_id}/unread", response_model=EmailMessageRead)
def mark_unread(
    message_id: str,
    service: Annotated[EmailMessageService, Depends(get_email_service)],
) -> EmailMessageRead:
    return service.mark_read(message_id, False)


@router.post("/{message_id}/move", response_model=EmailMessageRead)
def move_message_to_folder(
    message_id: str,
    payload: EmailMessageMove,
    service: Annotated[EmailMessageService, Depends(get_email_service)],
) -> EmailMessageRead:
    return service.move_to_folder(message_id, payload.folder)


@router.delete("/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_message_from_trash(
    message_id: str,
    service: Annotated[EmailMessageService, Depends(get_email_service)],
) -> Response:
    service.delete_from_trash(message_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
