from datetime import datetime
from zoneinfo import ZoneInfo

from apps.calendar_app.database import (
    build_engine as build_calendar_engine,
)
from apps.calendar_app.database import (
    build_session_factory as build_calendar_session_factory,
)
from apps.calendar_app.database import session_scope as calendar_session_scope
from apps.calendar_app.repositories import CalendarEventRepository
from apps.calendar_app.schemas import CalendarEventCreate, Participant
from apps.calendar_app.services import CalendarEventService
from apps.email_app.database import build_engine as build_email_engine
from apps.email_app.database import build_session_factory as build_email_session_factory
from apps.email_app.database import session_scope as email_session_scope
from apps.email_app.repositories import EmailMessageRepository
from apps.email_app.schemas import EmailMessageCreate
from apps.email_app.services import EmailMessageService
from apps.todo_app.database import build_engine as build_todo_engine
from apps.todo_app.database import build_session_factory as build_todo_session_factory
from apps.todo_app.database import session_scope as todo_session_scope
from apps.todo_app.models import TaskPriority
from apps.todo_app.repositories import TaskRepository
from apps.todo_app.schemas import TaskCreate
from apps.todo_app.services import TaskService
from scripts.migrate_all import migrate_all
from scripts.reset_data import reset_data

CHICAGO = ZoneInfo("America/Chicago")


def seed_email() -> None:
    engine = build_email_engine("sqlite:///data/email.db")
    session_factory = build_email_session_factory(engine)
    with email_session_scope(session_factory) as session:
        service = EmailMessageService(EmailMessageRepository(session))
        service.create(
            EmailMessageCreate(
                id="00000000-0000-4000-8000-000000000101",
                sender_name="Анна",
                sender_email="anna@example.test",
                recipient_email="me@example.test",
                subject="Встреча с Анной",
                body="Давай встретимся 12 августа 2026 в 14:30 и обсудим учебный проект.",
                received_at=datetime(2026, 8, 6, 10, 0, tzinfo=CHICAGO),
            )
        )
        service.create(
            EmailMessageCreate(
                id="00000000-0000-4000-8000-000000000102",
                sender_name="Ирина",
                sender_email="irina@example.test",
                recipient_email="me@example.test",
                subject="Подготовить материалы",
                body="Пожалуйста, подготовь материалы к обсуждению до завтра 15:00.",
                received_at=datetime(2026, 8, 6, 11, 0, tzinfo=CHICAGO),
            )
        )
        service.create(
            EmailMessageCreate(
                id="00000000-0000-4000-8000-000000000103",
                sender_name="Сергей",
                sender_email="sergey@example.test",
                recipient_email="me@example.test",
                subject="Привет",
                body="Просто проверяю, что учебная почта работает.",
                received_at=datetime(2026, 8, 6, 12, 0, tzinfo=CHICAGO),
            )
        )
    engine.dispose()


def seed_todo() -> None:
    engine = build_todo_engine("sqlite:///data/todo.db")
    session_factory = build_todo_session_factory(engine)
    with todo_session_scope(session_factory) as session:
        service = TaskService(TaskRepository(session))
        service.create(
            TaskCreate(
                id="00000000-0000-4000-8000-000000000201",
                title="Подготовиться к встрече",
                description="Собрать материалы, проверить повестку и подготовить вопросы.",
                priority=TaskPriority.HIGH,
            )
        )
        completed = service.create(
            TaskCreate(
                id="00000000-0000-4000-8000-000000000202",
                title="Проверить учебные данные",
                description="Убедиться, что demo data отображается во всех приложениях.",
                priority=TaskPriority.NORMAL,
            )
        )
        service.complete(completed.id)
    engine.dispose()


def seed_calendar() -> None:
    engine = build_calendar_engine("sqlite:///data/calendar.db")
    session_factory = build_calendar_session_factory(engine)
    with calendar_session_scope(session_factory) as session:
        service = CalendarEventService(CalendarEventRepository(session))
        service.create(
            CalendarEventCreate(
                id="00000000-0000-4000-8000-000000000301",
                title="Встреча с Анной",
                description="Обсудить учебный проект и следующие шаги.",
                start_at=datetime(2026, 8, 12, 14, 30),
                end_at=datetime(2026, 8, 12, 15, 30),
                location="Office",
                participants=[Participant(name="Анна", email="anna@example.test")],
            )
        )
        cancelled = service.create(
            CalendarEventCreate(
                id="00000000-0000-4000-8000-000000000302",
                title="Отмененный созвон",
                description="Пример отмененного события.",
                start_at=datetime(2026, 8, 13, 10, 0),
                end_at=datetime(2026, 8, 13, 10, 30),
                location="",
                participants=[Participant(name="Сергей", email="sergey@example.test")],
            )
        )
        service.cancel(cancelled.id)
    engine.dispose()


def seed_demo_data() -> None:
    reset_data()
    migrate_all(verbose=False)
    seed_email()
    seed_todo()
    seed_calendar()


def main() -> None:
    seed_demo_data()
    print("Demo data created in data/email.db, data/todo.db, and data/calendar.db.")


if __name__ == "__main__":
    main()
