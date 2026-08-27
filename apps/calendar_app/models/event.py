from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from apps.calendar_app.database import Base
from shared.datetime import now_local_naive
from shared.sqlalchemy_types import LocalNaiveDateTime


class CalendarEventStatus(StrEnum):
    CONFIRMED = "confirmed"
    TENTATIVE = "tentative"
    CANCELLED = "cancelled"


class CalendarEvent(Base):
    __tablename__ = "calendar_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    start_at: Mapped[datetime] = mapped_column(LocalNaiveDateTime(), nullable=False)
    end_at: Mapped[datetime] = mapped_column(LocalNaiveDateTime(), nullable=False)
    timezone: Mapped[str] = mapped_column(String(100), nullable=False, default="local")
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=CalendarEventStatus.CONFIRMED.value,
    )
    location: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    participants: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        LocalNaiveDateTime(),
        nullable=False,
        default=now_local_naive,
    )
    updated_at: Mapped[datetime] = mapped_column(
        LocalNaiveDateTime(),
        nullable=False,
        default=now_local_naive,
        onupdate=now_local_naive,
    )
