from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.orm import Session

from apps.email_app.database import Base, build_engine, build_session_factory
from apps.email_app.models import EmailFolder
from apps.email_app.repositories import EmailMessageRepository
from apps.email_app.schemas import EmailMessageCreate
from apps.email_app.services import EmailMessageService
from shared.errors import NotFoundError, ValidationAppError


@pytest.fixture
def service(tmp_path: Path) -> Iterator[EmailMessageService]:
    engine = build_engine(f"sqlite:///{(tmp_path / 'email.db').as_posix()}")
    Base.metadata.create_all(engine)
    session_factory = build_session_factory(engine)
    db_session: Session = session_factory()
    try:
        yield EmailMessageService(EmailMessageRepository(db_session))
    finally:
        db_session.close()
        engine.dispose()


def message_payload(subject: str = "Meeting with Anna") -> EmailMessageCreate:
    return EmailMessageCreate(
        sender_name="Anna",
        sender_email="anna@example.test",
        recipient_email="me@example.test",
        subject=subject,
        body="Let's meet tomorrow.",
        received_at=datetime(2026, 8, 6, 12, 0, tzinfo=ZoneInfo("America/Chicago")),
    )


def test_service_create_and_get(service: EmailMessageService) -> None:
    created = service.create(message_payload())

    found = service.get(created.id)

    assert found.id == created.id
    assert found.folder == EmailFolder.INBOX
    assert found.is_read is False


def test_service_create_sent_message(service: EmailMessageService) -> None:
    created = service.create_sent(message_payload("Project update"))

    sent_messages = service.list()

    assert created.folder == EmailFolder.SENT
    assert created.is_read is True
    assert [message.id for message in sent_messages] == [created.id]


def test_service_records_message_change_events(service: EmailMessageService) -> None:
    created = service.create(message_payload())
    read = service.mark_read(created.id, True)
    service.delete_permanently(created.id)

    events = service.pull_events()

    assert [event.action for event in events] == ["created", "updated", "deleted"]
    assert [event.message_id for event in events] == [created.id, read.id, created.id]
    assert [event.folder for event in events] == [
        EmailFolder.INBOX,
        EmailFolder.INBOX,
        EmailFolder.INBOX,
    ]
    assert service.pull_events() == []


def test_service_read_and_trash_flow(service: EmailMessageService) -> None:
    created = service.create(message_payload())

    read = service.mark_read(created.id, True)
    trashed = service.move_to_folder(created.id, EmailFolder.TRASH)

    assert read.is_read is True
    assert trashed.folder == EmailFolder.TRASH


def test_service_lists_folders(service: EmailMessageService) -> None:
    folders = service.list_folders()

    assert [folder.id for folder in folders] == [
        EmailFolder.INBOX,
        EmailFolder.SENT,
        EmailFolder.SPAM,
        EmailFolder.FRIENDS,
        EmailFolder.WORK,
        EmailFolder.LOGS,
        EmailFolder.TRASH,
    ]


def test_service_rejects_permanent_delete_outside_trash(service: EmailMessageService) -> None:
    created = service.create(message_payload())

    with pytest.raises(ValidationAppError):
        service.delete_from_trash(created.id)


def test_service_deletes_any_message_permanently(service: EmailMessageService) -> None:
    created = service.create(message_payload())

    service.delete_permanently(created.id)

    with pytest.raises(NotFoundError):
        service.get(created.id)


def test_service_raises_not_found(service: EmailMessageService) -> None:
    with pytest.raises(NotFoundError):
        service.get("missing")
