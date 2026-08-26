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


def test_calendar_app_lifespan_starts_with_embedded_mcp(tmp_path: Path) -> None:
    settings = CalendarAppSettings(db_path=tmp_path / "calendar.db")
    app = create_app(settings, include_ui=False)

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200


def test_calendar_app_lifespan_disposes_engine_on_shutdown(tmp_path: Path) -> None:
    settings = CalendarAppSettings(db_path=tmp_path / "calendar.db")
    app = create_app(settings, include_ui=False)
    disposed = False

    def dispose() -> None:
        nonlocal disposed
        disposed = True

    app.state.engine.dispose = dispose

    with TestClient(app):
        assert disposed is False

    assert disposed is True
