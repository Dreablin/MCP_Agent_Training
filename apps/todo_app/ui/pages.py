from collections.abc import Callable
from typing import TypeVar

from nicegui import ui
from nicegui.element import Element
from sqlalchemy.orm import Session, sessionmaker

from apps.todo_app.command_runner import TaskCommandRunner
from apps.todo_app.config import TodoAppSettings
from apps.todo_app.events import TaskEventBus
from apps.todo_app.models import TaskPriority, TaskStatus
from apps.todo_app.repositories import TaskSearch
from apps.todo_app.schemas import TaskCreate, TaskRead, TaskUpdate
from apps.todo_app.services import TaskService
from shared.errors import AppError

T = TypeVar("T")

TASK_VIEW_LABELS = {
    "open": "Open Tasks",
    "completed": "Completed",
    "cancelled": "Canceled",
}
TASK_STATUS_LABELS = {
    TaskStatus.OPEN: "Not Started",
    TaskStatus.IN_PROGRESS: "In Progress",
    TaskStatus.COMPLETED: "Completed",
    TaskStatus.CANCELLED: "Canceled",
}
TASK_PRIORITY_LABELS = {
    TaskPriority.LOW: "Low",
    TaskPriority.NORMAL: "Normal",
    TaskPriority.HIGH: "High",
    TaskPriority.URGENT: "Urgent",
}
TASK_PRIORITY_CLASSES = {
    TaskPriority.LOW: "priority-low",
    TaskPriority.NORMAL: "priority-normal",
    TaskPriority.HIGH: "priority-high",
    TaskPriority.URGENT: "priority-urgent",
}


def register_pages(
    settings: TodoAppSettings,
    session_factory: sessionmaker[Session],
    event_bus: TaskEventBus,
    command_runner: TaskCommandRunner | None = None,
) -> None:
    resolved_command_runner = command_runner or TaskCommandRunner(
        session_factory,
        event_bus,
    )

    def run_with_service(action: Callable[[TaskService], T]) -> T:
        return resolved_command_runner.run(action)

    def notify_error(exc: Exception) -> None:
        if isinstance(exc, AppError):
            ui.notify(exc.message, type="negative")
            return
        ui.notify(str(exc), type="negative")

    @ui.page("/")
    def index() -> None:
        selected_view = "open"
        current_view = "tasks"
        header_container: Element | None = None
        tabs_container: Element | None = None
        list_container: Element | None = None
        last_action = "Tasks are ready."

        ui.add_head_html(
            """
            <style>
                body {
                    margin: 0;
                    background: #f5f7fb;
                    color: #1f2937;
                }

                .todo-shell {
                    height: 100vh;
                    width: 100%;
                    gap: 0;
                    overflow: hidden;
                    font-family: Inter, Roboto, Arial, sans-serif;
                }

                .todo-toolbar {
                    width: 100%;
                    min-height: 58px;
                    padding: 8px 14px;
                    gap: 8px;
                    align-items: center;
                    border-bottom: 1px solid #d8dee9;
                    background: #ffffff;
                    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.08);
                }

                .todo-toolbar .q-btn {
                    border-radius: 6px;
                    min-height: 38px;
                    text-transform: none;
                    font-weight: 600;
                }

                .todo-main {
                    flex: 1;
                    width: 100%;
                    min-height: 0;
                    overflow: hidden;
                }

                .todo-view {
                    width: 100%;
                    height: 100%;
                    gap: 0;
                    background: #ffffff;
                    overflow: hidden;
                }

                .todo-header {
                    min-height: 78px;
                    padding: 14px 18px;
                    gap: 4px;
                    border-bottom: 1px solid #e5e7eb;
                    background: #fbfdff;
                }

                .todo-title {
                    color: #0f172a;
                    font-size: 18px;
                    font-weight: 700;
                    line-height: 1.25;
                }

                .todo-meta {
                    color: #64748b;
                    font-size: 12px;
                }

                .task-tabs {
                    width: 100%;
                    min-height: 50px;
                    padding: 8px 18px 0;
                    gap: 4px;
                    align-items: flex-end;
                    border-bottom: 1px solid #d8dee9;
                    background: #ffffff;
                }

                .task-tab {
                    min-height: 42px;
                    padding: 0 14px;
                    gap: 8px;
                    align-items: center;
                    border: 1px solid transparent;
                    border-bottom: 0;
                    border-radius: 6px 6px 0 0;
                    color: #475569;
                    cursor: pointer;
                    user-select: none;
                    font-weight: 600;
                }

                .task-tab:hover {
                    background: #f1f7fd;
                }

                .task-tab.active {
                    background: #ffffff;
                    border-color: #d8dee9;
                    color: #075985;
                    box-shadow: inset 0 3px 0 #1976d2;
                }

                .task-count {
                    min-width: 24px;
                    padding: 2px 7px;
                    border-radius: 999px;
                    background: #e2e8f0;
                    color: #334155;
                    text-align: center;
                    font-size: 12px;
                    font-weight: 700;
                }

                .task-tab.active .task-count {
                    background: #dbeafe;
                    color: #075985;
                }

                .task-list {
                    flex: 1;
                    min-height: 0;
                    width: 100%;
                    padding: 18px;
                    gap: 10px;
                    overflow-y: auto;
                    background: #ffffff;
                }

                .task-section {
                    width: 100%;
                    gap: 10px;
                }

                .task-section-header {
                    width: 100%;
                    align-items: center;
                    justify-content: space-between;
                    gap: 10px;
                }

                .task-section-title {
                    color: #0f172a;
                    font-size: 15px;
                    font-weight: 700;
                }

                .task-section-count,
                .task-section-empty {
                    color: #64748b;
                    font-size: 12px;
                }

                .task-list-separator {
                    width: 100%;
                    margin: 8px 0;
                    background: #d8dee9;
                }

                .task-tile {
                    width: 100%;
                    padding: 14px 16px;
                    gap: 10px;
                    border: 1px solid #dfe5ed;
                    border-left: 4px solid #1976d2;
                    border-radius: 8px;
                    background: #ffffff;
                    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.06);
                }

                .task-tile.completed {
                    border-left-color: #16a34a;
                }

                .task-tile.cancelled {
                    border-left-color: #94a3b8;
                    background: #f8fafc;
                }

                .task-tile-title {
                    overflow-wrap: anywhere;
                    color: #0f172a;
                    font-size: 15px;
                    font-weight: 700;
                    line-height: 1.35;
                }

                .task-tile-text {
                    overflow-wrap: anywhere;
                    white-space: pre-wrap;
                    color: #334155;
                    font-size: 14px;
                    line-height: 1.45;
                }

                .task-chip {
                    width: fit-content;
                    padding: 3px 8px;
                    border-radius: 999px;
                    background: #e2e8f0;
                    color: #334155;
                    font-size: 12px;
                    font-weight: 700;
                }

                .task-chip.priority-low {
                    background: #dcfce7;
                    color: #166534;
                }

                .task-chip.priority-normal {
                    background: #dbeafe;
                    color: #075985;
                }

                .task-chip.priority-high {
                    background: #fef3c7;
                    color: #92400e;
                }

                .task-chip.priority-urgent {
                    background: #fee2e2;
                    color: #991b1b;
                }

                .task-actions {
                    width: 100%;
                    gap: 8px;
                    align-items: center;
                    justify-content: flex-end;
                }

                .task-actions .q-btn {
                    border-radius: 6px;
                    text-transform: none;
                }

                .empty-task-view,
                .info-view {
                    width: 100%;
                    height: 100%;
                    align-items: center;
                    justify-content: center;
                    gap: 8px;
                    color: #64748b;
                    background: #ffffff;
                }

                .info-view {
                    align-items: stretch;
                    justify-content: flex-start;
                    padding: 24px;
                    gap: 16px;
                    overflow-y: auto;
                }

                .openapi-frame {
                    width: 100%;
                    min-height: 720px;
                    border: 1px solid #d8dee9;
                    border-radius: 6px;
                    background: #ffffff;
                }

                .create-dialog-card {
                    width: min(620px, calc(100vw - 32px));
                    border-radius: 8px;
                    gap: 12px;
                }

                .create-dialog-actions {
                    width: 100%;
                    justify-content: flex-end;
                    gap: 8px;
                }

                @media (max-width: 760px) {
                    .task-tabs {
                        overflow-x: auto;
                        flex-wrap: nowrap;
                    }

                    .task-tab {
                        flex: 0 0 auto;
                    }

                    .task-actions {
                        justify-content: flex-start;
                    }
                }
            </style>
            """
        )

        def list_tasks_for_view(view: str) -> list[TaskRead]:
            if view == "completed":
                return run_with_service(
                    lambda service: service.list(TaskSearch(status=TaskStatus.COMPLETED))
                )
            if view == "cancelled":
                return run_with_service(
                    lambda service: service.list(TaskSearch(status=TaskStatus.CANCELLED))
                )

            tasks = run_with_service(lambda service: service.list(TaskSearch(limit=500)))
            return [
                task
                for task in tasks
                if task.status in {TaskStatus.OPEN, TaskStatus.IN_PROGRESS}
            ]

        def count_tasks_by_view() -> dict[str, int]:
            tasks = run_with_service(lambda service: service.list(TaskSearch(limit=500)))
            return {
                "open": sum(
                    task.status in {TaskStatus.OPEN, TaskStatus.IN_PROGRESS} for task in tasks
                ),
                "completed": sum(task.status == TaskStatus.COMPLETED for task in tasks),
                "cancelled": sum(task.status == TaskStatus.CANCELLED for task in tasks),
            }

        def perform(action: Callable[[TaskService], object], success: str) -> None:
            nonlocal last_action
            try:
                run_with_service(action)
            except Exception as exc:
                notify_error(exc)
                return

            last_action = success
            refresh_tasks()
            ui.notify(success, type="positive")

        def task_count_label(count: int) -> str:
            label = "task" if count == 1 else "tasks"
            return f"{count} {label}"

        def set_selected_view(view: str) -> None:
            nonlocal selected_view
            selected_view = view
            refresh_tasks()

        def render_task_tabs(counts: dict[str, int]) -> None:
            with ui.row().classes("task-tabs"):
                for view, label in TASK_VIEW_LABELS.items():
                    active_class = " active" if view == selected_view else ""
                    with ui.row().classes(f"task-tab{active_class}").on(
                        "click",
                        lambda view=view: set_selected_view(view),
                    ):
                        ui.label(label)
                        ui.label(str(counts[view])).classes("task-count")

        def render_task_card(task: TaskRead, refresh: Callable[[], None]) -> None:
            tile_classes = ["task-tile"]
            if task.status == TaskStatus.COMPLETED:
                tile_classes.append("completed")
            elif task.status == TaskStatus.CANCELLED:
                tile_classes.append("cancelled")

            with ui.column().classes(" ".join(tile_classes)):
                with ui.row().classes("items-start justify-between w-full gap-2"):
                    with ui.column().classes("gap-1"):
                        ui.label(task.title).classes("task-tile-title")
                        with ui.row().classes("gap-2"):
                            ui.label(TASK_STATUS_LABELS[task.status]).classes("task-chip")
                            ui.label(TASK_PRIORITY_LABELS[task.priority]).classes(
                                f"task-chip {TASK_PRIORITY_CLASSES[task.priority]}"
                            )
                    ui.button(icon="refresh", on_click=refresh).props("flat round dense")

                ui.label(task.description or "No description").classes("task-tile-text")

                with ui.row().classes("task-actions"):
                    if task.status == TaskStatus.OPEN:
                        ui.button(
                            "Start",
                            icon="play_arrow",
                            on_click=lambda task_id=task.id: perform(
                                lambda service: service.update(
                                    task_id,
                                    TaskUpdate(status=TaskStatus.IN_PROGRESS),
                                ),
                                "Task moved to in progress.",
                            ),
                        ).props("outline")
                    if task.status in {TaskStatus.OPEN, TaskStatus.IN_PROGRESS}:
                        ui.button(
                            "Complete",
                            icon="done",
                            on_click=lambda task_id=task.id: perform(
                                lambda service: service.complete(task_id),
                                "Task completed.",
                            ),
                        ).props("unelevated")
                        ui.button(
                            "Cancel",
                            icon="block",
                            on_click=lambda task_id=task.id: perform(
                                lambda service: service.cancel(task_id),
                                "Task canceled.",
                            ),
                        ).props("outline color=negative")
                    if task.status in {TaskStatus.COMPLETED, TaskStatus.CANCELLED}:
                        ui.button(
                            "Reopen",
                            icon="restore",
                            on_click=lambda task_id=task.id: perform(
                                lambda service: service.reopen(task_id),
                                "Task reopened.",
                            ),
                        ).props("outline")

        def render_task_section(title: str, tasks: list[TaskRead]) -> None:
            with ui.column().classes("task-section"):
                with ui.row().classes("task-section-header"):
                    ui.label(title).classes("task-section-title")
                    ui.label(task_count_label(len(tasks))).classes("task-section-count")

                if not tasks:
                    ui.label("Nothing here yet.").classes("task-section-empty")
                    return

                for task in tasks:
                    render_task_card(task, refresh_tasks)

        def refresh_tasks() -> None:
            if current_view == "tasks":
                refresh_tasks_content()

        def refresh_tasks_content() -> None:
            if (
                header_container is None
                or tabs_container is None
                or list_container is None
            ):
                return

            try:
                counts = count_tasks_by_view()
                tasks = list_tasks_for_view(selected_view)
            except Exception as exc:
                notify_error(exc)
                return

            header_container.clear()
            with header_container:
                ui.label("Tasks").classes("todo-title")
                view_summary = f"{TASK_VIEW_LABELS[selected_view]}: {task_count_label(len(tasks))}"
                ui.label(view_summary).classes("todo-meta")

            tabs_container.clear()
            with tabs_container:
                render_task_tabs(counts)

            list_container.clear()
            with list_container:
                if selected_view == "open":
                    in_progress_tasks = [
                        task for task in tasks if task.status == TaskStatus.IN_PROGRESS
                    ]
                    not_started_tasks = [
                        task for task in tasks if task.status == TaskStatus.OPEN
                    ]
                    render_task_section("In Progress", in_progress_tasks)
                    ui.separator().classes("task-list-separator")
                    render_task_section("Not Started", not_started_tasks)
                    return

                if not tasks:
                    with ui.column().classes("empty-task-view"):
                        ui.icon("task_alt", size="42px").classes("text-grey-5")
                        ui.label("No tasks in this tab yet.").classes("text-subtitle1")
                        ui.label("Add a new task or switch tabs.").classes("text-caption")
                    return

                for task in tasks:
                    render_task_card(task, refresh_tasks)

        def render_tasks() -> None:
            nonlocal current_view, header_container, tabs_container, list_container
            current_view = "tasks"
            main_container.clear()
            with main_container, ui.column().classes("todo-view"):
                header_container = ui.column().classes("todo-header")
                tabs_container = ui.element("div")
                list_container = ui.column().classes("task-list")
            refresh_tasks_content()

        def render_info() -> None:
            nonlocal current_view
            current_view = "info"
            main_container.clear()
            with main_container, ui.column().classes("info-view"):
                with ui.card().classes("w-full max-w-xl"):
                    ui.label("Application Status").classes("text-h6")
                    ui.label(settings.app_name)
                    ui.label(f"Address: http://{settings.host}:{settings.port}")
                    ui.label(f"Database: {settings.db_path}")
                ui.label(last_action).classes("text-caption text-grey-7")
                ui.html(
                    '<iframe class="openapi-frame" src="/docs" title="OpenAPI"></iframe>'
                ).classes("w-full")

        def reset_create_form() -> None:
            title_input.value = ""
            description_input.value = ""
            priority_input.value = TaskPriority.NORMAL.value

        def open_create_dialog() -> None:
            reset_create_form()
            create_task_dialog.open()

        def create_from_form() -> None:
            nonlocal selected_view, last_action
            try:
                payload = TaskCreate(
                    title=str(title_input.value or ""),
                    description=str(description_input.value or ""),
                    priority=TaskPriority(str(priority_input.value)),
                )
                run_with_service(lambda service: service.create(payload))
            except Exception as exc:
                notify_error(exc)
                return

            selected_view = "open"
            last_action = "Task created."
            create_task_dialog.close()
            refresh_tasks()
            ui.notify(last_action, type="positive")

        with ui.dialog() as create_task_dialog, ui.card().classes("create-dialog-card"):
            ui.label("Add Task").classes("text-h6")
            title_input = ui.input("Title").classes("w-full")
            description_input = ui.textarea("Task Text").classes("w-full").props("rows=6")
            priority_input = ui.select(
                options=["low", "normal", "high", "urgent"],
                value="normal",
                label="Priority",
            ).classes("w-full")
            with ui.row().classes("create-dialog-actions"):
                ui.button("Cancel", on_click=create_task_dialog.close).props("flat")
                ui.button("Create", icon="add", on_click=create_from_form).props("unelevated")

        with ui.column().classes("todo-shell"):
            with ui.row().classes("todo-toolbar"):
                ui.button("Tasks", icon="task_alt", on_click=render_tasks).props("unelevated")
                ui.button("Add", icon="add", on_click=open_create_dialog).props("outline")
                ui.button("Info", icon="info", on_click=render_info).props("flat")

            main_container = ui.element("main").classes("todo-main")

        ui.on("todo-tasks-changed", lambda: refresh_tasks())
        ui.run_javascript(
            """
            (() => {
                if (window.todoAppEventSource) {
                    window.todoAppEventSource.close();
                }
                const source = new EventSource('/api/tasks/events');
                source.addEventListener('connected', () => {
                    emitEvent('todoTasksChanged');
                });
                source.addEventListener('tasks_changed', () => {
                    emitEvent('todoTasksChanged');
                });
                window.addEventListener('beforeunload', () => source.close(), { once: true });
                window.todoAppEventSource = source;
            })();
            """
        )
        reset_create_form()
        render_tasks()
