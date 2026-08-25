from pathlib import Path

from pydantic_settings import SettingsConfigDict

from shared.config import BaseAppSettings


class CalendarAppSettings(BaseAppSettings):
    app_name: str = "Calendar App"
    port: int = 8013
    db_path: Path = Path("data/calendar.db")

    model_config = SettingsConfigDict(env_file=".env", env_prefix="CALENDAR_APP_", extra="ignore")


def get_settings() -> CalendarAppSettings:
    return CalendarAppSettings()
