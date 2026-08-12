"""Application timezone helpers — all user-facing clocks use Asia/Kolkata (IST)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from time import struct_time
from zoneinfo import ZoneInfo

from app.core.config import settings

DEFAULT_APP_TIMEZONE = "Asia/Kolkata"


def app_timezone_name() -> str:
    return (settings.scheduler_timezone or DEFAULT_APP_TIMEZONE).strip() or DEFAULT_APP_TIMEZONE


def app_zone() -> ZoneInfo:
    return ZoneInfo(app_timezone_name())


def now_app() -> datetime:
    """Current time as a timezone-aware datetime in the app timezone (IST)."""
    return datetime.now(app_zone())


def today_app() -> date:
    """Calendar date in the app timezone (used for daily log filenames)."""
    return now_app().date()


def to_app_tz(value: datetime) -> datetime:
    """Normalize any datetime to the app timezone (naive values treated as UTC)."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(app_zone())


def logging_time_converter(seconds: float) -> struct_time:
    """logging.Formatter.converter that emits IST wall-clock times."""
    return datetime.fromtimestamp(seconds, tz=app_zone()).timetuple()
