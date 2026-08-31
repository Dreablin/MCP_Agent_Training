from __future__ import annotations

import builtins
import json
from pathlib import Path

from pydantic import ValidationError

from apps.email_app.events import EmailEvent
from apps.email_app.models import EmailFolder
from apps.email_app.repositories import EmailMessageRepository, EmailSearch
from apps.email_app.schemas import (
    EmailFolderRead,
    EmailMessageCreate,
    EmailMessageImport,
    EmailMessageRead,
)
from shared.errors import NotFoundError, ValidationAppError

FOLDER_LABELS: dict[EmailFolder, str] = {
    EmailFolder.INBOX: "Inbox",
    EmailFolder.SENT: "Sent",
    EmailFolder.SPAM: "Spam",
    EmailFolder.FRIENDS: "Friends",
    EmailFolder.WORK: "Work",
    EmailFolder.LOGS: "Logs",
    EmailFolder.TRASH: "Trash",
}


class EmailMessageService:
    def __init__(self, repository: EmailMessageRepository) -> None:
        self._repository = repository
        self._events: list[EmailEvent] = []

    def create(self, payload: EmailMessageCreate) -> EmailMessageRead:
        message = self._to_read_model(self._repository.create(payload))
        self._record_event("created", message)
        return message

    def create_sent(self, payload: EmailMessageCreate) -> EmailMessageRead:
        message = self._to_read_model(
            self._repository.create(payload, folder=EmailFolder.SENT, is_read=True)
        )
        self._record_event("sent", message)
        return message

    def receive_all_from_directory(self, source_dir: Path) -> builtins.list[EmailMessageRead]:
        messages = self._load_messages_from_directory(source_dir)
        created_messages: builtins.list[EmailMessageRead] = []
        for message in sorted(messages, key=lambda item: item.date):
            created_message = self._to_read_model(
                self._repository.create(
                    message.to_create_payload(),
                    folder=EmailFolder.INBOX,
                    is_read=False,
                )
            )
            self._record_event("created", created_message)
            created_messages.append(created_message)
        return created_messages

    def list(self, search: EmailSearch | None = None) -> list[EmailMessageRead]:
        return [self._to_read_model(message) for message in self._repository.list(search)]

    def list_folders(self) -> builtins.list[EmailFolderRead]:
        return [EmailFolderRead(id=folder, label=label) for folder, label in FOLDER_LABELS.items()]

    def get(self, message_id: str) -> EmailMessageRead:
        message = self._repository.get(message_id)
        if message is None:
            raise NotFoundError("Email message not found", details={"id": message_id})
        return self._to_read_model(message)

    def mark_read(self, message_id: str, is_read: bool) -> EmailMessageRead:
        message = self._repository.update(message_id, {"is_read": is_read})
        if message is None:
            raise NotFoundError("Email message not found", details={"id": message_id})
        read_message = self._to_read_model(message)
        self._record_event("updated", read_message)
        return read_message

    def move_to_folder(self, message_id: str, folder: EmailFolder) -> EmailMessageRead:
        return self._move_to_folder(message_id, folder)

    def delete_from_trash(self, message_id: str) -> None:
        message = self._repository.get(message_id)
        if message is None:
            raise NotFoundError("Email message not found", details={"id": message_id})
        if message.folder != EmailFolder.TRASH.value:
            raise ValidationAppError(
                "Only messages in trash can be permanently deleted",
                details={"id": message_id, "folder": message.folder},
            )
        self._repository.delete(message_id)
        self._events.append(
            EmailEvent(action="deleted", message_id=message_id, folder=EmailFolder.TRASH)
        )

    def delete_permanently(self, message_id: str) -> None:
        message = self._repository.get(message_id)
        if message is None:
            raise NotFoundError("Email message not found", details={"id": message_id})
        folder = EmailFolder(message.folder)
        self._repository.delete(message_id)
        self._events.append(EmailEvent(action="deleted", message_id=message_id, folder=folder))

    def empty_trash(self) -> dict[str, int]:
        deleted_count = self._repository.empty_trash()
        if deleted_count:
            self._events.append(EmailEvent(action="trash_emptied", folder=EmailFolder.TRASH))
        return {"deleted_count": deleted_count}

    def pull_events(self) -> builtins.list[EmailEvent]:
        events = list(self._events)
        self._events.clear()
        return events

    def _move_to_folder(self, message_id: str, folder: EmailFolder) -> EmailMessageRead:
        message = self._repository.update(message_id, {"folder": folder})
        if message is None:
            raise NotFoundError("Email message not found", details={"id": message_id})
        moved_message = self._to_read_model(message)
        self._record_event("moved", moved_message)
        return moved_message

    def _record_event(self, action: str, message: EmailMessageRead) -> None:
        self._events.append(
            EmailEvent(action=action, message_id=message.id, folder=message.folder)
        )

    @staticmethod
    def _load_messages_from_directory(source_dir: Path) -> builtins.list[EmailMessageImport]:
        if not source_dir.is_dir():
            raise ValidationAppError(
                "Message source directory was not found",
                details={"path": str(source_dir)},
            )

        messages: builtins.list[EmailMessageImport] = []
        for path in sorted(source_dir.glob("*.json")):
            try:
                raw_content = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise ValidationAppError(
                    "Message source file is not valid JSON",
                    details={"path": str(path), "error": str(exc)},
                ) from exc

            raw_messages = raw_content if isinstance(raw_content, list) else [raw_content]
            for raw_message in raw_messages:
                if not isinstance(raw_message, dict):
                    raise ValidationAppError(
                        "Message source file must contain an object or an array of objects",
                        details={"path": str(path)},
                    )
                try:
                    messages.append(EmailMessageImport.model_validate(raw_message))
                except ValidationError as exc:
                    raise ValidationAppError(
                        "Message source file has invalid message data",
                        details={"path": str(path), "error": str(exc)},
                    ) from exc
        return messages

    @staticmethod
    def _to_read_model(message: object) -> EmailMessageRead:
        return EmailMessageRead.model_validate(message)
