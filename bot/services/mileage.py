"""Odometer rules from docs/04-domain-model.md (business rules 1 and 3, D-13). No I/O."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date

DAYS_IN_MONTH = 30.4375
MIN_AVERAGE_SPAN_DAYS = 30


@dataclass(frozen=True)
class Reading:
    id: int | None
    date: date
    value: int


@dataclass(frozen=True)
class Violation:
    """Why a reading is rejected: it must be at least / at most ``bound``.

    ``bound_date`` is None when the bound is the profile's initial mileage.
    ``is_current`` marks the latest reading, i.e. the current mileage.
    """

    below: bool
    bound: int
    bound_date: date | None
    is_current: bool = False


def _key(r: Reading) -> tuple[date, int]:
    # Rule 3: the latest date wins; on equal dates the larger value
    return r.date, r.value


def latest(readings: Iterable[Reading]) -> Reading | None:
    return max(readings, key=_key, default=None)


def current_mileage(readings: Iterable[Reading], initial: int) -> int:
    last = latest(readings)
    return last.value if last else initial


def check_reading(
    readings: Sequence[Reading],
    initial: int,
    day: date,
    value: int,
    exclude_id: int | None = None,
) -> Violation | None:
    """Rule 1: readings never decrease by date, and none is below the initial mileage.

    Valid when max(initial, readings up to ``day``) <= value <= min(readings after ``day``).
    ``exclude_id`` leaves out the reading being edited.
    """
    others = [r for r in readings if exclude_id is None or r.id != exclude_id]
    floor = max(
        (r for r in others if r.date <= day), key=lambda r: (r.value, r.date), default=None
    )
    if floor is not None and value < floor.value:
        return Violation(True, floor.value, floor.date, is_current=floor == latest(others))
    if value < initial:
        return Violation(True, initial, None)
    ceiling = min(
        (r for r in others if r.date > day), key=lambda r: (r.value, r.date), default=None
    )
    if ceiling is not None and value > ceiling.value:
        return Violation(False, ceiling.value, ceiling.date)
    return None


@dataclass(frozen=True)
class Gain:
    km: int
    # None: counted from the initial mileage
    since: date | None


def gain(readings: Sequence[Reading], new: Reading, initial: int) -> Gain:
    """How much the odometer grew since the previous reading by date."""
    # ``new`` already passed check_reading, so nothing up to its date is larger
    previous = latest(r for r in readings if r.id != new.id and r.date <= new.date)
    if previous is None:
        return Gain(new.value - initial, None)
    return Gain(new.value - previous.value, previous.date)


def monthly_average(readings: Sequence[Reading]) -> int | None:
    """Average km per month between the first and the last reading.

    Needs readings at least MIN_AVERAGE_SPAN_DAYS apart; fewer data say nothing useful.
    """
    if len(readings) < 2:
        return None
    first = min(readings, key=_key)
    last = latest(readings)
    days = (last.date - first.date).days
    if days < MIN_AVERAGE_SPAN_DAYS:
        return None
    return round((last.value - first.value) / days * DAYS_IN_MONTH)
