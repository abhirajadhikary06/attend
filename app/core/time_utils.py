"""India Standard Time helpers for attendance dates and display."""

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


def now_ist() -> datetime:
    """Return current IST wall time as naive datetime for existing local-time APIs."""
    return datetime.now(IST).replace(tzinfo=None)


def today_ist() -> date:
    """Return today's date in India Standard Time."""
    return datetime.now(IST).date()


def to_ist(value: datetime) -> datetime:
    """Interpret legacy naive timestamps as UTC and convert them to IST."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(IST)
