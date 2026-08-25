from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy import Select, delete, func, or_, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from apps.email_app.models import EmailFolder, EmailMessage
from apps.email_app.schemas import EmailMessageCreate
from shared.datetime import now_utc


@dataclass(frozen=True)
class EmailSearch:
    query: str | None = None
    folder: EmailFolder | None = None
    is_read: bool | None = None
    sender: str | None = None
    subject: str | None = None
    limit: int = 100
    offset: int = 0


class EmailMessageRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self,
        message: EmailMessageCreate,
        *,
        folder: EmailFolder = EmailFolder.INBOX,
        is_read: bool = False,
    ) -> EmailMessage:
        db_message = EmailMessage(
            id=message.id,
            sender_name=message.sender_name,
            sender_email=message.sender_email,
            recipient_email=message.recipient_email,
            subject=message.subject,
            body=message.body,
            received_at=message.received_at,
            folder=folder.value,
            is_read=is_read,
        )
        self._session.add(db_message)
        self._session.flush()
        self._session.refresh(db_message)
        return db_message

    def get(self, message_id: str) -> EmailMessage | None:
        return self._session.get(EmailMessage, message_id)

    def list(self, search: EmailSearch | None = None) -> list[EmailMessage]:
        criteria = search or EmailSearch()
        statement = self._apply_search(select(EmailMessage), criteria)
        statement = statement.order_by(
            EmailMessage.received_at.desc(),
            EmailMessage.created_at.desc(),
        )
        statement = statement.offset(criteria.offset).limit(criteria.limit)
        return list(self._session.scalars(statement).all())

    def update(self, message_id: str, values: dict[str, Any]) -> EmailMessage | None:
        db_message = self.get(message_id)
        if db_message is None:
            return None

        allowed_fields = {
            "sender_name",
            "sender_email",
            "recipient_email",
            "subject",
            "body",
            "received_at",
            "folder",
            "is_read",
        }
        for field_name, value in values.items():
            if field_name in allowed_fields and value is not None:
                if isinstance(value, EmailFolder):
                    value = value.value
                setattr(db_message, field_name, value)
        db_message.updated_at = now_utc()
        self._session.flush()
        self._session.refresh(db_message)
        return db_message

    def delete(self, message_id: str) -> bool:
        db_message = self.get(message_id)
        if db_message is None:
            return False
        self._session.delete(db_message)
        self._session.flush()
        return True

    def empty_trash(self) -> int:
        result = cast(
            CursorResult[Any],
            self._session.execute(
                delete(EmailMessage).where(EmailMessage.folder == EmailFolder.TRASH.value)
            ),
        )
        return int(result.rowcount or 0)

    def count(self) -> int:
        return self._session.scalar(select(func.count()).select_from(EmailMessage)) or 0

    def _apply_search(
        self,
        statement: Select[tuple[EmailMessage]],
        search: EmailSearch,
    ) -> Select[tuple[EmailMessage]]:
        if search.folder is not None:
            statement = statement.where(EmailMessage.folder == search.folder.value)
        if search.is_read is not None:
            statement = statement.where(EmailMessage.is_read.is_(search.is_read))
        if search.sender:
            sender_pattern = self._like(search.sender)
            statement = statement.where(
                or_(
                    func.lower(EmailMessage.sender_name).like(sender_pattern),
                    func.lower(EmailMessage.sender_email).like(sender_pattern),
                )
            )
        if search.subject:
            statement = statement.where(
                func.lower(EmailMessage.subject).like(self._like(search.subject))
            )
        if search.query:
            query_pattern = self._like(search.query)
            statement = statement.where(
                or_(
                    func.lower(EmailMessage.sender_name).like(query_pattern),
                    func.lower(EmailMessage.sender_email).like(query_pattern),
                    func.lower(EmailMessage.subject).like(query_pattern),
                    func.lower(EmailMessage.body).like(query_pattern),
                )
            )
        return statement

    @staticmethod
    def _like(value: str) -> str:
        return f"%{value.lower()}%"
