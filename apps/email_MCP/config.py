from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class EmailMCPSettings(BaseSettings):
    app_name: str = Field(default="Email MCP server", min_length=1)
    host: str = "127.0.0.1"
    port: int = Field(default=8111, gt=0, lt=65536)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    streamable_http_path: str = Field(default="/mcp", min_length=1)
    email_api_scheme: Literal["http", "https"] = "http"
    email_api_host: str = "127.0.0.1"
    email_api_port: int = Field(default=8011, gt=0, lt=65536)
    email_api_messages_path: str = Field(default="/api/messages", min_length=1)
    email_api_timeout_seconds: float = Field(default=5.0, gt=0)

    model_config = SettingsConfigDict(env_file=".env", env_prefix="EMAIL_MCP_", extra="ignore")

    @field_validator("log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, value: object) -> object:
        if isinstance(value, str):
            return value.upper()
        return value

    @field_validator("streamable_http_path", "email_api_messages_path")
    @classmethod
    def paths_must_start_with_slash(cls, value: str) -> str:
        if not value.startswith("/"):
            msg = f"Path must start with '/': {value}"
            raise ValueError(msg)
        return value

    @property
    def email_api_base_url(self) -> str:
        return f"{self.email_api_scheme}://{self.email_api_host}:{self.email_api_port}"

    @property
    def email_api_messages_url(self) -> str:
        return f"{self.email_api_base_url}{self.email_api_messages_path}"

    @property
    def email_api_folders_url(self) -> str:
        return f"{self.email_api_messages_url}/folders"


def get_settings() -> EmailMCPSettings:
    return EmailMCPSettings()
