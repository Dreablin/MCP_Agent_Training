from collections.abc import Generator

from fastapi import Request
from sqlalchemy.orm import Session, sessionmaker

from apps.email_app.database import session_scope
from apps.email_app.repositories import EmailMessageRepository
from apps.email_app.services import EmailMessageService


def get_session(request: Request) -> Generator[Session]:
    session_factory: sessionmaker[Session] = request.app.state.session_factory
    with session_scope(session_factory) as session:
        yield session


def get_email_service(request: Request) -> Generator[EmailMessageService]:
    session_factory: sessionmaker[Session] = request.app.state.session_factory
    with session_scope(session_factory) as session:
        yield EmailMessageService(EmailMessageRepository(session))
