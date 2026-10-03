"""Reminders designed to make themselves unnecessary."""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime

from .rng import Rng, sample_beta
from .tuning import DEFAULT_TUNING, ReminderTuning


def weekday(dt: datetime) -> int:
    """0 = Sunday ... 6 = Saturday, the convention used for agreed slots and rest days."""
    return dt.isoweekday() % 7


@dataclass(frozen=True)
class NudgeWindow:
    """A time slot the family agreed on, e.g. "after school", weekdays 17:00-18:30."""

    id: str
    label: str
    days: Sequence[int]
    """0 = Sunday ... 6 = Saturday."""
    start: str
    """"HH:MM"."""
    end: str


@dataclass(frozen=True)
class NudgeSettings:
    windows: Sequence[NudgeWindow]
    max_per_day: int = 1
    """Hard cap, 1 by default. 0 switches reminders off."""
    rest_days: Sequence[int] = ()
    """No reminders at all on these days."""
    intention: str | None = None
    """The learner's own plan ("After my snack"), used as the reminder's first words."""


@dataclass(frozen=True)
class DayRecord:
    date: str
    session_done: bool
    self_started: bool
    """Started without a reminder."""
    nudged: bool


@dataclass(frozen=True)
class WindowStats:
    started: int = 0
    """Reminders in this slot followed by a session within the follow window."""
    ignored: int = 0


@dataclass(frozen=True)
class NudgeState:
    windows: Mapping[str, WindowStats] = field(default_factory=dict)
    ignored_streak: int = 0
    days: Sequence[DayRecord] = ()
    """Most recent last."""


@dataclass(frozen=True)
class NudgeDecision:
    send: bool
    reason: str
    at: datetime | None = None
    window_id: str | None = None
    text: str | None = None


@dataclass(frozen=True)
class NudgeContext:
    session_done_today: bool
    reminders_sent_today: int
    plan_minutes: int
    plan_subjects: Sequence[str]
    rng: Rng | None = None


def decide_nudge(
    now: datetime,
    settings: NudgeSettings,
    state: NudgeState,
    ctx: NudgeContext,
    rules: ReminderTuning = DEFAULT_TUNING.reminders,
) -> NudgeDecision:
    """Decide whether to send today's reminder, and when.

    The goal is for reminders to become unnecessary: they pause when the learner
    starts on their own, back off when ignored, and never escalate. The time slot
    is learned per learner with Thompson sampling over the agreed windows.
    """

    def no(reason: str) -> NudgeDecision:
        return NudgeDecision(send=False, reason=reason)

    if settings.max_per_day <= 0:
        return no("Reminders are switched off.")
    if ctx.session_done_today:
        return no("Today's session is already done.")
    if ctx.plan_minutes == 0:
        return no("Nothing planned today.")
    if weekday(now) in settings.rest_days:
        return no("Rest day.")
    if ctx.reminders_sent_today >= settings.max_per_day:
        return no("Daily reminder limit reached.")

    active = [d for d in list(state.days)[-rules.lookback_days :] if d.session_done]
    self_started = sum(1 for d in active if d.self_started)
    if len(active) >= rules.min_active_days and self_started / len(active) >= rules.self_start_share:
        return no("Habit formed: started on their own on most days, so reminders pause.")
    if state.ignored_streak >= rules.stop_after_ignored:
        return no("Reminders were ignored several times in a row: stopped. Parents see it in the weekly summary.")
    if state.ignored_streak >= rules.backoff_after_ignored and state.days and state.days[-1].nudged:
        return no("Backing off after ignored reminders: none today.")

    minutes_now = now.hour * 60 + now.minute
    open_windows = [w for w in settings.windows if weekday(now) in w.days and _to_minutes(w.end) > minutes_now]
    if not open_windows:
        return no("No agreed time slot left today.")

    rng = ctx.rng or random.random
    best_window = open_windows[0]
    best_score = -1.0
    for w in open_windows:
        stats = state.windows.get(w.id, WindowStats())
        score = sample_beta(1 + stats.started, 1 + stats.ignored, rng)
        if score > best_score:
            best_window, best_score = w, score

    start = max(minutes_now, _to_minutes(best_window.start))
    at = now.replace(hour=start // 60, minute=start % 60, second=0, microsecond=0)
    return NudgeDecision(
        send=True,
        at=at,
        window_id=best_window.id,
        text=reminder_text(settings.intention, ctx.plan_minutes, ctx.plan_subjects),
        reason=f'Slot "{best_window.label}" chosen from this learner\'s past responses.',
    )


def record_nudge_outcome(state: NudgeState, window_id: str, started: bool) -> NudgeState:
    """Update what we learned about a slot once we know whether the reminder was followed."""
    stats = state.windows.get(window_id, WindowStats())
    updated = replace(stats, started=stats.started + 1) if started else replace(stats, ignored=stats.ignored + 1)
    return replace(
        state,
        windows={**state.windows, window_id: updated},
        ignored_streak=0 if started else state.ignored_streak + 1,
    )


def reminder_text(intention: str | None, minutes: int, subjects: Sequence[str]) -> str:
    """Informational and finite: what, how long, nothing else. No mascot guilt, no
    streak threats, no fake urgency."""
    what = f"{minutes} min today ({', '.join(subjects)})"
    return f"{intention}: {what}." if intention else f"{what[0].upper()}{what[1:]}."


def _to_minutes(hhmm: str) -> int:
    h, _, m = hhmm.partition(":")
    return int(h or 0) * 60 + int(m or 0)
