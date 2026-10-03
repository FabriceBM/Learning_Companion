"""Several short sessions a day, each finite.

A unit learned or missed in one session comes back for a second look in a later
one (same-day steps in the memory model); everything else is due on a day, not
at a minute.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

from fsrs import Card, State

from .clock import DAY, local, start_of_day
from .model import ItemState


def _same_day_step(card: Card) -> bool:
    return card.state in (State.Learning, State.Relearning)


def is_due(card: Card, now: datetime) -> bool:
    if _same_day_step(card):
        return card.due <= now
    return card.due < start_of_day(now) + DAY


@dataclass(frozen=True)
class DayRules:
    sessions_per_day: int
    min_gap_minutes: float


@dataclass(frozen=True)
class DaySoFar:
    sessions_done: int = 0
    last_ended_at: datetime | None = None


@dataclass(frozen=True)
class SessionGate:
    open: bool
    reason: str = ""
    next_at: datetime | None = None


def session_gate(now: datetime, rules: DayRules, today: DaySoFar) -> SessionGate:
    """May a session start now? The family sets the ceiling; a break between sessions is part of learning."""
    if today.sessions_done >= rules.sessions_per_day:
        return SessionGate(
            open=False,
            reason=f"That's all {rules.sessions_per_day} sessions for today.",
            next_at=start_of_day(now) + DAY,
        )
    if today.last_ended_at is not None:
        next_at = today.last_ended_at + timedelta(minutes=rules.min_gap_minutes)
        if next_at > now:
            return SessionGate(open=False, reason="A break between sessions helps memory.", next_at=next_at)
    return SessionGate(open=True)


def next_useful_time(items: Iterable[ItemState], now: datetime) -> datetime | None:
    """When will a session next have something worth doing? Used when today's plan
    is empty, so the app says "come back at 18:30" instead of offering filler."""
    best: datetime | None = None
    for item in items:
        card = item.card
        if card is None:
            continue
        if is_due(card, now):
            return now
        at = local(card.due, now) if _same_day_step(card) else start_of_day(local(card.due, now))
        if best is None or at < best:
            best = at
    return best
