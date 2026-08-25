from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"

DB_FILES = [
    DATA_DIR / "email.db",
    DATA_DIR / "todo.db",
    DATA_DIR / "calendar.db",
]


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def assert_inside_data_dir(path: Path) -> None:
    resolved_data_dir = DATA_DIR.resolve()
    resolved_path = path.resolve()
    if resolved_data_dir not in [resolved_path, *resolved_path.parents]:
        msg = f"Refusing to touch path outside data directory: {path}"
        raise ValueError(msg)
