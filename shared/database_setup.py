from pathlib import Path

from alembic import command
from alembic.config import Config


def upgrade_database(
    config_path: Path,
    project_root: Path,
    database_url: str | None = None,
) -> None:
    config = Config(str(config_path))
    config.set_main_option("prepend_sys_path", str(project_root))
    if database_url is not None:
        config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")


def initialize_database_if_missing(
    db_path: Path,
    database_url: str,
    alembic_config_path: Path,
    project_root: Path,
) -> None:
    if db_path.exists():
        return
    db_path.parent.mkdir(parents=True, exist_ok=True)
    upgrade_database(alembic_config_path, project_root, database_url)
