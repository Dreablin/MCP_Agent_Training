from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from shared.datetime import get_timezone


class BaseAppSettings(BaseSettings):
    """Common local settings used by each training application."""

    app_name: str = Field(min_length=1)
    host: str = "127.0.0.1"
    port: int = Field(gt=0, lt=65536)
    db_path: Path
    log_level: str = "INFO"
    default_timezone: str = "local"
    dev_mode: bool = True
    auto_open_browser: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        normalized = value.upper()
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if normalized not in allowed:
            msg = f"Unsupported log level: {value}"
            raise ValueError(msg)
        return normalized

    @field_validator("default_timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        get_timezone(value)
        return value

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.db_path.as_posix()}"

    def ensure_data_dir(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
