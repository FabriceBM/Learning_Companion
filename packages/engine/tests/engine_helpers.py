"""Shared builders for the engine tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from lc_engine import AdaptiveScheduler, Goal, ItemState, KnowledgeUnit, Latency, LearnerProfile, MemoryModel, Rating, add_days

PARIS = ZoneInfo("Europe/Paris")
NOW = datetime(2026, 10, 2, 17, 0, tzinfo=PARIS)


def at(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=PARIS)


def unit(uid: str, **overrides: Any) -> KnowledgeUnit:
    fields: dict[str, Any] = {"id": uid, "subject": "Maths", "kind": "fact", "title": uid}
    return KnowledgeUnit(**{**fields, **overrides})


LEA = LearnerProfile(
    id="lea",
    name="Léa",
    session_minutes=10,
    sessions_per_day=1,
    min_gap_minutes=90,
    max_new_per_day=6,
    seconds_per_probe={"recognize": 8, "recall": 12, "apply": 20, "explain": 35},
    latency_ms=Latency(3000, 9000),
    recent_accuracy=0.88,
)


def learner(**overrides: Any) -> LearnerProfile:
    return replace(LEA, **overrides)


def studied(
    ku: KnowledgeUnit,
    grades: list[Rating] | None = None,
    gap_days: float = 3,
    end_days_ago: float = 0,
    goals: list[Goal] | None = None,
) -> ItemState:
    """Study a unit with the given grades, one per ``gap_days``, ending ``end_days_ago`` days before NOW."""
    grades = grades or [Rating.Good]
    scheduler = AdaptiveScheduler(MemoryModel(), goals or [])
    item = ItemState(ku)
    start = add_days(NOW, -end_days_ago - gap_days * (len(grades) - 1))
    for i, grade in enumerate(grades):
        item = ItemState(ku, scheduler.record(item, add_days(start, i * gap_days), grade))
    return item
