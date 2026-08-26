import json

import httpx
import pytest

from apps.email_MCP.config import EmailMCPSettings
from apps.email_MCP.server import create_mcp_server
from apps.email_MCP.tools import (
    get_email_folders,
    get_oldest_unread_email_from_api,
    mark_email_read_in_api,
    move_email_to_folder_in_api,
    parse_email_folders_response,
    parse_email_messages_response,
)


@pytest.mark.anyio
async def test_list_email_folders_tool_has_annotations() -> None:
    mcp = create_mcp_server(EmailMCPSettings())
    tools = await mcp.list_tools()

    tool = next(tool for tool in tools if tool.name == "list_email_folders")

    assert tool.title == "List email folders"
    assert tool.annotations is not None
    assert tool.annotations.read_only_hint is True
    assert tool.annotations.open_world_hint is False


@pytest.mark.anyio
async def test_get_oldest_unread_email_tool_has_annotations() -> None:
    mcp = create_mcp_server(EmailMCPSettings())
    tools = await mcp.list_tools()

    tool = next(tool for tool in tools if tool.name == "get_oldest_unread_email")

    assert tool.title == "Get oldest unread email"
    assert tool.annotations is not None
    assert tool.annotations.read_only_hint is True
    assert tool.annotations.open_world_hint is False


@pytest.mark.anyio
async def test_mark_email_read_tool_has_annotations() -> None:
    mcp = create_mcp_server(EmailMCPSettings())
    tools = await mcp.list_tools()

    tool = next(tool for tool in tools if tool.name == "mark_email_read")

    assert tool.title == "Mark email as read"
    assert tool.annotations is not None
    assert tool.annotations.read_only_hint is False
    assert tool.annotations.destructive_hint is False
    assert tool.annotations.idempotent_hint is True
    assert tool.annotations.open_world_hint is False


@pytest.mark.anyio
async def test_move_email_to_folder_tool_has_annotations() -> None:
    mcp = create_mcp_server(EmailMCPSettings())
    tools = await mcp.list_tools()

    tool = next(tool for tool in tools if tool.name == "move_email_to_folder")

    assert tool.title == "Move email to folder"
    assert tool.annotations is not None
    assert tool.annotations.read_only_hint is False
    assert tool.annotations.destructive_hint is False
    assert tool.annotations.idempotent_hint is True
    assert tool.annotations.open_world_hint is False


@pytest.mark.anyio
async def test_get_email_folders_calls_email_api() -> None:
    requested_urls: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        return httpx.Response(
            200,
            json=[
                {"id": "inbox", "label": "Inbox"},
                {"id": "trash", "label": "Trash"},
            ],
    )

    settings = EmailMCPSettings()
    folders = await get_email_folders(settings, transport=httpx.MockTransport(handler))

    assert requested_urls == ["http://127.0.0.1:8011/api/messages/folders"]
    assert folders == [
        {"id": "inbox", "label": "Inbox"},
        {"id": "trash", "label": "Trash"},
    ]


@pytest.mark.anyio
async def test_get_oldest_unread_email_calls_email_api() -> None:
    requested_urls: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        return httpx.Response(200, json=[email_message_payload("oldest-message")])

    settings = EmailMCPSettings()
    message = await get_oldest_unread_email_from_api(
        settings,
        transport=httpx.MockTransport(handler),
    )

    assert requested_urls == ["http://127.0.0.1:8011/api/messages?is_read=false&limit=1"]
    assert message is not None
    assert message["id"] == "oldest-message"
    assert message["is_read"] is False


@pytest.mark.anyio
async def test_get_oldest_unread_email_returns_none_when_mailbox_has_no_unread() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    settings = EmailMCPSettings()
    message = await get_oldest_unread_email_from_api(
        settings,
        transport=httpx.MockTransport(handler),
    )

    assert message is None


@pytest.mark.anyio
async def test_mark_email_read_calls_email_api() -> None:
    requested_methods_and_urls: list[tuple[str, str]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requested_methods_and_urls.append((request.method, str(request.url)))
        return httpx.Response(
            200,
            json=email_message_payload("message-id", is_read=True),
        )

    settings = EmailMCPSettings()
    message = await mark_email_read_in_api(
        settings,
        "message-id",
        transport=httpx.MockTransport(handler),
    )

    assert requested_methods_and_urls == [
        ("POST", "http://127.0.0.1:8011/api/messages/message-id/read")
    ]
    assert message["id"] == "message-id"
    assert message["is_read"] is True


@pytest.mark.anyio
async def test_move_email_to_folder_calls_email_api() -> None:
    requested_methods_urls_and_bodies: list[tuple[str, str, dict[str, object]]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requested_methods_urls_and_bodies.append(
            (request.method, str(request.url), json.loads(request.content.decode()))
        )
        return httpx.Response(
            200,
            json=email_message_payload("message-id", folder="work"),
        )

    settings = EmailMCPSettings()
    message = await move_email_to_folder_in_api(
        settings,
        "message-id",
        "work",
        transport=httpx.MockTransport(handler),
    )

    assert requested_methods_urls_and_bodies == [
        ("POST", "http://127.0.0.1:8011/api/messages/message-id/move", {"folder": "work"})
    ]
    assert message["id"] == "message-id"
    assert message["folder"] == "work"


def test_parse_email_folders_response_rejects_invalid_payload() -> None:
    with pytest.raises(ValueError, match="must be a list"):
        parse_email_folders_response({"id": "inbox", "label": "Inbox"})


def test_parse_email_folders_response_rejects_invalid_items() -> None:
    with pytest.raises(ValueError, match="string id and label"):
        parse_email_folders_response([{"id": "inbox"}])


def test_parse_email_messages_response_rejects_invalid_payload() -> None:
    with pytest.raises(ValueError, match="must be a list"):
        parse_email_messages_response(email_message_payload("message-id"))


def test_parse_email_messages_response_rejects_invalid_items() -> None:
    with pytest.raises(ValueError, match="string subject"):
        parse_email_messages_response([email_message_payload("message-id", subject=None)])


def email_message_payload(
    message_id: str,
    subject: str | None = "Hello",
    is_read: bool = False,
    folder: str = "inbox",
) -> dict[str, object]:
    return {
        "id": message_id,
        "sender_name": "Anna",
        "sender_email": "anna@example.test",
        "recipient_email": "me@example.test",
        "subject": subject,
        "body": "Body",
        "received_at": "2026-08-06T15:00:00+00:00",
        "folder": folder,
        "is_read": is_read,
        "created_at": "2026-08-06T15:00:00+00:00",
        "updated_at": "2026-08-06T15:00:00+00:00",
    }
