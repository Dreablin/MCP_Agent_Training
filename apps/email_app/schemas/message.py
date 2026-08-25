from datetime import datetime
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from apps.email_app.models import EmailFolder
from shared.datetime import now_utc, require_aware


def new_message_id() -> str:
    return str(uuid4())


class EmailMessageBase(BaseModel):
    sender_name: str = Field(min_length=1, max_length=200)
    sender_email: str = Field(min_length=3, max_length=320)
    recipient_email: str = Field(min_length=3, max_length=320)
    subject: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=20_000)
    received_at: datetime = Field(default_factory=now_utc)

    @field_validator("sender_email", "recipient_email")
    @classmethod
    def validate_basic_email(cls, value: str) -> str:
        if "@" not in value:
            msg = "Email address must contain @"
            raise ValueError(msg)
        return value

    @field_validator("received_at")
    @classmethod
    def validate_received_at(cls, value: datetime) -> datetime:
        return require_aware(value, "received_at")


class EmailMessageCreate(EmailMessageBase):
    id: str = Field(default_factory=new_message_id)


class EmailMessageMove(BaseModel):
    folder: EmailFolder


class EmailFolderRead(BaseModel):
    id: EmailFolder
    label: str


class EmailMessageRead(EmailMessageBase):
    id: str
    folder: EmailFolder
    is_read: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
