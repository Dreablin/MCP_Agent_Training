from collections.abc import Awaitable, Callable
from typing import Any, TypedDict

import httpx
from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from apps.email_MCP.config import EmailMCPSettings


class EmailFolderInfo(TypedDict):
    id: str
    label: str


class EmailMessageInfo(TypedDict):
    id: str
    sender_name: str
    sender_email: str
    recipient_email: str
    subject: str
    body: str
    received_at: str
    folder: str
    is_read: bool
    created_at: str
    updated_at: str


def register_tools(mcp: MCPServer, settings: EmailMCPSettings) -> None:
    mcp.add_tool(
        build_list_email_folders_tool(settings),
        name="list_email_folders",
        title="List email folders",
        annotations=ToolAnnotations(
            read_only_hint=True,
            open_world_hint=False,
        ),
    )
    mcp.add_tool(
        build_get_oldest_unread_email_tool(settings),
        name="get_oldest_unread_email",
        title="Get oldest unread email",
        annotations=ToolAnnotations(
            read_only_hint=True,
            open_world_hint=False,
        ),
    )
    mcp.add_tool(
        build_mark_email_read_tool(settings),
        name="mark_email_read",
        title="Mark email as read",
        annotations=ToolAnnotations(
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        ),
    )
    mcp.add_tool(
        build_move_email_to_folder_tool(settings),
        name="move_email_to_folder",
        title="Move email to folder",
        annotations=ToolAnnotations(
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        ),
    )
    mcp.add_tool(
        build_send_email_tool(settings),
        name="send_email",
        title="Send email",
        annotations=ToolAnnotations(
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=False,
            open_world_hint=False,
        ),
    )


def build_list_email_folders_tool(
    settings: EmailMCPSettings,
) -> Callable[[], Awaitable[list[EmailFolderInfo]]]:
    async def list_email_folders() -> list[EmailFolderInfo]:
        """Get the list of available folders in the Email app mailbox."""
        return await get_email_folders(settings)

    return list_email_folders


def build_get_oldest_unread_email_tool(
    settings: EmailMCPSettings,
) -> Callable[[], Awaitable[EmailMessageInfo | None]]:
    async def get_oldest_unread_email() -> EmailMessageInfo | None:
        """Get the oldest unread email message from the Email app mailbox."""
        return await get_oldest_unread_email_from_api(settings)

    return get_oldest_unread_email


def build_mark_email_read_tool(
    settings: EmailMCPSettings,
) -> Callable[[str], Awaitable[EmailMessageInfo]]:
    async def mark_email_read(message_id: str) -> EmailMessageInfo:
        """Mark an email message as read by ID."""
        return await mark_email_read_in_api(settings, message_id)

    return mark_email_read


def build_move_email_to_folder_tool(
    settings: EmailMCPSettings,
) -> Callable[[str, str], Awaitable[EmailMessageInfo]]:
    async def move_email_to_folder(message_id: str, folder: str) -> EmailMessageInfo:
        """Move an email message to a folder by ID."""
        return await move_email_to_folder_in_api(settings, message_id, folder)

    return move_email_to_folder


def build_send_email_tool(
    settings: EmailMCPSettings,
) -> Callable[[str, str, str, str, str], Awaitable[EmailMessageInfo]]:
    async def send_email(
        sender_name: str,
        sender_email: str,
        recipient_email: str,
        subject: str,
        body: str,
    ) -> EmailMessageInfo:
        """Send an email message by placing it in the Sent folder."""
        return await send_email_via_api(
            settings,
            sender_name=sender_name,
            sender_email=sender_email,
            recipient_email=recipient_email,
            subject=subject,
            body=body,
        )

    return send_email


async def get_email_folders(
    settings: EmailMCPSettings,
    transport: httpx.AsyncBaseTransport | None = None,
) -> list[EmailFolderInfo]:
    async with httpx.AsyncClient(
        timeout=settings.email_api_timeout_seconds,
        transport=transport,
    ) as client:
        response = await client.get(settings.email_api_folders_url)
        response.raise_for_status()

    return parse_email_folders_response(response.json())


async def get_oldest_unread_email_from_api(
    settings: EmailMCPSettings,
    transport: httpx.AsyncBaseTransport | None = None,
) -> EmailMessageInfo | None:
    async with httpx.AsyncClient(
        timeout=settings.email_api_timeout_seconds,
        transport=transport,
    ) as client:
        response = await client.get(
            settings.email_api_messages_url,
            params={"is_read": "false", "limit": "1"},
        )
        response.raise_for_status()

    messages = parse_email_messages_response(response.json())
    if not messages:
        return None
    return messages[0]


async def mark_email_read_in_api(
    settings: EmailMCPSettings,
    message_id: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> EmailMessageInfo:
    async with httpx.AsyncClient(
        timeout=settings.email_api_timeout_seconds,
        transport=transport,
    ) as client:
        response = await client.post(f"{settings.email_api_messages_url}/{message_id}/read")
        response.raise_for_status()

    return parse_email_message_response(response.json())


async def move_email_to_folder_in_api(
    settings: EmailMCPSettings,
    message_id: str,
    folder: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> EmailMessageInfo:
    async with httpx.AsyncClient(
        timeout=settings.email_api_timeout_seconds,
        transport=transport,
    ) as client:
        response = await client.post(
            f"{settings.email_api_messages_url}/{message_id}/move",
            json={"folder": folder},
        )
        response.raise_for_status()

    return parse_email_message_response(response.json())


async def send_email_via_api(
    settings: EmailMCPSettings,
    *,
    sender_name: str,
    sender_email: str,
    recipient_email: str,
    subject: str,
    body: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> EmailMessageInfo:
    async with httpx.AsyncClient(
        timeout=settings.email_api_timeout_seconds,
        transport=transport,
    ) as client:
        create_response = await client.post(
            settings.email_api_messages_url,
            json={
                "sender_name": sender_name,
                "sender_email": sender_email,
                "recipient_email": recipient_email,
                "subject": subject,
                "body": body,
            },
        )
        create_response.raise_for_status()
        created = parse_email_message_response(create_response.json())

        move_response = await client.post(
            f"{settings.email_api_messages_url}/{created['id']}/move",
            json={"folder": "sent"},
        )
        move_response.raise_for_status()

    return parse_email_message_response(move_response.json())


def parse_email_folders_response(payload: Any) -> list[EmailFolderInfo]:
    if not isinstance(payload, list):
        msg = "Email API folders response must be a list."
        raise ValueError(msg)

    folders: list[EmailFolderInfo] = []
    for item in payload:
        if not isinstance(item, dict):
            msg = "Email API folder item must be an object."
            raise ValueError(msg)

        folder_id = item.get("id")
        label = item.get("label")
        if not isinstance(folder_id, str) or not isinstance(label, str):
            msg = "Email API folder item must contain string id and label."
            raise ValueError(msg)

        folders.append({"id": folder_id, "label": label})

    return folders


def parse_email_messages_response(payload: Any) -> list[EmailMessageInfo]:
    if not isinstance(payload, list):
        msg = "Email API messages response must be a list."
        raise ValueError(msg)

    messages: list[EmailMessageInfo] = []
    for item in payload:
        if not isinstance(item, dict):
            msg = "Email API message item must be an object."
            raise ValueError(msg)

        message = parse_email_message_response(item)
        messages.append(message)

    return messages


def parse_email_message_response(payload: dict[str, Any]) -> EmailMessageInfo:
    string_fields = [
        "id",
        "sender_name",
        "sender_email",
        "recipient_email",
        "subject",
        "body",
        "received_at",
        "folder",
        "created_at",
        "updated_at",
    ]
    for field_name in string_fields:
        if not isinstance(payload.get(field_name), str):
            msg = f"Email API message item must contain string {field_name}."
            raise ValueError(msg)

    if not isinstance(payload.get("is_read"), bool):
        msg = "Email API message item must contain boolean is_read."
        raise ValueError(msg)

    return {
        "id": payload["id"],
        "sender_name": payload["sender_name"],
        "sender_email": payload["sender_email"],
        "recipient_email": payload["recipient_email"],
        "subject": payload["subject"],
        "body": payload["body"],
        "received_at": payload["received_at"],
        "folder": payload["folder"],
        "is_read": payload["is_read"],
        "created_at": payload["created_at"],
        "updated_at": payload["updated_at"],
    }
