from datetime import date, datetime
from zoneinfo import ZoneInfo


def local_today(now_utc: datetime, tz: str) -> date:
    return now_utc.astimezone(ZoneInfo(tz)).date()


def fmt_date(d: date) -> str:
    return d.strftime("%d.%m.%Y")


def utc_offset(tz: str, now_utc: datetime) -> str:
    """«UTC+3», «UTC+5:30»."""
    offset = now_utc.astimezone(ZoneInfo(tz)).utcoffset()
    minutes = int(offset.total_seconds()) // 60
    sign = "+" if minutes >= 0 else "−"
    hours, rest = divmod(abs(minutes), 60)
    return f"UTC{sign}{hours}" + (f":{rest:02d}" if rest else "")
