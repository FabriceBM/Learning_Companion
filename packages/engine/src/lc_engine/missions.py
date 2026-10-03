"""A mission is what the learner chooses to work on.

The app suggests and ranks; the learner picks. A mission session goes entirely
to its units.

- by-heart: a text or a figure to learn word for word (use case 1, by_heart.py)
- pushed:   a notion parents pushed to the app, with the prerequisites it needs (use case 2)
- test:     everything a dated test covers
- topic:    anything chosen freely (a subject, a lesson, a notion)
- mixed:    no focus: review whatever is due, interleaved (keeps everything fresh)
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from .clock import days_between, round_half_up
from .day import is_due
from .memory import MemoryModel
from .model import Goal, ItemState
from .planner import Focus
from .tuning import DEFAULT_TUNING, Tuning

MissionKind = Literal["by-heart", "pushed", "test", "topic", "mixed"]


@dataclass(frozen=True)
class Mission:
    id: str
    kind: MissionKind
    title: str
    ku_ids: tuple[str, ...] = ()
    """Units in scope; empty for a mixed review."""
    goal: Goal | None = None
    pushed_by: str | None = None
    """Who pushed it, shown on the card ("pushed by your parents")."""


def mission_for_test(goal: Goal, items: Sequence[ItemState]) -> Mission:
    """Everything a dated test covers. (Not named test_mission so test runners never collect it.)"""
    return Mission(f"test:{goal.id}", "test", goal.title, tuple(i.ku.id for i in items if goal.id in i.ku.goal_ids), goal=goal)


def pushed_mission(
    mission_id: str,
    title: str,
    notion_ids: Sequence[str],
    items: Sequence[ItemState],
    pushed_by: str | None = None,
    goal: Goal | None = None,
) -> Mission:
    """Use case 2: a notion parents pushed, as a learning path from KnowledgeMap.learning_path()."""
    notions = set(notion_ids)
    ku_ids = tuple(i.ku.id for i in items if i.ku.notion_id and i.ku.notion_id in notions)
    return Mission(f"pushed:{mission_id}", "pushed", title, ku_ids, goal=goal, pushed_by=pushed_by)


def by_heart_mission(mission_id: str, title: str, ku_ids: Sequence[str], goal: Goal | None = None) -> Mission:
    """Use case 1: a text or figure to learn by heart (units from by_heart_units / figure_units),
    optionally for a recitation date."""
    return Mission(f"by-heart:{mission_id}", "by-heart", title, tuple(ku_ids), goal=goal)


def topic_mission(mission_id: str, title: str, items: Sequence[ItemState], pick: Callable[[ItemState], bool]) -> Mission:
    return Mission(f"topic:{mission_id}", "topic", title, tuple(i.ku.id for i in items if pick(i)))


MIXED_REVIEW = Mission("mixed", "mixed", "Keep everything fresh")


def to_focus(mission: Mission) -> Focus | None:
    """What the planner needs; None for a mixed review."""
    return None if mission.kind == "mixed" else Focus(mission.id, frozenset(mission.ku_ids))


@dataclass(frozen=True)
class MissionProgress:
    total: int
    started: int
    secure: int
    """Units whose memory is stable enough to leave the mission (tuning.mission)."""
    readiness: float
    """Mean predicted recall over the scope, on the test day for a test mission (unstarted units count 0)."""
    complete: bool


def mission_progress(
    mission: Mission,
    items: Sequence[ItemState],
    memory: MemoryModel,
    now: datetime,
    tuning: Tuning = DEFAULT_TUNING,
) -> MissionProgress:
    scope = set(mission.ku_ids)
    units = [i for i in items if i.ku.id in scope]
    at = mission.goal.date if mission.goal and mission.goal.date > now else now
    secure = sum(1 for i in units if i.card is not None and (i.card.stability or 0) >= tuning.mission.secure_stability_days)
    readiness = sum(memory.retrievability(i.card, at) for i in units) / len(units) if units else 0.0
    return MissionProgress(
        total=len(units),
        started=sum(1 for i in units if i.card is not None),
        secure=secure,
        readiness=readiness,
        complete=bool(units) and secure == len(units),
    )


@dataclass(frozen=True)
class Suggestion:
    mission: Mission
    score: float
    reason: str
    progress: MissionProgress


_KIND_WEIGHT = {"pushed": 0.6, "by-heart": 0.5, "test": 0.5, "topic": 0.3}


def suggest_missions(
    missions: Sequence[Mission],
    items: Sequence[ItemState],
    memory: MemoryModel,
    now: datetime,
    tuning: Tuning = DEFAULT_TUNING,
) -> list[Suggestion]:
    """Rank missions for the learner to choose from: a close test that isn't ready
    comes first, then gaps a parent flagged, then topics; a mixed review rises as
    reviews pile up. The learner can always pick something else."""
    due_count = sum(1 for i in items if i.card is not None and is_due(i.card, now))
    suggestions: list[Suggestion] = []
    for mission in missions:
        progress = mission_progress(mission, items, memory, now, tuning)
        if mission.kind == "mixed":
            suggestions.append(
                Suggestion(mission, 0.7 * due_count / (due_count + 15), f"{due_count} reviews due across subjects", progress)
            )
            continue
        if progress.complete:
            continue
        not_secure = 1 - progress.secure / progress.total if progress.total else 0
        if mission.goal is not None:
            days = max(0.5, days_between(now, mission.goal.date))
            window = tuning.retention.test_window_days
            in_days = math.ceil(days)
            suggestions.append(
                Suggestion(
                    mission,
                    # Inside the test window a test leads; further out it competes on how unready it is.
                    (0.5 if days <= window else 0.2) + (1 - progress.readiness) * min(1, window / days),
                    f"In {in_days} day{'' if in_days == 1 else 's'} · {round_half_up(progress.readiness * 100)}% ready",
                    progress,
                )
            )
            continue
        if mission.kind == "pushed" and mission.pushed_by:
            label = f"Pushed by {mission.pushed_by}"
        elif mission.kind == "by-heart":
            label = "To learn by heart"
        else:
            label = "Your choice"
        suggestions.append(
            Suggestion(
                mission,
                not_secure * _KIND_WEIGHT[mission.kind],
                f"{label} · {progress.secure} of {progress.total} secure",
                progress,
            )
        )
    return sorted(suggestions, key=lambda s: -s.score)
