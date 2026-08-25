from pathlib import Path


def temp_db_path(tmp_path: Path, filename: str) -> Path:
    return tmp_path / filename
