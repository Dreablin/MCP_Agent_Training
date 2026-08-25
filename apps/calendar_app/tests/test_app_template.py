from pathlib import Path

from fastapi.testclient import TestClient

from apps.calendar_app.config import CalendarAppSettings
from apps.calendar_app.main import create_app


def test_calendar_app_health_endpoint(tmp_path: Path) -> None:
    settings = CalendarAppSettings(db_path=tmp_path / "calendar.db")
    app = create_app(settings, include_ui=False)

    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "app_name": "Calendar App",
        "version": "0.1.0",
    }
