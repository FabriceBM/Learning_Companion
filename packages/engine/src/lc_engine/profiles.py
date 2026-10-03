"""Age bands: time limits, answer modes and who sees what.

The app is for children aged 10 to 13 and their parents, who learn too.
Knowledge is measured on an absolute map (knowledge_map.py), not by school
grade, so bands only set limits. A family can choose anything inside a band's
limits, never outside them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

AgeBand = Literal["child", "young-teen", "adult"]

AnswerMode = Literal["choices", "voice", "short-text", "maths", "free-text"]

ProgressVisibility = Literal[
    "family",  # children: parents see progress, and the child sees exactly what parents see
    "learner-only",  # parents' own learning: nobody else sees it unless they share it
]

Range = tuple[float, float]


@dataclass(frozen=True)
class BandDefaults:
    band: AgeBand
    session_minutes: int
    """One session: short enough to stay sharp."""
    session_range: Range
    sessions_per_day: int
    """Sessions allowed per day; each one is still finite."""
    sessions_per_day_range: Range
    min_gap_minutes: int
    """Minimum break between two sessions: spacing within the day helps memory."""
    max_new_per_day: int
    max_reminders_per_day: int
    answer_modes: tuple[AnswerMode, ...]
    visibility: ProgressVisibility
    parental_consent: bool
    """Parental consent is needed below 15 in France (digital majority)."""


BANDS: dict[AgeBand, BandDefaults] = {
    "child": BandDefaults(
        band="child",
        session_minutes=10,
        session_range=(5, 15),
        sessions_per_day=2,
        sessions_per_day_range=(1, 5),
        min_gap_minutes=90,
        max_new_per_day=10,
        max_reminders_per_day=1,
        answer_modes=("choices", "voice", "short-text"),
        visibility="family",
        parental_consent=True,
    ),
    "young-teen": BandDefaults(
        band="young-teen",
        session_minutes=12,
        session_range=(5, 15),
        sessions_per_day=2,
        sessions_per_day_range=(1, 5),
        min_gap_minutes=90,
        max_new_per_day=14,
        max_reminders_per_day=1,
        # free text means a sentence or two for "explain" questions
        answer_modes=("choices", "voice", "short-text", "maths", "free-text"),
        visibility="family",
        parental_consent=True,
    ),
    "adult": BandDefaults(
        band="adult",
        session_minutes=15,
        session_range=(5, 30),
        sessions_per_day=2,
        sessions_per_day_range=(1, 5),
        min_gap_minutes=60,
        max_new_per_day=20,
        max_reminders_per_day=2,
        answer_modes=("choices", "voice", "short-text", "maths", "free-text"),
        visibility="learner-only",
        parental_consent=False,
    ),
}


def age_band(age: float) -> AgeBand:
    """Children outside 10–13 fall back to the nearest child band; any minor keeps the child limits."""
    if age < 12:
        return "child"
    if age < 18:
        return "young-teen"
    return "adult"


def defaults_for_age(age: float) -> BandDefaults:
    return BANDS[age_band(age)]


@dataclass(frozen=True)
class DailyLimits:
    session_minutes: float
    sessions_per_day: int
    max_reminders_per_day: int
    max_new_per_day: int


def _clamp(value: float, bounds: Range) -> float:
    lo, hi = bounds
    return min(hi, max(lo, value))


def within_limits(age: float, chosen: DailyLimits) -> DailyLimits:
    """Keep what a family or learner chose inside the limits of the learner's age band."""
    d = defaults_for_age(age)
    return DailyLimits(
        session_minutes=_clamp(chosen.session_minutes, d.session_range),
        sessions_per_day=int(_clamp(chosen.sessions_per_day, d.sessions_per_day_range)),
        max_reminders_per_day=int(_clamp(chosen.max_reminders_per_day, (0, d.max_reminders_per_day))),
        max_new_per_day=int(_clamp(chosen.max_new_per_day, (0, d.max_new_per_day))),
    )
