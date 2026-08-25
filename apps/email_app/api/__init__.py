"""API routes for Email app."""

from apps.email_app.api.messages import router as messages_router

__all__ = ["messages_router"]
