from pathlib import Path

import pytest
from pydantic import ValidationError

from shared.config import BaseAppSettings


def test_base_app_settings_builds_sqlite_url() -> None:
    settings = BaseAppSettings(app_name="Email App", port=8011, db_path=Path("data/email.db"))

    assert settings.database_url == "sqlite:///data/email.db"
    assert settings.default_timezone == "local"


def test_base_app_settings_rejects_invalid_timezone() -> None:
    with pytest.raises(ValidationError):
        BaseAppSettings(
            app_name="Email App",
            port=8011,
            db_path=Path("data/email.db"),
            default_timezone="No/Such_Zone",
        )
