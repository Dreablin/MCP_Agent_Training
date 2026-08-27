from datetime import datetime

from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.types import String, TypeDecorator

from shared.datetime import require_naive, to_utc


class UTCDateTime(TypeDecorator[datetime]):
    """Store aware datetimes as UTC ISO strings and return aware UTC datetimes."""

    impl = String(40)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> str | None:
        if value is None:
            return None
        return to_utc(value).isoformat()

    def process_result_value(self, value: str | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return to_utc(datetime.fromisoformat(value))


class LocalNaiveDateTime(TypeDecorator[datetime]):
    """Store local naive datetimes as ISO strings and return naive datetimes."""

    impl = String(40)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> str | None:
        if value is None:
            return None
        return require_naive(value).isoformat()

    def process_result_value(self, value: str | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        parsed = datetime.fromisoformat(value)
        return parsed.replace(tzinfo=None)
