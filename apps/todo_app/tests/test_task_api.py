from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from apps.todo_app.config import TodoAppSettings
from apps.todo_app.database import Base
from apps.todo_app.main import create_app


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    settings = TodoAppSettings(db_path=tmp_path / "todo.db")
    app = create_app(settings, include_ui=False)
    Base.metadata.create_all(app.state.engine)
    return TestClient(app)


def api_payload(title: str = "Prepare meeting notes") -> dict[str, str]:
    return {
        "title": title,
        "description": "Collect agenda items",
        "priority": "high",
    }


def create_task(client: TestClient, title: str = "Prepare meeting notes") -> dict[str, Any]:
    response = client.post("/api/tasks", json=api_payload(title))
    assert response.status_code == 201
    return cast(dict[str, Any], response.json())


def test_create_get_and_list_task(client: TestClient) -> None:
    created = create_task(client)

    get_response = client.get(f"/api/tasks/{created['id']}")
    list_response = client.get("/api/tasks")

    assert get_response.status_code == 200
    assert get_response.json()["title"] == "Prepare meeting notes"
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1


def test_due_at_is_not_accepted_by_api(client: TestClient) -> None:
    payload = api_payload()
    payload["due_at"] = "2026-08-12T13:00:00-05:00"

    response = client.post("/api/tasks", json=payload)

    assert response.status_code == 422


def test_complete_reopen_and_cancel_task(client: TestClient) -> None:
    created = create_task(client)

    completed = client.post(f"/api/tasks/{created['id']}/complete")
    reopened = client.post(f"/api/tasks/{created['id']}/reopen")
    cancelled = client.post(f"/api/tasks/{created['id']}/cancel")

    assert completed.json()["status"] == "completed"
    assert completed.json()["completed_at"] is not None
    assert reopened.json()["status"] == "open"
    assert reopened.json()["completed_at"] is None
    assert cancelled.json()["status"] == "cancelled"


def test_filter_and_search_tasks(client: TestClient) -> None:
    first = create_task(client, "Prepare deck")
    create_task(client, "Buy milk")
    client.patch(f"/api/tasks/{first['id']}", json={"status": "in_progress"})

    status_response = client.get("/api/tasks", params={"status": "in_progress"})
    query_response = client.get("/api/tasks", params={"query": "milk"})

    assert [task["id"] for task in status_response.json()] == [first["id"]]
    assert [task["title"] for task in query_response.json()] == ["Buy milk"]


def test_missing_task_returns_standard_error(client: TestClient) -> None:
    response = client.get("/api/tasks/missing")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
