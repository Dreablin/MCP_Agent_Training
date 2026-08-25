from datetime import datetime, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

UTC = ZoneInfo("UTC")


def get_timezone(timezone_name: str) -> tzinfo:
    if timezone_name == "local":
        return datetime.now().astimezone().tzinfo or UTC
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        msg = f"Unknown timezone: {timezone_name}"
        raise ValueError(msg) from exc


def now_utc() -> datetime:
    return datetime.now(UTC)


def require_aware(value: datetime, field_name: str = "datetime") -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        msg = f"{field_name} must include timezone information"
        raise ValueError(msg)
    return value


def to_utc(value: datetime, field_name: str = "datetime") -> datetime:
    return require_aware(value, field_name).astimezone(UTC)


def from_utc(value: datetime, timezone_name: str) -> datetime:
    return require_aware(value, "datetime").astimezone(get_timezone(timezone_name))
