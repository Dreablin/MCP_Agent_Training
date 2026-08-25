from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel


class HealthPayload(BaseModel):
    status: str
    app_name: str
    version: str


def build_health_payload(app_name: str, version: str = "0.1.0") -> HealthPayload:
    return HealthPayload(status="ok", app_name=app_name, version=version)


def register_health_route(app: FastAPI, app_name: str, version: str = "0.1.0") -> None:
    @app.get("/health", tags=["system"])
    def health() -> dict[str, Any]:
        return build_health_payload(app_name, version).model_dump()
