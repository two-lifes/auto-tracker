"""Business rules of mileage (docs/04-domain-model.md, rules 1 and 3) and input formats (05)."""

from datetime import UTC, date, datetime

import pytest

from bot.services import parse
from bot.services.dates import utc_offset
from bot.services.mileage import (
    Gain,
    Reading,
    Violation,
    check_reading,
    current_mileage,
    gain,
    monthly_average,
)
from bot.services.parse import InvalidInput

TODAY = date(2026, 10, 20)
INITIAL = 140_000
READINGS = [
    Reading(1, date(2026, 9, 1), 150_000),
    Reading(2, date(2026, 10, 1), 151_000),
    Reading(3, date(2026, 10, 12), 152_300),
]


def reason(fn, *args) -> str:
    with pytest.raises(InvalidInput) as exc:
        fn(*args)
    return exc.value.reason


# --- input formats ---

@pytest.mark.parametrize(
    ("text", "value"),
    [("152300", 152_300), ("152 300", 152_300), ("152 300", 152_300), (" 0 ", 0)],
)
def test_parse_mileage(text, value):
    assert parse.parse_mileage(text) == value


@pytest.mark.parametrize(
    ("text", "why"),
    [("", parse.FORMAT), ("152.3", parse.FORMAT), ("-5", parse.FORMAT), ("абв", parse.FORMAT),
     ("2000001", parse.OUT_OF_RANGE)],
)
def test_parse_mileage_rejects(text, why):
    assert reason(parse.parse_mileage, text) == why


@pytest.mark.parametrize(
    ("text", "value"),
    [("сегодня", TODAY), ("Вчера", date(2026, 10, 19)), ("12.10", date(2026, 10, 12)),
     ("1.2", date(2026, 2, 1)), ("20.10", TODAY), ("31.12.2025", date(2025, 12, 31)),
     ("29.02.2024", date(2024, 2, 29))],
)
def test_parse_date(text, value):
    assert parse.parse_date(text, TODAY) == value


@pytest.mark.parametrize(
    ("text", "why"),
    [("21.10", parse.FUTURE_NO_YEAR), ("25.12", parse.FUTURE_NO_YEAR),
     ("01.01.2027", parse.FUTURE), ("31.02", parse.FORMAT), ("29.02.2025", parse.FORMAT),
     ("12/10", parse.FORMAT), ("завтра", parse.FORMAT), ("01.01.1900", parse.OUT_OF_RANGE)],
)
def test_parse_date_rejects(text, why):
    assert reason(parse.parse_date, text, TODAY) == why


def test_parse_year():
    assert parse.parse_year("2019", TODAY) == 2019
    assert parse.parse_year("2027", TODAY) == 2027  # next model year is on sale already
    assert reason(parse.parse_year, "2028", TODAY) == parse.OUT_OF_RANGE
    assert reason(parse.parse_year, "19", TODAY) == parse.OUT_OF_RANGE
    assert reason(parse.parse_year, "две тыщи", TODAY) == parse.FORMAT


def test_parse_vin():
    assert parse.parse_vin("tmb jg7ne 5j0123456") == "TMBJG7NE5J0123456"
    assert reason(parse.parse_vin, "TMBJG7NE5J012345") == parse.FORMAT  # 16 characters
    assert reason(parse.parse_vin, "TMBJG7NE5J012345O") == parse.FORMAT  # O is not allowed


def test_parse_texts():
    assert parse.parse_text("  Октавия ", 64) == "Октавия"
    assert reason(parse.parse_text, "   ", 64) == parse.FORMAT
    assert reason(parse.parse_text, "x" * 65, 64) == parse.TOO_LONG
    assert parse.parse_plate("а 123  вс 77") == "А 123 ВС 77"
    assert parse.parse_currency(" usd ") == "USD"
    assert reason(parse.parse_currency, "рубль") == parse.FORMAT


def test_utc_offset():
    now = datetime(2026, 10, 20, tzinfo=UTC)
    assert utc_offset("Europe/Moscow", now) == "UTC+3"
    assert utc_offset("Asia/Kolkata", now) == "UTC+5:30"
    assert utc_offset("America/New_York", now) == "UTC−4"


# --- rule 3: current mileage ---

def test_current_mileage_is_latest_by_date():
    assert current_mileage(READINGS, INITIAL) == 152_300
    # Entered later but dated earlier: the date decides, not the order of entry
    assert current_mileage([*READINGS, Reading(4, date(2026, 8, 1), 149_000)], INITIAL) == 152_300


def test_current_mileage_equal_dates_take_larger():
    same_day = [Reading(1, TODAY, 152_500), Reading(2, TODAY, 152_400)]
    assert current_mileage(same_day, INITIAL) == 152_500


def test_current_mileage_without_readings_is_initial():
    assert current_mileage([], INITIAL) == INITIAL


# --- rule 1: readings never decrease by date ---

def test_new_reading_today():
    assert check_reading(READINGS, INITIAL, TODAY, 153_000) is None
    assert check_reading(READINGS, INITIAL, TODAY, 152_300) is None  # standing still is fine


def test_smaller_than_current_rejected():
    assert check_reading(READINGS, INITIAL, TODAY, 152_000) == Violation(
        True, 152_300, date(2026, 10, 12), is_current=True
    )


def test_same_date_smaller_rejected():
    assert check_reading(READINGS, INITIAL, date(2026, 10, 12), 152_299).below


def test_backdated_reading_between_neighbours():
    assert check_reading(READINGS, INITIAL, date(2026, 10, 5), 151_500) is None
    assert check_reading(READINGS, INITIAL, date(2026, 10, 5), 150_900) == Violation(
        True, 151_000, date(2026, 10, 1)
    )
    assert check_reading(READINGS, INITIAL, date(2026, 10, 5), 152_400) == Violation(
        False, 152_300, date(2026, 10, 12)
    )


def test_backdated_before_all_readings():
    assert check_reading(READINGS, INITIAL, date(2026, 8, 1), 145_000) is None
    assert check_reading(READINGS, INITIAL, date(2026, 8, 1), 150_001) == Violation(
        False, 150_000, date(2026, 9, 1)
    )


def test_below_initial_rejected():
    assert check_reading([], INITIAL, TODAY, 139_999) == Violation(True, INITIAL, None)
    assert check_reading([], INITIAL, TODAY, INITIAL) is None


def test_edit_ignores_the_reading_itself():
    # Fixing a typo in the latest reading: 152 300 was meant to be 152 030
    assert check_reading(READINGS, INITIAL, date(2026, 10, 12), 152_030, exclude_id=3) is None
    # ...but still not below the previous one
    assert check_reading(READINGS, INITIAL, date(2026, 10, 12), 150_500, exclude_id=3).below


# --- gain and average ---

def test_gain_since_previous_reading():
    new = Reading(4, TODAY, 153_500)
    assert gain([*READINGS, new], new, INITIAL) == Gain(1_200, date(2026, 10, 12))


def test_gain_backdated_counts_from_earlier_neighbour():
    new = Reading(4, date(2026, 10, 5), 151_500)
    assert gain([*READINGS, new], new, INITIAL) == Gain(500, date(2026, 10, 1))


def test_first_reading_gain_from_initial():
    new = Reading(1, TODAY, 141_000)
    assert gain([new], new, INITIAL) == Gain(1_000, None)


def test_monthly_average():
    # 2 300 km over 41 days
    assert monthly_average(READINGS) == round(2_300 / 41 * 30.4375)


def test_monthly_average_needs_enough_data():
    assert monthly_average([]) is None
    assert monthly_average(READINGS[:1]) is None
    assert monthly_average(READINGS[1:]) is None  # 11 days apart
