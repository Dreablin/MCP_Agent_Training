from collections.abc import Generator
from typing import cast

from fastapi import Request
from sqlalchemy.orm import Session, sessionmaker

from apps.email_app.database import session_scope
from apps.email_app.events import EmailEventBus
from apps.email_app.repositories import EmailMessageRepository
from apps.email_app.services import EmailMessageService


def get_session(request: Request) -> Generator[Session]:
    session_factory: sessionmaker[Session] = request.app.state.session_factory
    with session_scope(session_factory) as session:
        yield session


def get_email_service(request: Request) -> Generator[EmailMessageService]:
    session_factory: sessionmaker[Session] = request.app.state.session_factory
    event_bus: EmailEventBus = request.app.state.email_event_bus
    service: EmailMessageService | None = None
    with session_scope(session_factory) as session:
        service = EmailMessageService(EmailMessageRepository(session))
        yield service
    assert service is not None
    for event in service.pull_events():
        event_bus.publish(event)


def get_email_event_bus(request: Request) -> EmailEventBus:
    return cast(EmailEventBus, request.app.state.email_event_bus)
