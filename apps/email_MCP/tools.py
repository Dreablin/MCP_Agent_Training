from collections.abc import Awaitable, Callable
from typing import Any, TypedDict

import httpx
from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from apps.email_MCP.config import EmailMCPSettings


class EmailFolderInfo(TypedDict):
    id: str
    label: str


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

def build_list_email_folders_tool(
    settings: EmailMCPSettings,
) -> Callable[[], Awaitable[list[EmailFolderInfo]]]:
    async def list_email_folders() -> list[EmailFolderInfo]:
        """Get the list of available folders in the Email app mailbox."""
        return await get_email_folders(settings)

    return list_email_folders


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
