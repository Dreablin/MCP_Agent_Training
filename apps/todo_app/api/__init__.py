"""API routes for Todo App."""

from apps.todo_app.api.tasks import router as tasks_router

__all__ = ["tasks_router"]
