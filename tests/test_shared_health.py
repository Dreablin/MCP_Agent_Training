from fastapi import FastAPI
from fastapi.testclient import TestClient

from shared.health import build_health_payload, register_health_route


def test_build_health_payload() -> None:
    payload = build_health_payload("Email App")

    assert payload.status == "ok"
    assert payload.app_name == "Email App"
    assert payload.version == "0.1.0"


def test_register_health_route() -> None:
    app = FastAPI()
    register_health_route(app, "Email App")

    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "app_name": "Email App",
        "version": "0.1.0",
    }
