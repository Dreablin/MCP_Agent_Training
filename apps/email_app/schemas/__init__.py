"""Pydantic schemas for Email app."""

from apps.email_app.schemas.message import (
    EmailFolderRead,
    EmailMessageCreate,
    EmailMessageMove,
    EmailMessageRead,
)

__all__ = ["EmailFolderRead", "EmailMessageCreate", "EmailMessageMove", "EmailMessageRead"]
