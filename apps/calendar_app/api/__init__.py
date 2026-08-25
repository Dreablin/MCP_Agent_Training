"""API routes for Calendar App."""

from apps.calendar_app.api.events import router as events_router

__all__ = ["events_router"]
