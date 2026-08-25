from pathlib import Path

from fastapi.testclient import TestClient

from apps.email_app.config import EmailAppSettings
from apps.email_app.main import create_app


def test_email_app_health_endpoint(tmp_path: Path) -> None:
    settings = EmailAppSettings(db_path=tmp_path / "email.db")
    app = create_app(settings, include_ui=False)

    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "app_name": "Email app",
        "version": "0.1.0",
    }


def test_email_app_creates_data_directory(tmp_path: Path) -> None:
    db_path = tmp_path / "nested" / "email.db"
    settings = EmailAppSettings(db_path=db_path)

    create_app(settings, include_ui=False)

    assert db_path.parent.exists()
