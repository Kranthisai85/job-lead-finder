"""App timezone (IST) helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.core.timezone import app_zone, now_app, to_app_tz, today_app


def test_now_app_is_asia_kolkata() -> None:
    stamp = now_app()
    assert stamp.tzinfo is not None
    assert stamp.utcoffset() == ZoneInfo("Asia/Kolkata").utcoffset(stamp)


def test_to_app_tz_converts_utc() -> None:
    utc = datetime(2026, 8, 12, 3, 30, tzinfo=timezone.utc)
    ist = to_app_tz(utc)
    assert ist.hour == 9
    assert ist.minute == 0
    assert str(ist.tzinfo) == "Asia/Kolkata"


def test_today_app_matches_ist_calendar() -> None:
    assert today_app() == datetime.now(app_zone()).date()
