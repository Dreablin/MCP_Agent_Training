from pathlib import Path

from scripts.paths import DATA_DIR, DB_FILES, assert_inside_data_dir, ensure_data_dir


def reset_data() -> list[Path]:
    ensure_data_dir()
    removed: list[Path] = []
    targets = list(DB_FILES)
    for db_file in DB_FILES:
        targets.extend(DATA_DIR.glob(f"{db_file.name}-*"))

    for target in targets:
        assert_inside_data_dir(target)
        if target.exists() and target.is_file():
            target.unlink()
            removed.append(target)
    return removed


def main() -> None:
    removed = reset_data()
    if not removed:
        print("No local SQLite data files found.")
        return
    print("Removed local SQLite data files:")
    for path in removed:
        print(f"- {path}")


if __name__ == "__main__":
    main()
