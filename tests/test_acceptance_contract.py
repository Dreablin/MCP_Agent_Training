from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import inspect

from apps.calendar_app.config import CalendarAppSettings
from apps.calendar_app.main import create_app as create_calendar_app
from apps.email_app.config import EmailAppSettings
from apps.email_app.main import create_app as create_email_app
from apps.email_MCP.config import EmailMCPSettings
from apps.email_MCP.server import create_app as create_email_mcp_app
from apps.todo_app.config import TodoAppSettings
from apps.todo_app.main import create_app as create_todo_app


def test_default_ports_are_distinct() -> None:
    ports = {
        EmailAppSettings().port,
        EmailMCPSettings().port,
        TodoAppSettings().port,
        CalendarAppSettings().port,
    }

    assert ports == {8011, 8012, 8013, 8111}


def test_email_mcp_app_uses_streamable_http_endpoint() -> None:
    settings = EmailMCPSettings()
    app = create_email_mcp_app(settings)

    assert settings.streamable_http_path == "/mcp"
    assert any(getattr(route, "path", None) == "/mcp" for route in app.routes)


def test_email_mcp_settings_point_to_email_api() -> None:
    settings = EmailMCPSettings()

    assert not hasattr(settings, "db_path")
    assert settings.email_api_base_url == "http://127.0.0.1:8011"
    assert settings.email_api_messages_url == "http://127.0.0.1:8011/api/messages"
    assert settings.email_api_folders_url == "http://127.0.0.1:8011/api/messages/folders"


def test_default_database_paths_are_distinct() -> None:
    db_paths = {
        EmailAppSettings().db_path,
        TodoAppSettings().db_path,
        CalendarAppSettings().db_path,
    }

    assert db_paths == {Path("data/email.db"), Path("data/todo.db"), Path("data/calendar.db")}


def test_all_apps_expose_health_and_openapi(tmp_path: Path) -> None:
    app_factories = [
        (create_email_app, EmailAppSettings(db_path=tmp_path / "email.db"), "email_messages"),
        (create_todo_app, TodoAppSettings(db_path=tmp_path / "todo.db"), "tasks"),
        (
            create_calendar_app,
            CalendarAppSettings(db_path=tmp_path / "calendar.db"),
            "calendar_events",
        ),
    ]

    for create_app, settings, expected_table in app_factories:
        app = create_app(settings, include_ui=False)
        client = TestClient(app)

        health_response = client.get("/health")
        openapi_response = client.get("/openapi.json")

        assert settings.db_path.exists()
        assert inspect(app.state.engine).has_table(expected_table)
        assert health_response.status_code == 200
        assert health_response.json()["status"] == "ok"
        assert openapi_response.status_code == 200
        assert openapi_response.json()["info"]["title"] == settings.app_name
