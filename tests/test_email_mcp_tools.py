import httpx
import pytest

from apps.email_MCP.config import EmailMCPSettings
from apps.email_MCP.server import create_mcp_server
from apps.email_MCP.tools import get_email_folders, parse_email_folders_response


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


def test_parse_email_folders_response_rejects_invalid_payload() -> None:
    with pytest.raises(ValueError, match="must be a list"):
        parse_email_folders_response({"id": "inbox", "label": "Inbox"})


def test_parse_email_folders_response_rejects_invalid_items() -> None:
    with pytest.raises(ValueError, match="string id and label"):
        parse_email_folders_response([{"id": "inbox"}])
