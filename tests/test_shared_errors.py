from fastapi import FastAPI
from fastapi.testclient import TestClient

from shared.errors import ErrorCode, NotFoundError, error_payload, register_error_handlers


def test_error_payload_uses_standard_shape() -> None:
    payload = error_payload(ErrorCode.VALIDATION_ERROR, "Invalid value", {"field": "title"})

    assert payload == {
        "error": {
            "code": "VALIDATION_ERROR",
            "message": "Invalid value",
            "details": {"field": "title"},
        }
    }


def test_registered_app_error_handler_returns_standard_shape() -> None:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/missing")
    def missing() -> None:
        raise NotFoundError("Record not found", details={"id": "demo"})

    response = TestClient(app).get("/missing")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
    assert response.json()["error"]["details"] == {"id": "demo"}
