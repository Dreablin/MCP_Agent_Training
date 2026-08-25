from collections.abc import Iterator
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.orm import Session

from apps.email_app.database import Base, build_engine, build_session_factory
from apps.email_app.models import EmailFolder
from apps.email_app.repositories import EmailMessageRepository, EmailSearch
from apps.email_app.schemas import EmailMessageCreate
from shared.datetime import UTC


@pytest.fixture
def session(tmp_path) -> Iterator[Session]:  # type: ignore[no-untyped-def]
    engine = build_engine(f"sqlite:///{(tmp_path / 'email.db').as_posix()}")
    Base.metadata.create_all(engine)
    session_factory = build_session_factory(engine)
    db_session = session_factory()
    try:
        yield db_session
    finally:
        db_session.close()
        engine.dispose()


def create_message(
    repository: EmailMessageRepository,
    *,
    subject: str = "Meeting with Anna",
    body: str = "Please prepare agenda for tomorrow.",
    sender_name: str = "Anna",
    sender_email: str = "anna@example.test",
) -> str:
    message = repository.create(
        EmailMessageCreate(
            sender_name=sender_name,
            sender_email=sender_email,
            recipient_email="me@example.test",
            subject=subject,
            body=body,
            received_at=datetime(2026, 8, 6, 12, 0, tzinfo=ZoneInfo("America/Chicago")),
        )
    )
    return message.id


def test_create_and_get_message(session: Session) -> None:
    repository = EmailMessageRepository(session)

    message_id = create_message(repository)
    session.commit()

    message = repository.get(message_id)
    assert message is not None
    assert message.subject == "Meeting with Anna"
    assert message.folder == EmailFolder.INBOX.value
    assert message.is_read is False
    assert message.received_at.tzinfo == UTC


def test_search_by_query_and_folder(session: Session) -> None:
    repository = EmailMessageRepository(session)
    create_message(repository, subject="Meeting with Anna", body="Calendar event")
    work_id = create_message(
        repository,
        subject="Weekly report",
        body="No event here",
        sender_name="Manager",
        sender_email="manager@example.test",
    )
    repository.update(work_id, {"folder": EmailFolder.WORK})
    session.commit()

    inbox_results = repository.list(EmailSearch(folder=EmailFolder.INBOX))
    query_results = repository.list(EmailSearch(query="weekly"))
    work_results = repository.list(EmailSearch(folder=EmailFolder.WORK))

    assert [message.subject for message in inbox_results] == ["Meeting with Anna"]
    assert [message.subject for message in query_results] == ["Weekly report"]
    assert [message.subject for message in work_results] == ["Weekly report"]


def test_update_read_status_and_folder(session: Session) -> None:
    repository = EmailMessageRepository(session)
    message_id = create_message(repository)

    updated = repository.update(message_id, {"is_read": True, "folder": EmailFolder.TRASH})
    session.commit()

    assert updated is not None
    assert updated.is_read is True
    assert updated.folder == EmailFolder.TRASH.value


def test_search_supports_additional_folders(session: Session) -> None:
    repository = EmailMessageRepository(session)
    message_id = create_message(repository, subject="Build log")
    repository.update(message_id, {"folder": EmailFolder.LOGS})
    session.commit()

    results = repository.list(EmailSearch(folder=EmailFolder.LOGS))

    assert [message.subject for message in results] == ["Build log"]


def test_empty_trash_deletes_only_trash_messages(session: Session) -> None:
    repository = EmailMessageRepository(session)
    inbox_id = create_message(repository, subject="Keep me")
    trash_id = create_message(repository, subject="Delete me")
    repository.update(trash_id, {"folder": EmailFolder.TRASH})
    session.commit()

    deleted_count = repository.empty_trash()
    session.commit()

    assert deleted_count == 1
    assert repository.get(inbox_id) is not None
    assert repository.get(trash_id) is None
