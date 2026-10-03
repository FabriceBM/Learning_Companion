import re
from dataclasses import replace

from engine_helpers import at
from lc_engine import (
    DayRecord,
    NudgeContext,
    NudgeSettings,
    NudgeState,
    NudgeWindow,
    decide_nudge,
    record_nudge_outcome,
    seeded_rng,
)

SETTINGS = NudgeSettings(
    windows=[
        NudgeWindow("after-school", "After school", [1, 2, 3, 4, 5], "17:00", "18:30"),
        NudgeWindow("evening", "Before dinner", [1, 2, 3, 4, 5], "18:30", "19:30"),
        NudgeWindow("saturday", "Saturday morning", [6], "10:00", "12:00"),
    ],
    max_per_day=1,
    rest_days=[0],
    intention="After my snack",
)

FRIDAY = at(2026, 10, 2, 16)
SUNDAY = at(2026, 10, 4, 16)
FRESH = NudgeState()


def ctx(**overrides) -> NudgeContext:
    fields = {
        "session_done_today": False,
        "reminders_sent_today": 0,
        "plan_minutes": 9,
        "plan_subjects": ["Spanish", "Maths"],
        "rng": seeded_rng(1),
    }
    return NudgeContext(**{**fields, **overrides})


def days(n: int, **fields) -> list[DayRecord]:
    def record(i: int) -> DayRecord:
        values = {"date": f"d{i}", "session_done": True, "self_started": False, "nudged": True}
        values.update({k: (v(i) if callable(v) else v) for k, v in fields.items()})
        return DayRecord(**values)

    return [record(i) for i in range(n)]


def test_sends_one_informational_reminder_inside_an_agreed_slot():
    d = decide_nudge(FRIDAY, SETTINGS, FRESH, ctx())
    assert d.send
    assert d.window_id in ("after-school", "evening")
    assert d.at.hour >= 17
    assert d.text == "After my snack: 9 min today (Spanish, Maths)."


def test_never_uses_guilt_streaks_or_urgency():
    d = decide_nudge(FRIDAY, replace(SETTINGS, intention=None), FRESH, ctx())
    assert d.send
    assert not re.search(r"streak|lose|lost|sad|miss|hurry|last chance|don't break|!", d.text, re.IGNORECASE)


def test_stays_silent_when_the_session_is_done_on_rest_days_or_at_the_daily_limit():
    assert not decide_nudge(FRIDAY, SETTINGS, FRESH, ctx(session_done_today=True)).send
    assert not decide_nudge(SUNDAY, SETTINGS, FRESH, ctx()).send
    assert not decide_nudge(FRIDAY, SETTINGS, FRESH, ctx(reminders_sent_today=1)).send


def test_pauses_once_the_learner_starts_on_their_own():
    state = replace(FRESH, days=days(10, self_started=lambda i: i != 3, nudged=False))
    d = decide_nudge(FRIDAY, SETTINGS, state, ctx())
    assert not d.send
    assert "Habit formed" in d.reason


def test_backs_off_then_stops_when_reminders_are_ignored():
    backoff = replace(FRESH, ignored_streak=3, days=days(3, session_done=False))
    assert not decide_nudge(FRIDAY, SETTINGS, backoff, ctx()).send
    stopped = replace(FRESH, ignored_streak=6)
    assert not decide_nudge(FRIDAY, SETTINGS, stopped, ctx()).send


def test_learns_which_slot_works_for_this_learner():
    state = FRESH
    for _ in range(12):
        state = record_nudge_outcome(state, "evening", True)
        state = record_nudge_outcome(state, "after-school", False)
    state = replace(state, ignored_streak=0)
    rng = seeded_rng(7)
    picks = [decide_nudge(FRIDAY, SETTINGS, state, ctx(rng=rng)) for _ in range(50)]
    evening = sum(1 for d in picks if d.send and d.window_id == "evening")
    assert evening >= 45, f"evening picked {evening}/50"
