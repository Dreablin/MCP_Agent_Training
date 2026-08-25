from pathlib import Path

from pydantic_settings import SettingsConfigDict

from shared.config import BaseAppSettings


class EmailAppSettings(BaseAppSettings):
    app_name: str = "Email app"
    port: int = 8011
    db_path: Path = Path("data/email.db")

    model_config = SettingsConfigDict(env_file=".env", env_prefix="EMAIL_APP_", extra="ignore")


def get_settings() -> EmailAppSettings:
    return EmailAppSettings()
