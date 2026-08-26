from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from shared.datetime import UTC, from_utc, require_aware, require_naive, to_utc


def test_require_aware_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="must include timezone"):
        require_aware(datetime(2026, 8, 6, 12, 0), "start_at")


def test_require_naive_rejects_aware_datetime() -> None:
    chicago = ZoneInfo("America/Chicago")

    with pytest.raises(ValueError, match="must not include timezone"):
        require_naive(datetime(2026, 8, 6, 12, 0, tzinfo=chicago), "start_at")


def test_to_utc_converts_aware_datetime() -> None:
    chicago = ZoneInfo("America/Chicago")
    local_value = datetime(2026, 8, 6, 12, 0, tzinfo=chicago)

    result = to_utc(local_value)

    assert result.tzinfo == UTC
    assert result.hour == 17


def test_from_utc_converts_to_target_timezone() -> None:
    utc_value = datetime(2026, 8, 6, 17, 0, tzinfo=UTC)

    result = from_utc(utc_value, "America/Chicago")

    assert result.hour == 12
    assert result.tzinfo == ZoneInfo("America/Chicago")
