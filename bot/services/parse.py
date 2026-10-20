"""Parsers of the owner's input (docs/05-bot-ux.md, «Форматы ввода»).

Every parser returns a value or raises InvalidInput; the reason picks the message in views.
"""

import re
from datetime import date, timedelta

MAX_MILEAGE = 2_000_000
MIN_YEAR = 1950

# Reasons of InvalidInput
FORMAT = "format"
FUTURE = "future"
FUTURE_NO_YEAR = "future_no_year"
TOO_LONG = "too_long"
OUT_OF_RANGE = "out_of_range"

_SPACES = re.compile(r"[\s  ]+")
_DATE = re.compile(r"(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?")
_VIN = re.compile(r"[A-HJ-NPR-Z0-9]{17}")


class InvalidInput(ValueError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def parse_mileage(text: str) -> int:
    """«152300», «152 300»; Telegram may turn spaces into NBSP."""
    digits = _SPACES.sub("", text)
    if not digits.isdigit():
        raise InvalidInput(FORMAT)
    value = int(digits)
    if value > MAX_MILEAGE:
        raise InvalidInput(OUT_OF_RANGE)
    return value


def parse_date(text: str, today: date) -> date:
    """«сегодня», «вчера», ДД.ММ, ДД.ММ.ГГГГ; dates in the future are not accepted.

    ДД.ММ means the current year; if that day is still ahead, the owner has to give the
    year explicitly (D-14) rather than the bot guessing the previous one.
    """
    word = text.strip().lower()
    if word == "сегодня":
        return today
    if word == "вчера":
        return today - timedelta(days=1)
    match = _DATE.fullmatch(word)
    if match is None:
        raise InvalidInput(FORMAT)
    day, month, year = match.groups()
    try:
        value = date(int(year) if year else today.year, int(month), int(day))
    except ValueError:
        raise InvalidInput(FORMAT) from None
    if value.year < MIN_YEAR:
        raise InvalidInput(OUT_OF_RANGE)
    if value > today:
        raise InvalidInput(FUTURE if year else FUTURE_NO_YEAR)
    return value


def parse_year(text: str, today: date) -> int:
    value = text.strip()
    if not value.isdigit():
        raise InvalidInput(FORMAT)
    year = int(value)
    if not MIN_YEAR <= year <= today.year + 1:
        raise InvalidInput(OUT_OF_RANGE)
    return year


def parse_vin(text: str) -> str:
    vin = _SPACES.sub("", text).upper()
    if _VIN.fullmatch(vin) is None:
        raise InvalidInput(FORMAT)
    return vin


def parse_text(text: str, max_length: int) -> str:
    value = text.strip()
    if not value:
        raise InvalidInput(FORMAT)
    if len(value) > max_length:
        raise InvalidInput(TOO_LONG)
    return value


def parse_plate(text: str) -> str:
    return parse_text(_SPACES.sub(" ", text), 16).upper()


def parse_currency(text: str) -> str:
    code = text.strip().upper()
    if re.fullmatch(r"[A-Z]{3}", code) is None:
        raise InvalidInput(FORMAT)
    return code
