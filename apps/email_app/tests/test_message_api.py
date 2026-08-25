from datetime import datetime
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from apps.email_app.config import EmailAppSettings
from apps.email_app.database import Base
from apps.email_app.main import create_app


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    settings = EmailAppSettings(db_path=tmp_path / "email.db")
    app = create_app(settings, include_ui=False)
    Base.metadata.create_all(app.state.engine)
    return TestClient(app)


def api_payload(subject: str = "Meeting with Anna") -> dict[str, str]:
    return {
        "sender_name": "Anna",
        "sender_email": "anna@example.test",
        "recipient_email": "me@example.test",
        "subject": subject,
        "body": "Let's meet tomorrow.",
        "received_at": datetime(
            2026,
            8,
            6,
            12,
            0,
            tzinfo=ZoneInfo("America/Chicago"),
        ).isoformat(),
    }


def create_message(client: TestClient, subject: str = "Meeting with Anna") -> dict[str, Any]:
    response = client.post("/api/messages", json=api_payload(subject))
    assert response.status_code == 201
    return cast(dict[str, Any], response.json())


def test_create_get_and_list_message(client: TestClient) -> None:
    created = create_message(client)

    get_response = client.get(f"/api/messages/{created['id']}")
    list_response = client.get("/api/messages")

    assert get_response.status_code == 200
    assert get_response.json()["subject"] == "Meeting with Anna"
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1


def test_search_and_filter_messages(client: TestClient) -> None:
    first = create_message(client, "Meeting with Anna")
    second = create_message(client, "Weekly report")
    client.post(f"/api/messages/{second['id']}/move", json={"folder": "trash"})

    search_response = client.get("/api/messages", params={"query": "weekly"})
    inbox_response = client.get("/api/messages", params={"folder": "inbox"})
    trash_response = client.get("/api/messages", params={"folder": "trash"})

    assert [message["id"] for message in search_response.json()] == [second["id"]]
    assert [message["id"] for message in inbox_response.json()] == [first["id"]]
    assert [message["id"] for message in trash_response.json()] == [second["id"]]


def test_read_trash_delete_flow(client: TestClient) -> None:
    created = create_message(client)

    read_response = client.post(f"/api/messages/{created['id']}/read")
    trash_response = client.post(f"/api/messages/{created['id']}/move", json={"folder": "trash"})
    delete_response = client.delete(f"/api/messages/{created['id']}")
    get_response = client.get(f"/api/messages/{created['id']}")

    assert read_response.status_code == 200
    assert read_response.json()["is_read"] is True
    assert trash_response.status_code == 200
    assert trash_response.json()["folder"] == "trash"
    assert delete_response.status_code == 204
    assert get_response.status_code == 404
    assert get_response.json()["error"]["code"] == "NOT_FOUND"


def test_delete_rejects_message_outside_trash(client: TestClient) -> None:
    created = create_message(client)

    response = client.delete(f"/api/messages/{created['id']}")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_empty_trash(client: TestClient) -> None:
    first = create_message(client, "Keep me")
    second = create_message(client, "Delete me")
    client.post(f"/api/messages/{second['id']}/move", json={"folder": "trash"})

    response = client.delete("/api/messages/trash")
    list_response = client.get("/api/messages")

    assert response.status_code == 200
    assert response.json() == {"deleted_count": 1}
    assert [message["id"] for message in list_response.json()] == [first["id"]]


def test_list_folders(client: TestClient) -> None:
    response = client.get("/api/messages/folders")

    assert response.status_code == 200
    assert response.json() == [
        {"id": "inbox", "label": "Inbox"},
        {"id": "sent", "label": "Sent"},
        {"id": "spam", "label": "Spam"},
        {"id": "friends", "label": "Friends"},
        {"id": "work", "label": "Work"},
        {"id": "logs", "label": "Logs"},
        {"id": "trash", "label": "Trash"},
    ]
