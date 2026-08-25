from dataclasses import dataclass
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from apps.todo_app.models import Task, TaskPriority, TaskStatus
from apps.todo_app.schemas import TaskCreate
from shared.datetime import now_utc


@dataclass(frozen=True)
class TaskSearch:
    query: str | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    limit: int = 100
    offset: int = 0


class TaskRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, task: TaskCreate) -> Task:
        db_task = Task(
            id=task.id,
            title=task.title,
            description=task.description,
            status=TaskStatus.OPEN.value,
            priority=task.priority.value,
        )
        self._session.add(db_task)
        self._session.flush()
        self._session.refresh(db_task)
        return db_task

    def get(self, task_id: str) -> Task | None:
        return self._session.get(Task, task_id)

    def list(self, search: TaskSearch | None = None) -> list[Task]:
        criteria = search or TaskSearch()
        statement = self._apply_search(select(Task), criteria)
        statement = statement.order_by(
            Task.created_at.desc(),
        )
        statement = statement.offset(criteria.offset).limit(criteria.limit)
        return list(self._session.scalars(statement).all())

    def update(self, task_id: str, values: dict[str, Any]) -> Task | None:
        db_task = self.get(task_id)
        if db_task is None:
            return None

        allowed_fields = {
            "title",
            "description",
            "status",
            "priority",
            "completed_at",
        }
        for field_name, value in values.items():
            if field_name not in allowed_fields:
                continue
            if isinstance(value, TaskStatus | TaskPriority):
                value = value.value
            setattr(db_task, field_name, value)
        db_task.updated_at = now_utc()
        self._session.flush()
        self._session.refresh(db_task)
        return db_task

    def count(self) -> int:
        return self._session.scalar(select(func.count()).select_from(Task)) or 0

    def _apply_search(
        self,
        statement: Select[tuple[Task]],
        search: TaskSearch,
    ) -> Select[tuple[Task]]:
        if search.status is not None:
            statement = statement.where(Task.status == search.status.value)
        if search.priority is not None:
            statement = statement.where(Task.priority == search.priority.value)
        if search.query:
            query_pattern = self._like(search.query)
            statement = statement.where(
                or_(
                    func.lower(Task.title).like(query_pattern),
                    func.lower(Task.description).like(query_pattern),
                )
            )
        return statement

    @staticmethod
    def _like(value: str) -> str:
        return f"%{value.lower()}%"
