from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from shared.sqlalchemy_types import LocalNaiveDateTime, UTCDateTime


def test_utc_datetime_rejects_naive_bind_value() -> None:
    column_type = UTCDateTime()

    with pytest.raises(ValueError, match="must include timezone"):
        column_type.process_bind_param(datetime(2026, 8, 6, 12, 0), dialect=None)  # type: ignore[arg-type]


def test_utc_datetime_round_trip() -> None:
    column_type = UTCDateTime()
    local_value = datetime(2026, 8, 6, 12, 0, tzinfo=ZoneInfo("America/Chicago"))

    stored = column_type.process_bind_param(local_value, dialect=None)  # type: ignore[arg-type]
    restored = column_type.process_result_value(stored, dialect=None)  # type: ignore[arg-type]

    assert stored == "2026-08-06T17:00:00+00:00"
    assert restored == datetime(2026, 8, 6, 17, 0, tzinfo=ZoneInfo("UTC"))


def test_local_naive_datetime_rejects_aware_bind_value() -> None:
    column_type = LocalNaiveDateTime()

    with pytest.raises(ValueError, match="must not include timezone"):
        column_type.process_bind_param(
            datetime(2026, 8, 6, 12, 0, tzinfo=ZoneInfo("America/Chicago")),
            dialect=None,  # type: ignore[arg-type]
        )


def test_local_naive_datetime_round_trip() -> None:
    column_type = LocalNaiveDateTime()
    local_value = datetime(2026, 8, 6, 12, 0)

    stored = column_type.process_bind_param(local_value, dialect=None)  # type: ignore[arg-type]
    restored = column_type.process_result_value(stored, dialect=None)  # type: ignore[arg-type]

    assert stored == "2026-08-06T12:00:00"
    assert restored == datetime(2026, 8, 6, 12, 0)


def test_local_naive_datetime_strips_legacy_timezone_on_read() -> None:
    column_type = LocalNaiveDateTime()

    restored = column_type.process_result_value(
        "2026-08-06T17:00:00+00:00",
        dialect=None,  # type: ignore[arg-type]
    )

    assert restored == datetime(2026, 8, 6, 17, 0)
