from collections.abc import Callable
from typing import TypeVar

from nicegui import ui
from nicegui.element import Element
from sqlalchemy.orm import Session, sessionmaker

from apps.email_app.config import EmailAppSettings
from apps.email_app.database import session_scope
from apps.email_app.events import EmailEventBus
from apps.email_app.models import EmailFolder
from apps.email_app.repositories import EmailMessageRepository, EmailSearch
from apps.email_app.schemas import EmailMessageCreate, EmailMessageRead
from apps.email_app.services import EmailMessageService
from shared.datetime import now_utc
from shared.errors import AppError
from shared.ui import render_app_status

T = TypeVar("T")

FOLDER_LABELS: dict[EmailFolder, str] = {
    EmailFolder.INBOX: "Inbox",
    EmailFolder.SENT: "Sent",
    EmailFolder.SPAM: "Spam",
    EmailFolder.FRIENDS: "Friends",
    EmailFolder.WORK: "Work",
    EmailFolder.LOGS: "Logs",
    EmailFolder.TRASH: "Trash",
}
FOLDER_ICONS: dict[EmailFolder, str] = {
    EmailFolder.INBOX: "inbox",
    EmailFolder.SENT: "send",
    EmailFolder.SPAM: "report",
    EmailFolder.FRIENDS: "group",
    EmailFolder.WORK: "work",
    EmailFolder.LOGS: "article",
    EmailFolder.TRASH: "delete",
}
FOLDER_ORDER: tuple[EmailFolder | None, ...] = (
    EmailFolder.INBOX,
    EmailFolder.WORK,
    EmailFolder.FRIENDS,
    EmailFolder.LOGS,
    EmailFolder.SPAM,
    None,
    EmailFolder.SENT,
    None,
    EmailFolder.TRASH,
)
LOCAL_SENDER_EMAIL = "me@example.test"


def register_pages(
    settings: EmailAppSettings,
    session_factory: sessionmaker[Session],
    event_bus: EmailEventBus,
) -> None:
    def run_with_service(action: Callable[[EmailMessageService], T]) -> T:
        service: EmailMessageService | None = None
        with session_scope(session_factory) as session:
            service = EmailMessageService(EmailMessageRepository(session))
            result = action(service)
        assert service is not None
        for event in service.pull_events():
            event_bus.publish(event)
        return result

    def notify_error(exc: Exception) -> None:
        if isinstance(exc, AppError):
            ui.notify(exc.message, type="negative")
            return
        ui.notify(str(exc), type="negative")

    @ui.page("/")
    def index() -> None:
        selected_folder = EmailFolder.INBOX
        selected_message_id: str | None = None
        pending_delete_message_id: str | None = None
        current_view = "mail"
        folder_container: Element | None = None
        message_container: Element | None = None
        reader_container: Element | None = None
        last_action = "Mail is ready."

        ui.add_head_html(
            """
            <style>
                body {
                    margin: 0;
                    background: #f5f7fb;
                    color: #1f2937;
                }

                .email-shell {
                    height: 100vh;
                    width: 100%;
                    gap: 0;
                    overflow: hidden;
                    font-family: Inter, Roboto, Arial, sans-serif;
                }

                .email-toolbar {
                    width: 100%;
                    min-height: 58px;
                    padding: 8px 14px;
                    gap: 8px;
                    align-items: center;
                    border-bottom: 1px solid #d8dee9;
                    background: #ffffff;
                    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.08);
                }

                .email-toolbar .q-btn {
                    border-radius: 6px;
                    min-height: 38px;
                    text-transform: none;
                    font-weight: 600;
                }

                .email-main {
                    flex: 1;
                    width: 100%;
                    min-height: 0;
                    overflow: hidden;
                }

                .email-workspace {
                    width: 100%;
                    height: 100%;
                    gap: 0;
                    flex-wrap: nowrap;
                    overflow: hidden;
                }

                .folder-pane {
                    width: 220px;
                    min-width: 180px;
                    height: 100%;
                    padding: 18px 12px;
                    gap: 8px;
                    background: #edf4fa;
                    border-right: 1px solid #d8dee9;
                }

                .folder-button {
                    width: 100%;
                    min-height: 36px;
                    padding: 0 10px;
                    align-items: center;
                    justify-content: space-between;
                    gap: 8px;
                    border-radius: 6px;
                    color: #334155;
                    cursor: pointer;
                    user-select: none;
                }

                .folder-button:hover {
                    background: #e1edf8;
                }

                .folder-button.active {
                    background: #cfe3fb;
                    color: #075985;
                }

                .folder-name {
                    min-width: 0;
                    gap: 10px;
                    align-items: center;
                }

                .folder-label {
                    overflow: hidden;
                    text-overflow: ellipsis;
                    white-space: nowrap;
                }

                .folder-count {
                    margin-left: auto;
                    font-weight: 700;
                }

                .folder-separator {
                    width: 100%;
                    margin: 4px 0;
                    background: #d8dee9;
                }

                .message-pane {
                    width: 380px;
                    min-width: 280px;
                    height: 100%;
                    gap: 0;
                    background: #ffffff;
                    border-right: 1px solid #d8dee9;
                }

                .message-pane-header {
                    min-height: 64px;
                    padding: 12px 16px;
                    border-bottom: 1px solid #e5e7eb;
                    background: #fbfdff;
                }

                .message-list {
                    flex: 1;
                    min-height: 0;
                    width: 100%;
                    gap: 0;
                    overflow-y: auto;
                }

                .message-row {
                    width: 100%;
                    padding: 12px 14px;
                    gap: 4px;
                    border-bottom: 1px solid #edf0f4;
                    cursor: pointer;
                    background: #ffffff;
                }

                .message-row:hover {
                    background: #f7fbff;
                }

                .message-row.active {
                    background: #dbeafe;
                    border-left: 4px solid #1976d2;
                    padding-left: 10px;
                }

                .message-row.unread .message-subject,
                .message-row.unread .message-sender {
                    font-weight: 700;
                }

                .message-preview,
                .message-date,
                .reader-meta {
                    color: #64748b;
                }

                .reader-pane {
                    flex: 1;
                    min-width: 0;
                    height: 100%;
                    gap: 0;
                    background: #ffffff;
                    overflow: hidden;
                }

                .reader-header {
                    padding: 18px 24px;
                    gap: 8px;
                    border-bottom: 1px solid #e5e7eb;
                    background: #ffffff;
                }

                .reader-body {
                    flex: 1;
                    min-height: 0;
                    padding: 24px;
                    overflow-y: auto;
                    font-size: 16px;
                    line-height: 1.55;
                    white-space: pre-wrap;
                    overflow-wrap: anywhere;
                }

                .reader-status {
                    width: fit-content;
                    padding: 3px 8px;
                    border-radius: 999px;
                    background: #e2e8f0;
                    color: #334155;
                    font-size: 12px;
                    font-weight: 700;
                }

                .reader-status.unread {
                    background: #dbeafe;
                    color: #075985;
                }

                .reader-actions {
                    width: 100%;
                    justify-content: flex-start;
                    gap: 8px;
                }

                .empty-state,
                .placeholder-view {
                    width: 100%;
                    height: 100%;
                    align-items: center;
                    justify-content: center;
                    gap: 8px;
                    color: #64748b;
                    background: #ffffff;
                }

                .info-view {
                    width: 100%;
                    height: 100%;
                    padding: 24px;
                    gap: 16px;
                    background: #ffffff;
                    overflow-y: auto;
                }

                .openapi-frame {
                    width: 100%;
                    min-height: 720px;
                    border: 1px solid #d8dee9;
                    border-radius: 6px;
                    background: #ffffff;
                }

                .send-dialog-card {
                    width: min(620px, calc(100vw - 32px));
                    border-radius: 8px;
                    gap: 14px;
                }

                .send-dialog-actions {
                    width: 100%;
                    justify-content: flex-end;
                    gap: 8px;
                }

                .confirm-dialog-card {
                    width: min(460px, calc(100vw - 32px));
                    border-radius: 8px;
                    gap: 12px;
                }

                @media (max-width: 900px) {
                    .email-workspace {
                        flex-direction: column;
                    }

                    .folder-pane,
                    .message-pane,
                    .reader-pane {
                        width: 100%;
                        min-width: 0;
                        height: auto;
                    }

                    .folder-pane {
                        flex-direction: row;
                        flex-wrap: wrap;
                    }

                    .message-pane {
                        max-height: 42vh;
                    }

                    .reader-pane {
                        flex: 1;
                    }
                }
            </style>
            """
        )

        def list_messages(folder: EmailFolder) -> list[EmailMessageRead]:
            return run_with_service(
                lambda service: service.list(EmailSearch(folder=folder, limit=200))
            )

        def format_date(message: EmailMessageRead) -> str:
            return message.received_at.astimezone().strftime("%d.%m.%Y %H:%M")

        def preview_text(message: EmailMessageRead) -> str:
            compact_body = " ".join(message.body.split())
            return compact_body[:120] + ("..." if len(compact_body) > 120 else "")

        def show_placeholder(title: str, details: str) -> None:
            nonlocal current_view, last_action
            current_view = "placeholder"
            last_action = details
            ui.notify(details)
            render_placeholder(title, details)

        def reset_send_form() -> None:
            recipient_input.value = ""
            subject_input.value = ""
            body_input.value = ""

        def reset_receive_form() -> None:
            sender_input.value = ""
            received_subject_input.value = ""
            received_body_input.value = ""

        def send_message() -> None:
            nonlocal selected_folder, selected_message_id, last_action
            try:
                payload = EmailMessageCreate(
                    sender_name=settings.app_name,
                    sender_email=LOCAL_SENDER_EMAIL,
                    recipient_email=str(recipient_input.value or ""),
                    subject=str(subject_input.value or ""),
                    body=str(body_input.value or ""),
                    received_at=now_utc(),
                )
                created = run_with_service(lambda service: service.create_sent(payload))
            except Exception as exc:
                notify_error(exc)
                return

            selected_folder = EmailFolder.SENT
            selected_message_id = created.id
            last_action = "Message sent."
            send_dialog.close()
            reset_send_form()
            render_mail()
            ui.notify(last_action, type="positive")

        def receive_message() -> None:
            nonlocal selected_folder, selected_message_id, last_action
            sender_email = str(sender_input.value or "")
            try:
                payload = EmailMessageCreate(
                    sender_name=sender_email.split("@", maxsplit=1)[0] or sender_email,
                    sender_email=sender_email,
                    recipient_email=LOCAL_SENDER_EMAIL,
                    subject=str(received_subject_input.value or ""),
                    body=str(received_body_input.value or ""),
                    received_at=now_utc(),
                )
                created = run_with_service(lambda service: service.create(payload))
            except Exception as exc:
                notify_error(exc)
                return

            selected_folder = EmailFolder.INBOX
            selected_message_id = created.id
            last_action = "Message received."
            receive_dialog.close()
            reset_receive_form()
            render_mail()
            ui.notify(last_action, type="positive")

        def receive_all_messages() -> None:
            nonlocal selected_folder, selected_message_id, last_action
            try:
                created_messages = run_with_service(
                    lambda service: service.receive_all_from_directory(settings.test_messages_dir)
                )
            except Exception as exc:
                notify_error(exc)
                return

            selected_folder = EmailFolder.INBOX
            if created_messages:
                selected_message_id = created_messages[0].id
            last_action = f"Loaded {len(created_messages)} messages."
            render_mail()
            ui.notify(last_action, type="positive")

        def set_message_read(message_id: str, is_read: bool) -> None:
            nonlocal selected_message_id, last_action
            try:
                run_with_service(lambda service: service.mark_read(message_id, is_read))
            except Exception as exc:
                notify_error(exc)
                return

            selected_message_id = message_id
            last_action = "Message marked as read." if is_read else "Message marked as unread."
            render_mail()
            ui.notify(last_action, type="positive")

        def ask_delete_message(message_id: str, subject: str) -> None:
            nonlocal pending_delete_message_id
            pending_delete_message_id = message_id
            delete_subject_label.text = subject
            delete_dialog.open()

        def delete_selected_message() -> None:
            nonlocal selected_message_id, pending_delete_message_id, last_action
            if pending_delete_message_id is None:
                delete_dialog.close()
                return

            message_id = pending_delete_message_id
            try:
                run_with_service(lambda service: service.delete_permanently(message_id))
            except Exception as exc:
                notify_error(exc)
                return

            selected_message_id = None
            pending_delete_message_id = None
            last_action = "Message deleted."
            delete_dialog.close()
            render_mail()
            ui.notify(last_action, type="positive")

        def select_folder(folder: EmailFolder) -> None:
            nonlocal selected_folder, selected_message_id
            selected_folder = folder
            selected_message_id = None
            render_mail()

        def select_message(message_id: str) -> None:
            nonlocal selected_message_id
            selected_message_id = message_id
            render_mail()

        def render_folder_button(folder: EmailFolder, count: int) -> None:
            active_class = " active" if folder == selected_folder else ""
            with ui.row().classes(f"folder-button{active_class}").on(
                "click",
                lambda folder=folder: select_folder(folder),
            ):
                with ui.row().classes("folder-name"):
                    ui.icon(FOLDER_ICONS[folder], size="20px")
                    ui.label(FOLDER_LABELS[folder]).classes("folder-label")
                ui.label(str(count)).classes("folder-count")

        def render_message_row(message: EmailMessageRead) -> None:
            row_classes = ["message-row"]
            if message.id == selected_message_id:
                row_classes.append("active")
            if not message.is_read:
                row_classes.append("unread")
            correspondent = (
                f"To: {message.recipient_email}"
                if selected_folder == EmailFolder.SENT
                else message.sender_name
            )

            with ui.column().classes(" ".join(row_classes)).on(
                "click",
                lambda message_id=message.id: select_message(message_id),
            ):
                with ui.row().classes("items-start justify-between w-full gap-2"):
                    ui.label(correspondent).classes("message-sender text-sm")
                    ui.label(format_date(message)).classes("message-date text-xs")
                ui.label(message.subject).classes("message-subject text-sm")
                ui.label(preview_text(message)).classes("message-preview text-xs")

        def render_reader_content(message: EmailMessageRead | None) -> None:
            if message is None:
                with ui.column().classes("empty-state"):
                    ui.icon("mail", size="40px").classes("text-grey-5")
                    ui.label("Select a message").classes("text-subtitle1")
                    ui.label("The selected message will appear here.").classes("text-caption")
                return

            with ui.column().classes("reader-header"):
                with ui.row().classes("reader-actions"):
                    if message.is_read:
                        ui.button(
                            "Mark unread",
                            icon="mark_email_unread",
                            on_click=lambda message_id=message.id: set_message_read(
                                message_id,
                                False,
                            ),
                        ).props("outline")
                    else:
                        ui.button(
                            "Mark read",
                            icon="done",
                            on_click=lambda message_id=message.id: set_message_read(
                                message_id,
                                True,
                            ),
                        ).props("unelevated")
                    ui.button(
                        "Delete",
                        icon="delete",
                        on_click=lambda message_id=message.id, subject=message.subject: (
                            ask_delete_message(message_id, subject)
                        ),
                    ).props("outline color=negative")
                ui.label(message.subject).classes("text-h6")
                status_label = "Read" if message.is_read else "Unread"
                status_class = "reader-status" if message.is_read else "reader-status unread"
                ui.label(status_label).classes(status_class)
                ui.label(f"From: {message.sender_name} <{message.sender_email}>").classes(
                    "reader-meta text-sm"
                )
                ui.label(f"To: {message.recipient_email}").classes("reader-meta text-sm")
                ui.label(f"Date: {format_date(message)}").classes("reader-meta text-sm")
            with ui.column().classes("reader-body"):
                ui.label(message.body)

        def refresh_mail_content() -> None:
            nonlocal selected_message_id
            if (
                folder_container is None
                or message_container is None
                or reader_container is None
            ):
                return

            try:
                folder_messages = {folder: list_messages(folder) for folder in FOLDER_LABELS}
            except Exception as exc:
                notify_error(exc)
                return

            messages = folder_messages[selected_folder]
            message_ids = {message.id for message in messages}
            if selected_message_id not in message_ids:
                selected_message_id = messages[0].id if messages else None
            selected_message = next(
                (message for message in messages if message.id == selected_message_id),
                None,
            )

            folder_container.clear()
            with folder_container:
                ui.label(settings.app_name).classes("text-subtitle1 text-weight-bold")
                ui.label("Folders").classes("text-caption text-grey-7")
                for folder in FOLDER_ORDER:
                    if folder is None:
                        ui.separator().classes("folder-separator")
                    else:
                        render_folder_button(folder, len(folder_messages[folder]))

            message_container.clear()
            with message_container:
                with ui.column().classes("message-pane-header"):
                    ui.label(FOLDER_LABELS[selected_folder]).classes("text-subtitle1")
                    ui.label(f"{len(messages)} messages").classes("text-caption text-grey-7")

                with ui.column().classes("message-list"):
                    if not messages:
                        with ui.column().classes("empty-state"):
                            ui.icon("mark_email_unread", size="36px").classes("text-grey-5")
                            ui.label("There are no messages in this folder.").classes(
                                "text-caption"
                            )
                    else:
                        for message in messages:
                            render_message_row(message)

            reader_container.clear()
            with reader_container:
                render_reader_content(selected_message)

        def refresh_mail_from_event() -> None:
            if current_view == "mail":
                refresh_mail_content()

        def render_mail() -> None:
            nonlocal current_view, folder_container, message_container, reader_container
            current_view = "mail"
            main_container.clear()
            with main_container, ui.row().classes("email-workspace"):
                folder_container = ui.column().classes("folder-pane")
                message_container = ui.column().classes("message-pane")
                reader_container = ui.column().classes("reader-pane")
            refresh_mail_content()

        def render_placeholder(title: str, details: str) -> None:
            main_container.clear()
            with main_container, ui.column().classes("placeholder-view"):
                ui.icon("construction", size="42px").classes("text-grey-5")
                ui.label(title).classes("text-h6")
                ui.label(details).classes("text-body2")

        def render_info() -> None:
            nonlocal current_view
            current_view = "info"
            main_container.clear()
            with main_container, ui.column().classes("info-view"):
                render_app_status(
                    app_name=settings.app_name,
                    host=settings.host,
                    port=settings.port,
                    db_path=settings.db_path,
                    show_openapi_link=False,
                    title="Application Status",
                    address_label="Address",
                    database_label="Database",
                )
                ui.label(last_action).classes("text-caption text-grey-7")
                ui.html(
                    '<iframe class="openapi-frame" src="/docs" title="OpenAPI"></iframe>'
                ).classes("w-full")

        with ui.dialog() as delete_dialog, ui.card().classes("confirm-dialog-card"):
            ui.label("Delete message?").classes("text-h6")
            ui.label("This message will be permanently deleted.").classes("text-body2")
            delete_subject_label = ui.label("").classes("text-caption text-grey-7")
            with ui.row().classes("send-dialog-actions"):
                ui.button("Cancel", on_click=delete_dialog.close).props("flat")
                ui.button(
                    "Delete",
                    icon="delete",
                    on_click=delete_selected_message,
                ).props("unelevated color=negative")

        with ui.dialog() as send_dialog, ui.card().classes("send-dialog-card"):
            ui.label("Send Message").classes("text-h6")
            recipient_input = ui.input("Email").classes("w-full")
            subject_input = ui.input("Subject").classes("w-full")
            body_input = ui.textarea("Text").classes("w-full").props("rows=8")
            with ui.row().classes("send-dialog-actions"):
                ui.button("Cancel", on_click=send_dialog.close).props("flat")
                ui.button("Send", icon="send", on_click=send_message).props("unelevated")

        with ui.dialog() as receive_dialog, ui.card().classes("send-dialog-card"):
            ui.label("Receive Message").classes("text-h6")
            sender_input = ui.input("Email").classes("w-full")
            received_subject_input = ui.input("Subject").classes("w-full")
            received_body_input = ui.textarea("Text").classes("w-full").props("rows=8")
            with ui.row().classes("send-dialog-actions"):
                ui.button("Cancel", on_click=receive_dialog.close).props("flat")
                ui.button("Receive", icon="download", on_click=receive_message).props(
                    "unelevated"
                )

        with ui.column().classes("email-shell"):
            with ui.row().classes("email-toolbar"):
                ui.button("Mail", icon="mail", on_click=render_mail).props("unelevated")
                ui.button(
                    "Send Message",
                    icon="send",
                    on_click=send_dialog.open,
                ).props("outline")
                ui.button(
                    "Receive Message",
                    icon="download",
                    on_click=receive_dialog.open,
                ).props("outline")
                ui.button(
                    "Receive All",
                    icon="cloud_download",
                    on_click=receive_all_messages,
                ).props("outline")
                ui.button("Info", icon="info", on_click=render_info).props("flat")

            main_container = ui.element("main").classes("email-main")

        ui.on("email-messages-changed", lambda: refresh_mail_from_event())
        ui.run_javascript(
            """
            (() => {
                if (window.emailAppEventSource) {
                    window.emailAppEventSource.close();
                }
                const source = new EventSource('/api/messages/events');
                source.addEventListener('messages_changed', () => {
                    emitEvent('emailMessagesChanged');
                });
                window.addEventListener('beforeunload', () => source.close(), { once: true });
                window.emailAppEventSource = source;
            })();
            """
        )
        render_mail()
