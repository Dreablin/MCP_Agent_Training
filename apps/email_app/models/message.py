from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from apps.email_app.database import Base
from shared.datetime import now_utc
from shared.sqlalchemy_types import UTCDateTime


class EmailFolder(StrEnum):
    INBOX = "inbox"
    SENT = "sent"
    SPAM = "spam"
    FRIENDS = "friends"
    WORK = "work"
    LOGS = "logs"
    TRASH = "trash"


class EmailMessage(Base):
    __tablename__ = "email_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    sender_name: Mapped[str] = mapped_column(String(200), nullable=False)
    sender_email: Mapped[str] = mapped_column(String(320), nullable=False)
    recipient_email: Mapped[str] = mapped_column(String(320), nullable=False)
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    received_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    folder: Mapped[str] = mapped_column(String(20), nullable=False, default=EmailFolder.INBOX.value)
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=now_utc,
        onupdate=now_utc,
    )
