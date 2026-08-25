from pathlib import Path

from fastapi.testclient import TestClient

from apps.todo_app.config import TodoAppSettings
from apps.todo_app.main import create_app


def test_todo_app_health_endpoint(tmp_path: Path) -> None:
    settings = TodoAppSettings(db_path=tmp_path / "todo.db")
    app = create_app(settings, include_ui=False)

    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "app_name": "Todo App",
        "version": "0.1.0",
    }
