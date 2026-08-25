from datetime import datetime
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from apps.todo_app.models import TaskPriority, TaskStatus
from shared.datetime import require_aware


def new_task_id() -> str:
    return str(uuid4())


class TaskBase(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=20_000)
    priority: TaskPriority = TaskPriority.NORMAL

    model_config = ConfigDict(extra="forbid")


class TaskCreate(TaskBase):
    id: str = Field(default_factory=new_task_id)


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=20_000)
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    completed_at: datetime | None = None

    @field_validator("completed_at")
    @classmethod
    def validate_datetime(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return require_aware(value)

    model_config = ConfigDict(extra="forbid")


class TaskRead(TaskBase):
    id: str
    status: TaskStatus
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
