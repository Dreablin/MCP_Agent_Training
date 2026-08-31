"""Pydantic schemas for Email app."""

from apps.email_app.schemas.message import (
    EmailFolderRead,
    EmailMessageCreate,
    EmailMessageImport,
    EmailMessageMove,
    EmailMessageRead,
)

__all__ = [
    "EmailFolderRead",
    "EmailMessageCreate",
    "EmailMessageImport",
    "EmailMessageMove",
    "EmailMessageRead",
]
