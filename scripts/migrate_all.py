from pathlib import Path

from scripts.paths import PROJECT_ROOT, ensure_data_dir
from shared.database_setup import upgrade_database

ALEMBIC_CONFIGS = [
    PROJECT_ROOT / "apps" / "email_app" / "alembic.ini",
    PROJECT_ROOT / "apps" / "todo_app" / "alembic.ini",
    PROJECT_ROOT / "apps" / "calendar_app" / "alembic.ini",
]


def upgrade(config_path: Path) -> None:
    upgrade_database(config_path, PROJECT_ROOT)


def migrate_all(*, verbose: bool = True) -> None:
    ensure_data_dir()
    for config_path in ALEMBIC_CONFIGS:
        if verbose:
            print(f"Initializing database schema: {config_path}")
        upgrade(config_path)


def main() -> None:
    migrate_all()
    print("All database schemas initialized.")


if __name__ == "__main__":
    main()
