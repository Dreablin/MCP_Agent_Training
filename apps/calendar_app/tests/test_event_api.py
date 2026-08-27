from datetime import datetime
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from apps.calendar_app.config import CalendarAppSettings
from apps.calendar_app.database import Base
from apps.calendar_app.main import create_app


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    settings = CalendarAppSettings(db_path=tmp_path / "calendar.db")
    app = create_app(settings, include_ui=False)
    Base.metadata.create_all(app.state.engine)
    return TestClient(app)


def api_payload(title: str = "Meeting with Anna") -> dict[str, object]:
    return {
        "title": title,
        "description": "Discuss training project",
        "start_at": datetime(2026, 8, 12, 14, 30).isoformat(),
        "end_at": datetime(2026, 8, 12, 15, 30).isoformat(),
        "location": "Office",
        "participants": [{"name": "Anna", "email": "anna@example.test"}],
    }


def create_event(client: TestClient, title: str = "Meeting with Anna") -> dict[str, Any]:
    response = client.post("/api/events", json=api_payload(title))
    assert response.status_code == 201
    return cast(dict[str, Any], response.json())


def test_create_get_and_list_event(client: TestClient) -> None:
    created = create_event(client)

    get_response = client.get(f"/api/events/{created['id']}")
    list_response = client.get("/api/events")

    assert get_response.status_code == 200
    assert get_response.json()["title"] == "Meeting with Anna"
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1


def test_create_event_without_status_and_location(client: TestClient) -> None:
    payload = api_payload()
    payload.pop("location")

    response = client.post("/api/events", json=payload)

    assert response.status_code == 201
    assert "timezone" not in response.json()
    assert response.json()["status"] == "confirmed"
    assert response.json()["location"] == ""


def test_cancel_restore_and_delete_event(client: TestClient) -> None:
    created = create_event(client)

    cancelled = client.post(f"/api/events/{created['id']}/cancel")
    restored = client.post(f"/api/events/{created['id']}/restore")
    deleted = client.delete(f"/api/events/{created['id']}")

    assert cancelled.json()["status"] == "cancelled"
    assert restored.json()["status"] == "confirmed"
    assert deleted.status_code == 204


def test_create_cancel_restore_and_delete_event_with_form_fields(client: TestClient) -> None:
    payload = {
        "title": "Design review",
        "description": "Discuss the calendar dialog fields.",
        "start_at": datetime(2026, 8, 21, 18, 0).isoformat(),
        "end_at": datetime(2026, 8, 21, 19, 0).isoformat(),
        "status": "confirmed",
        "location": "",
        "participants": [{"name": "Anna", "email": "anna@example.test"}],
    }

    created_response = client.post("/api/events", json=payload)

    assert created_response.status_code == 201
    created = created_response.json()
    assert created["title"] == "Design review"
    assert created["description"] == "Discuss the calendar dialog fields."
    assert created["participants"] == [{"name": "Anna", "email": "anna@example.test"}]
    assert "timezone" not in created

    cancelled_response = client.post(f"/api/events/{created['id']}/cancel")
    assert cancelled_response.status_code == 200
    assert cancelled_response.json()["status"] == "cancelled"

    restored_response = client.post(f"/api/events/{created['id']}/restore")
    assert restored_response.status_code == 200
    assert restored_response.json()["status"] == "confirmed"

    delete_response = client.delete(f"/api/events/{created['id']}")
    get_deleted_response = client.get(f"/api/events/{created['id']}")

    assert delete_response.status_code == 204
    assert get_deleted_response.status_code == 404


def test_search_and_overlap_endpoint(client: TestClient) -> None:
    created = create_event(client)

    search_response = client.get("/api/events", params={"query": "anna"})
    overlap_response = client.get(
        "/api/events/overlaps",
        params={
            "start_at": "2026-08-12T15:00:00",
            "end_at": "2026-08-12T16:00:00",
        },
    )
    excluded_response = client.get(
        "/api/events/overlaps",
        params={
            "start_at": "2026-08-12T15:00:00",
            "end_at": "2026-08-12T16:00:00",
            "exclude_event_id": created["id"],
        },
    )

    assert [event["id"] for event in search_response.json()] == [created["id"]]
    assert [event["id"] for event in overlap_response.json()] == [created["id"]]
    assert excluded_response.json() == []


def test_invalid_event_range_returns_standard_error(client: TestClient) -> None:
    payload = api_payload()
    payload["end_at"] = payload["start_at"]

    response = client.post("/api/events", json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_timezone_offset_returns_standard_error(client: TestClient) -> None:
    payload = api_payload()
    payload["start_at"] = "2026-08-12T14:30:00-05:00"

    response = client.post("/api/events", json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_timezone_offset_query_returns_standard_error(client: TestClient) -> None:
    response = client.get(
        "/api/events/overlaps",
        params={
            "start_at": "2026-08-12T15:00:00-05:00",
            "end_at": "2026-08-12T16:00:00",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_overlapping_create_returns_conflict_error(client: TestClient) -> None:
    created = create_event(client)
    payload = api_payload("Overlapping meeting")
    payload["start_at"] = "2026-08-12T15:00:00"
    payload["end_at"] = "2026-08-12T16:00:00"

    response = client.post("/api/events", json=payload)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONFLICT"
    assert response.json()["error"]["details"]["conflicting_event_ids"] == [created["id"]]


def test_overlapping_update_returns_conflict_error(client: TestClient) -> None:
    first = create_event(client)
    second_payload = api_payload("Second meeting")
    second_payload["start_at"] = "2026-08-12T16:00:00"
    second_payload["end_at"] = "2026-08-12T17:00:00"
    second_response = client.post("/api/events", json=second_payload)
    second = second_response.json()

    response = client.patch(
        f"/api/events/{second['id']}",
        json={
            "start_at": "2026-08-12T15:00:00",
            "end_at": "2026-08-12T16:00:00",
        },
    )

    assert second_response.status_code == 201
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONFLICT"
    assert response.json()["error"]["details"]["conflicting_event_ids"] == [first["id"]]


def test_missing_event_returns_standard_error(client: TestClient) -> None:
    response = client.get("/api/events/missing")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
