from datetime import datetime
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from apps.calendar_app.models import CalendarEventStatus
from shared.datetime import get_timezone, require_aware


def new_event_id() -> str:
    return str(uuid4())


class Participant(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=320)

    @field_validator("email")
    @classmethod
    def validate_basic_email(cls, value: str) -> str:
        if "@" not in value:
            msg = "Email address must contain @"
            raise ValueError(msg)
        return value


class CalendarEventBase(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=20_000)
    start_at: datetime
    end_at: datetime
    timezone: str = "local"
    status: CalendarEventStatus = CalendarEventStatus.CONFIRMED
    location: str = Field(default="", max_length=300)
    participants: list[Participant] = Field(default_factory=list)

    @field_validator("start_at", "end_at")
    @classmethod
    def validate_datetime(cls, value: datetime) -> datetime:
        return require_aware(value)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        if value == "local":
            return value
        get_timezone(value)
        return value

    @model_validator(mode="after")
    def validate_time_range(self) -> "CalendarEventBase":
        if self.end_at <= self.start_at:
            msg = "Event end time must be later than start time"
            raise ValueError(msg)
        return self


class CalendarEventCreate(CalendarEventBase):
    id: str = Field(default_factory=new_event_id)


class CalendarEventUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=20_000)
    start_at: datetime | None = None
    end_at: datetime | None = None
    timezone: str | None = None
    status: CalendarEventStatus | None = None
    location: str | None = Field(default=None, max_length=300)
    participants: list[Participant] | None = None

    @field_validator("start_at", "end_at")
    @classmethod
    def validate_datetime(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return require_aware(value)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value == "local":
            return value
        get_timezone(value)
        return value


class CalendarEventRead(CalendarEventBase):
    id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
