"""Dates and times.

Every datetime the engine sees is timezone-aware, in the family's local zone
(``zoneinfo.ZoneInfo("Europe/Paris")`` for example): "due today" and "best hour"
are local notions. Memory states (py-fsrs cards) are stored in UTC.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

DAY = timedelta(days=1)


def require_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError(f"{dt!r} has no time zone: pass an aware datetime, e.g. with zoneinfo.ZoneInfo('Europe/Paris')")
    return dt


def to_utc(dt: datetime) -> datetime:
    return require_aware(dt).astimezone(UTC)


def days_between(start: datetime, end: datetime) -> float:
    """Fractional days from ``start`` to ``end``, measured in real elapsed time."""
    return (to_utc(end) - to_utc(start)).total_seconds() / 86_400


def add_days(dt: datetime, days: float) -> datetime:
    return dt + timedelta(days=days)


def start_of_day(dt: datetime) -> datetime:
    """Local midnight of the day ``dt`` falls on, in ``dt``'s own zone."""
    return require_aware(dt).replace(hour=0, minute=0, second=0, microsecond=0)


def local(dt: datetime, like: datetime) -> datetime:
    """``dt`` seen in the zone of ``like`` (cards are stored in UTC, days are local)."""
    return require_aware(dt).astimezone(like.tzinfo)


def round_half_up(x: float) -> int:
    """Rounding as people expect it (2.5 -> 3), not Python's banker's rounding."""
    return math.floor(x + 0.5)


def pct(x: float) -> str:
    return f"{round_half_up(x * 100)}%"
