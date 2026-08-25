from __future__ import annotations

import builtins

from apps.email_app.models import EmailFolder
from apps.email_app.repositories import EmailMessageRepository, EmailSearch
from apps.email_app.schemas import EmailFolderRead, EmailMessageCreate, EmailMessageRead
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

    def create(self, payload: EmailMessageCreate) -> EmailMessageRead:
        return self._to_read_model(self._repository.create(payload))

    def create_sent(self, payload: EmailMessageCreate) -> EmailMessageRead:
        message = self._repository.create(payload, folder=EmailFolder.SENT, is_read=True)
        return self._to_read_model(message)

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
        return self._to_read_model(message)

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

    def delete_permanently(self, message_id: str) -> None:
        if not self._repository.delete(message_id):
            raise NotFoundError("Email message not found", details={"id": message_id})

    def empty_trash(self) -> dict[str, int]:
        return {"deleted_count": self._repository.empty_trash()}

    def _move_to_folder(self, message_id: str, folder: EmailFolder) -> EmailMessageRead:
        message = self._repository.update(message_id, {"folder": folder})
        if message is None:
            raise NotFoundError("Email message not found", details={"id": message_id})
        return self._to_read_model(message)

    @staticmethod
    def _to_read_model(message: object) -> EmailMessageRead:
        return EmailMessageRead.model_validate(message)
