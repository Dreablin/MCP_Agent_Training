from pathlib import Path

from pydantic_settings import SettingsConfigDict

from shared.config import BaseAppSettings


class TodoAppSettings(BaseAppSettings):
    app_name: str = "Todo App"
    port: int = 8012
    db_path: Path = Path("data/todo.db")

    model_config = SettingsConfigDict(env_file=".env", env_prefix="TODO_APP_", extra="ignore")


def get_settings() -> TodoAppSettings:
    return TodoAppSettings()
