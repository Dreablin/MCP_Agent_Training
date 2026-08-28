from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class TodoMCPSettings(BaseSettings):
    app_name: str = Field(default="Todo MCP server", min_length=1)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    todo_api_scheme: Literal["http", "https"] = "http"
    todo_api_host: str = "127.0.0.1"
    todo_api_port: int = Field(default=8012, gt=0, lt=65536)
    todo_api_tasks_path: str = Field(default="/api/tasks", min_length=1)
    todo_api_timeout_seconds: float = Field(default=5.0, gt=0)

    model_config = SettingsConfigDict(env_file=".env", env_prefix="TODO_MCP_", extra="ignore")

    @field_validator("log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, value: object) -> object:
        if isinstance(value, str):
            return value.upper()
        return value

    @field_validator("todo_api_tasks_path")
    @classmethod
    def tasks_path_must_start_with_slash(cls, value: str) -> str:
        if not value.startswith("/"):
            msg = f"Path must start with '/': {value}"
            raise ValueError(msg)
        return value

    @property
    def todo_api_base_url(self) -> str:
        return f"{self.todo_api_scheme}://{self.todo_api_host}:{self.todo_api_port}"

    @property
    def todo_api_tasks_url(self) -> str:
        return f"{self.todo_api_base_url}{self.todo_api_tasks_path}"


def get_settings() -> TodoMCPSettings:
    return TodoMCPSettings()
