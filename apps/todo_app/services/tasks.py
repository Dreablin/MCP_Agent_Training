from apps.todo_app.models import TaskStatus
from apps.todo_app.repositories import TaskRepository, TaskSearch
from apps.todo_app.schemas import TaskCreate, TaskRead, TaskUpdate
from shared.datetime import now_utc
from shared.errors import NotFoundError


class TaskService:
    def __init__(self, repository: TaskRepository) -> None:
        self._repository = repository

    def create(self, payload: TaskCreate) -> TaskRead:
        return self._to_read_model(self._repository.create(payload))

    def list(self, search: TaskSearch | None = None) -> list[TaskRead]:
        return [self._to_read_model(task) for task in self._repository.list(search)]

    def get(self, task_id: str) -> TaskRead:
        task = self._repository.get(task_id)
        if task is None:
            raise NotFoundError("Task not found", details={"id": task_id})
        return self._to_read_model(task)

    def update(self, task_id: str, payload: TaskUpdate) -> TaskRead:
        values = payload.model_dump(exclude_unset=True)
        self._apply_status_rules(values)
        task = self._repository.update(task_id, values)
        if task is None:
            raise NotFoundError("Task not found", details={"id": task_id})
        return self._to_read_model(task)

    def complete(self, task_id: str) -> TaskRead:
        return self.update(task_id, TaskUpdate(status=TaskStatus.COMPLETED))

    def reopen(self, task_id: str) -> TaskRead:
        return self.update(task_id, TaskUpdate(status=TaskStatus.OPEN))

    def cancel(self, task_id: str) -> TaskRead:
        return self.update(task_id, TaskUpdate(status=TaskStatus.CANCELLED))

    @staticmethod
    def _apply_status_rules(values: dict[str, object]) -> None:
        status = values.get("status")
        if status == TaskStatus.COMPLETED:
            values.setdefault("completed_at", now_utc())
        elif status in {TaskStatus.OPEN, TaskStatus.IN_PROGRESS, TaskStatus.CANCELLED}:
            values["completed_at"] = None

    @staticmethod
    def _to_read_model(task: object) -> TaskRead:
        return TaskRead.model_validate(task)
