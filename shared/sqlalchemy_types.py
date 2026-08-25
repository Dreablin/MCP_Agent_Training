from datetime import datetime

from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.types import String, TypeDecorator

from shared.datetime import to_utc


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
