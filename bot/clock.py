from collections.abc import Callable
from datetime import UTC, datetime

_clock: Callable[[], datetime] = lambda: datetime.now(UTC)  # noqa: E731


def utcnow() -> datetime:
    return _clock()


def set_clock(clock: Callable[[], datetime]) -> None:
    """Replaces the time source; used by tests to simulate time passing."""
    global _clock
    _clock = clock


def as_utc(value: datetime) -> datetime:
    """SQLite returns naive datetimes; they were written as UTC."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)
