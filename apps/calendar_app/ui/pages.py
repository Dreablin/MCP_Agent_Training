from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from typing import TypeVar

from nicegui import ui
from sqlalchemy.orm import Session, sessionmaker

from apps.calendar_app.config import CalendarAppSettings
from apps.calendar_app.database import session_scope
from apps.calendar_app.models import CalendarEventStatus
from apps.calendar_app.repositories import CalendarEventRepository, EventSearch
from apps.calendar_app.schemas import CalendarEventCreate, CalendarEventRead, Participant
from apps.calendar_app.services import CalendarEventService
from shared.errors import AppError

T = TypeVar("T")

DAY_LABELS = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)
HOUR_START = 8
HOUR_END = 22
HOUR_HEIGHT = 72


def register_pages(settings: CalendarAppSettings, session_factory: sessionmaker[Session]) -> None:
    def run_with_service(action: Callable[[CalendarEventService], T]) -> T:
        with session_scope(session_factory) as session:
            service = CalendarEventService(CalendarEventRepository(session))
            return action(service)

    def notify_error(exc: Exception) -> None:
        if isinstance(exc, AppError):
            ui.notify(exc.message, type="negative")
            return
        ui.notify(str(exc), type="negative")

    @ui.page("/")
    def index() -> None:
        today = datetime.now().date()
        week_start = today - timedelta(days=today.weekday())
        selected_event_id: str | None = None
        selected_event_status = CalendarEventStatus.CONFIRMED
        last_action = "Calendar is ready."

        ui.add_head_html(
            f"""
            <style>
                body {{
                    margin: 0;
                    background: #f5f7fb;
                    color: #1f2937;
                }}

                .calendar-shell {{
                    height: 100vh;
                    width: 100%;
                    gap: 0;
                    overflow: hidden;
                    font-family: Inter, Roboto, Arial, sans-serif;
                }}

                .calendar-toolbar {{
                    width: 100%;
                    min-height: 58px;
                    padding: 8px 14px;
                    gap: 8px;
                    align-items: center;
                    border-bottom: 1px solid #d8dee9;
                    background: #ffffff;
                    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.08);
                }}

                .calendar-toolbar .q-btn {{
                    border-radius: 6px;
                    min-height: 38px;
                    text-transform: none;
                    font-weight: 600;
                }}

                .calendar-main {{
                    flex: 1;
                    width: 100%;
                    min-height: 0;
                    overflow: hidden;
                }}

                .calendar-view {{
                    width: 100%;
                    height: 100%;
                    gap: 0;
                    background: #ffffff;
                    overflow: hidden;
                }}

                .calendar-titlebar {{
                    min-height: 58px;
                    padding: 10px 16px;
                    align-items: center;
                    justify-content: space-between;
                    border-bottom: 1px solid #e5e7eb;
                    background: #fbfdff;
                }}

                .calendar-week-title {{
                    color: #0f172a;
                    font-size: 17px;
                    font-weight: 700;
                }}

                .calendar-week-meta {{
                    color: #64748b;
                    font-size: 12px;
                }}

                .calendar-scroll {{
                    flex: 1;
                    width: 100%;
                    min-height: 0;
                    overflow: auto;
                    background: #ffffff;
                }}

                .calendar-grid {{
                    min-width: 980px;
                    width: 100%;
                    --hour-height: {HOUR_HEIGHT}px;
                    --day-height: {(HOUR_END - HOUR_START) * HOUR_HEIGHT}px;
                }}

                .week-header {{
                    display: grid;
                    grid-template-columns: 68px repeat(7, minmax(128px, 1fr));
                    position: sticky;
                    top: 0;
                    z-index: 5;
                    min-height: 70px;
                    background: #ffffff;
                    border-bottom: 1px solid #cfd8e3;
                }}

                .time-gutter-header {{
                    border-right: 1px solid #d8dee9;
                    background: #ffffff;
                }}

                .day-header {{
                    min-width: 0;
                    padding: 10px 12px;
                    border-right: 1px solid #d8dee9;
                    background: #ffffff;
                }}

                .day-header.today {{
                    border-top: 3px solid #1976d2;
                    color: #075985;
                }}

                .day-number {{
                    color: #1976d2;
                    font-size: 18px;
                    font-weight: 700;
                    line-height: 1.1;
                }}

                .day-name {{
                    color: #475569;
                    font-size: 12px;
                    line-height: 1.2;
                }}

                .day-header.today .day-name {{
                    color: #1976d2;
                    font-weight: 600;
                }}

                .week-body {{
                    display: grid;
                    grid-template-columns: 68px repeat(7, minmax(128px, 1fr));
                    min-height: var(--day-height);
                }}

                .time-axis {{
                    position: relative;
                    height: var(--day-height);
                    border-right: 1px solid #d8dee9;
                    background: #fbfdff;
                }}

                .time-label {{
                    position: absolute;
                    right: 14px;
                    color: #64748b;
                    font-size: 12px;
                    line-height: 16px;
                }}

                .day-column {{
                    position: relative;
                    height: var(--day-height);
                    min-width: 0;
                    border-right: 1px solid #d8dee9;
                    background: #ffffff;
                }}

                .hour-cell {{
                    height: var(--hour-height);
                    border-bottom: 1px solid #dfe5ed;
                    background-image: linear-gradient(
                        to bottom,
                        transparent calc(50% - 1px),
                        #eef2f6 calc(50% - 1px),
                        #eef2f6 50%,
                        transparent 50%
                    );
                }}

                .calendar-event {{
                    position: absolute;
                    left: 8px;
                    right: 8px;
                    z-index: 2;
                    min-height: 28px;
                    padding: 7px 9px;
                    overflow: hidden;
                    border-left: 4px solid #7c83ff;
                    border-radius: 5px;
                    background: #eef0ff;
                    color: #1f2a44;
                    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.08);
                    cursor: pointer;
                }}

                .calendar-event:hover {{
                    background: #e3e7ff;
                }}

                .calendar-event.cancelled {{
                    border-left-color: #94a3b8;
                    background: #f1f5f9;
                    color: #64748b;
                    text-decoration: line-through;
                }}

                .event-title {{
                    display: block;
                    overflow: hidden;
                    text-overflow: ellipsis;
                    white-space: nowrap;
                    font-size: 13px;
                    font-weight: 700;
                    line-height: 16px;
                }}

                .event-meta {{
                    display: block;
                    overflow: hidden;
                    text-overflow: ellipsis;
                    white-space: nowrap;
                    font-size: 11px;
                    line-height: 15px;
                    color: inherit;
                    opacity: 0.82;
                }}

                .current-time-line {{
                    position: absolute;
                    left: 0;
                    right: 0;
                    z-index: 3;
                    height: 2px;
                    background: #1976d2;
                }}

                .current-time-line::before {{
                    content: "";
                    position: absolute;
                    left: -6px;
                    top: -5px;
                    width: 12px;
                    height: 12px;
                    border-radius: 999px;
                    background: #1976d2;
                }}

                .placeholder-view,
                .empty-calendar-view {{
                    width: 100%;
                    height: 100%;
                    align-items: center;
                    justify-content: center;
                    gap: 8px;
                    color: #64748b;
                    background: #ffffff;
                }}

                .info-view {{
                    width: 100%;
                    height: 100%;
                    padding: 24px;
                    gap: 16px;
                    background: #ffffff;
                    overflow-y: auto;
                }}

                .openapi-frame {{
                    width: 100%;
                    min-height: 720px;
                    border: 1px solid #d8dee9;
                    border-radius: 6px;
                    background: #ffffff;
                }}

                .event-dialog-card {{
                    width: min(560px, calc(100vw - 32px));
                    border-radius: 8px;
                    gap: 10px;
                }}

                .create-dialog-card {{
                    width: min(620px, calc(100vw - 32px));
                    border-radius: 8px;
                    gap: 12px;
                }}

                .event-dialog-meta {{
                    color: #64748b;
                    font-size: 13px;
                }}

                .event-dialog-actions {{
                    width: 100%;
                    justify-content: flex-end;
                    gap: 8px;
                }}

                @media (max-width: 900px) {{
                    .calendar-titlebar {{
                        align-items: flex-start;
                        flex-direction: column;
                        gap: 2px;
                    }}
                }}
            </style>
            """
        )

        def week_days() -> list[date]:
            return [week_start + timedelta(days=offset) for offset in range(7)]

        def week_bounds() -> tuple[datetime, datetime]:
            start = datetime.combine(week_start, time.min)
            end = start + timedelta(days=7)
            return start, end

        def fetch_week_events() -> list[CalendarEventRead]:
            start, end = week_bounds()
            return run_with_service(
                lambda service: service.list_events(
                    EventSearch(
                        starts_before=end,
                        ends_after=start,
                        include_cancelled=True,
                        limit=500,
                    )
                )
            )

        def day_range(day: date) -> tuple[datetime, datetime]:
            start = datetime.combine(day, time(HOUR_START))
            end = datetime.combine(day, time(HOUR_END))
            return start, end

        def format_event_time(event: CalendarEventRead) -> str:
            return f"{event.start_at:%H:%M} - {event.end_at:%H:%M}"

        def event_style(event: CalendarEventRead, day: date) -> str:
            visible_start, visible_end = day_range(day)
            event_start = max(event.start_at, visible_start)
            event_end = min(event.end_at, visible_end)
            minutes_from_start = max(
                0,
                int((event_start - visible_start).total_seconds() // 60),
            )
            event_minutes = max(30, int((event_end - event_start).total_seconds() // 60))
            top = minutes_from_start / 60 * HOUR_HEIGHT
            height = event_minutes / 60 * HOUR_HEIGHT
            return f"top: {top:.0f}px; height: {height:.0f}px;"

        def events_for_day(events: list[CalendarEventRead], day: date) -> list[CalendarEventRead]:
            visible_start, visible_end = day_range(day)
            return [
                event
                for event in events
                if event.start_at < visible_end and event.end_at > visible_start
            ]

        def set_last_action(message: str, *, notify: bool = True) -> None:
            nonlocal last_action
            last_action = message
            if notify:
                ui.notify(message)

        def refresh_calendar(message: str | None = None) -> None:
            if message is not None:
                set_last_action(message, notify=False)
            render_calendar()

        def parse_date_input(value: object) -> date:
            raw_value = str(value or "").strip()
            for date_format in ("%d.%m.%Y", "%Y-%m-%d"):
                try:
                    return datetime.strptime(raw_value, date_format).date()
                except ValueError:
                    continue
            msg = "Date must use DD.MM.YYYY format"
            raise ValueError(msg)

        def parse_time_input(value: object, field_label: str) -> time:
            raw_value = str(value or "").strip()
            try:
                return datetime.strptime(raw_value, "%H:%M").time()
            except ValueError as exc:
                msg = f"{field_label} must use HH:MM format"
                raise ValueError(msg) from exc

        def reset_create_form() -> None:
            default_date = datetime.now().date()
            create_title_input.value = ""
            create_participant_name_input.value = ""
            create_participant_email_input.value = ""
            create_description_input.value = ""
            create_date_input.value = default_date.strftime("%d.%m.%Y")
            create_start_time_input.value = "09:00"
            create_end_time_input.value = "10:00"

        def open_create_dialog() -> None:
            reset_create_form()
            create_event_dialog.open()

        def save_created_event() -> None:
            nonlocal week_start

            try:
                event_date = parse_date_input(create_date_input.value)
                start_time = parse_time_input(create_start_time_input.value, "Start time")
                end_time = parse_time_input(create_end_time_input.value, "End time")
                start_at = datetime.combine(event_date, start_time)
                end_at = datetime.combine(event_date, end_time)

                participants: list[Participant] = []
                participant_email = str(create_participant_email_input.value or "").strip()
                if participant_email:
                    participant_name = str(create_participant_name_input.value or "").strip()
                    participants.append(
                        Participant(
                            name=participant_name or participant_email,
                            email=participant_email,
                        )
                    )

                payload = CalendarEventCreate(
                    title=str(create_title_input.value or "").strip(),
                    description=str(create_description_input.value or "").strip(),
                    start_at=start_at,
                    end_at=end_at,
                    participants=participants,
                )
                run_with_service(lambda service: service.create(payload))
            except Exception as exc:
                notify_error(exc)
                return

            week_start = event_date - timedelta(days=event_date.weekday())
            create_event_dialog.close()
            refresh_calendar("Event created.")
            ui.notify("Event created.", type="positive")

        def perform(action: Callable[[CalendarEventService], object], success: str) -> None:
            try:
                run_with_service(action)
            except Exception as exc:
                notify_error(exc)
                return

            event_dialog.close()
            refresh_calendar(success)
            ui.notify(success, type="positive")

        def toggle_selected_event_status() -> None:
            if selected_event_id is None:
                return

            event_id = selected_event_id
            if selected_event_status == CalendarEventStatus.CANCELLED:
                perform(
                    lambda service: service.restore(event_id),
                    "Event restored.",
                )
            else:
                perform(
                    lambda service: service.cancel(event_id),
                    "Event cancelled.",
                )

        def ask_delete_selected_event() -> None:
            if selected_event_id is None:
                return
            delete_event_title_label.text = event_title_label.text
            delete_event_dialog.open()

        def delete_selected_event() -> None:
            if selected_event_id is None:
                delete_event_dialog.close()
                return

            event_id = selected_event_id
            try:
                run_with_service(lambda service: service.delete(event_id))
            except Exception as exc:
                notify_error(exc)
                return

            delete_event_dialog.close()
            event_dialog.close()
            refresh_calendar("Event deleted.")
            ui.notify("Event deleted.", type="positive")

        def open_event(event: CalendarEventRead) -> None:
            nonlocal selected_event_id, selected_event_status
            selected_event_id = event.id
            selected_event_status = event.status
            participants = ", ".join(
                f"{participant.name} <{participant.email}>" for participant in event.participants
            )
            event_title_label.text = event.title
            event_time_label.text = format_event_time(event)
            event_status_label.text = f"Status: {event.status.value}"
            event_location_label.text = f"Location: {event.location or 'not specified'}"
            event_participants_label.text = f"Participants: {participants or 'none'}"
            event_description_label.text = event.description or "No description"
            if event.status == CalendarEventStatus.CANCELLED:
                event_status_button.text = "Restore"
                event_status_button.props("icon=restore outline")
            else:
                event_status_button.text = "Cancel event"
                event_status_button.props("icon=event_busy outline")
            event_dialog.open()

        def render_time_axis() -> None:
            with ui.element("div").classes("time-axis"):
                for hour in range(HOUR_START, HOUR_END + 1):
                    top = (hour - HOUR_START) * HOUR_HEIGHT
                    ui.label(f"{hour:02d}:00").classes("time-label").style(f"top: {top}px;")

        def render_day_column(events: list[CalendarEventRead], day: date) -> None:
            with ui.element("div").classes("day-column"):
                for _hour in range(HOUR_START, HOUR_END):
                    ui.element("div").classes("hour-cell")

                now = datetime.now()
                if day == now.date() and HOUR_START <= now.hour < HOUR_END:
                    minutes = (now.hour - HOUR_START) * 60 + now.minute
                    top = minutes / 60 * HOUR_HEIGHT
                    ui.element("div").classes("current-time-line").style(f"top: {top:.0f}px;")

                for event in events_for_day(events, day):
                    classes = ["calendar-event"]
                    if event.status == CalendarEventStatus.CANCELLED:
                        classes.append("cancelled")
                    with ui.element("div").classes(" ".join(classes)).style(
                        event_style(event, day)
                    ).on("click", lambda event=event: open_event(event)):
                        ui.label(event.title).classes("event-title")
                        ui.label(format_event_time(event)).classes("event-meta")
                        if event.location:
                            ui.label(event.location).classes("event-meta")

        def render_calendar() -> None:
            try:
                events = fetch_week_events()
            except Exception as exc:
                notify_error(exc)
                return

            start, end = week_bounds()
            main_container.clear()
            with main_container, ui.column().classes("calendar-view"):
                with ui.row().classes("calendar-titlebar"):
                    with ui.column().classes("gap-0"):
                        ui.label("Calendar").classes("calendar-week-title")
                        week_end = end - timedelta(days=1)
                        ui.label(f"{start:%d.%m.%Y} - {week_end:%d.%m.%Y}").classes(
                            "calendar-week-meta",
                        )
                    ui.label(f"{len(events)} events this week").classes("calendar-week-meta")

                with (
                    ui.element("div").classes("calendar-scroll"),
                    ui.element("div").classes("calendar-grid"),
                ):
                        with ui.element("div").classes("week-header"):
                            ui.element("div").classes("time-gutter-header")
                            for day in week_days():
                                today_class = " today" if day == today else ""
                                with ui.column().classes(f"day-header{today_class}"):
                                    ui.label(str(day.day)).classes("day-number")
                                    ui.label(DAY_LABELS[day.weekday()]).classes("day-name")

                        with ui.element("div").classes("week-body"):
                            render_time_axis()
                            for day in week_days():
                                render_day_column(events, day)

        def render_info() -> None:
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

        with ui.dialog() as create_event_dialog, ui.card().classes("create-dialog-card"):
            ui.label("Create Event").classes("text-h6")
            create_title_input = ui.input("Title").classes("w-full")
            create_participant_name_input = ui.input(
                "Participant name",
            ).classes("w-full")
            create_participant_email_input = ui.input(
                "Participant email",
            ).classes("w-full")
            create_description_input = ui.textarea("Event description").classes("w-full")
            create_date_input = ui.input("Date", value=today.strftime("%d.%m.%Y")).classes(
                "w-full",
            )
            create_start_time_input = ui.input("Start time", value="09:00").classes("w-full")
            create_end_time_input = ui.input("End time", value="10:00").classes("w-full")
            with ui.row().classes("event-dialog-actions"):
                ui.button("Cancel", on_click=create_event_dialog.close).props("flat")
                ui.button(
                    "Save",
                    icon="save",
                    on_click=save_created_event,
                ).props("unelevated")

        with ui.dialog() as event_dialog, ui.card().classes("event-dialog-card"):
            event_title_label = ui.label("").classes("text-h6")
            event_time_label = ui.label("").classes("event-dialog-meta")
            event_status_label = ui.label("").classes("event-dialog-meta")
            event_location_label = ui.label("").classes("event-dialog-meta")
            event_participants_label = ui.label("").classes("event-dialog-meta")
            event_description_label = ui.label("").classes("text-body2")
            with ui.row().classes("event-dialog-actions"):
                event_status_button = ui.button(
                    "Cancel event",
                    icon="event_busy",
                    on_click=toggle_selected_event_status,
                ).props("outline")
                ui.button(
                    "Delete",
                    icon="delete",
                    on_click=ask_delete_selected_event,
                ).props("outline color=negative")
                ui.button("Close", on_click=event_dialog.close).props("flat")

        with ui.dialog() as delete_event_dialog, ui.card().classes("event-dialog-card"):
            ui.label("Delete event?").classes("text-h6")
            ui.label("This event will be deleted permanently.").classes("text-body2")
            delete_event_title_label = ui.label("").classes("event-dialog-meta")
            with ui.row().classes("event-dialog-actions"):
                ui.button("Cancel", on_click=delete_event_dialog.close).props("flat")
                ui.button(
                    "Delete",
                    icon="delete",
                    on_click=delete_selected_event,
                ).props("unelevated color=negative")

        with ui.column().classes("calendar-shell"):
            with ui.row().classes("calendar-toolbar"):
                ui.button("Calendar", icon="calendar_month", on_click=render_calendar).props(
                    "unelevated"
                )
                ui.button(
                    "Create event",
                    icon="add",
                    on_click=open_create_dialog,
                ).props("outline")
                ui.button("Info", icon="info", on_click=render_info).props("flat")

            main_container = ui.element("main").classes("calendar-main")

        render_calendar()
