"""Build one session: a finite list that fits the session length."""

from __future__ import annotations

import math
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from functools import cmp_to_key
from typing import Literal

from .clock import days_between, pct, round_half_up, to_utc
from .day import is_due
from .grading import probe_level_for
from .memory import MemoryModel
from .model import Goal, ItemState, KnowledgeUnit, LearnerProfile, ProbeLevel
from .retention import next_goal, target_retention
from .tuning import DEFAULT_TUNING, Tuning

PlanKind = Literal["review", "new", "repair", "practice"]
"""review: due today · new: first meeting · repair: a weak prerequisite of the
mission · practice: extra practice on a mission unit that is not secure yet."""


@dataclass(frozen=True)
class PlannedItem:
    ku_id: str
    subject: str
    title: str
    kind: PlanKind
    level: ProbeLevel
    recall: float
    """Predicted recall right now (0 for a new unit)."""
    seconds: float
    why: str
    """One line shown under "Why this card?"."""


@dataclass(frozen=True)
class SessionPlan:
    items: list[PlannedItem]
    minutes: int
    deferred: int
    """Due reviews in scope that did not fit. Re-prioritised next session; never shown as a debt."""
    waiting: int
    """Due reviews outside the mission, waiting for a later session."""
    subjects: list[str]
    mission_id: str | None = None


@dataclass(frozen=True)
class Focus:
    """A mission narrows the session to its units (missions.py)."""

    mission_id: str
    ku_ids: frozenset[str] = field(default_factory=frozenset)


@dataclass
class _Due:
    item: ItemState
    recall: float
    goal: Goal | None
    priority: float


def plan_session(
    learner: LearnerProfile,
    items: Sequence[ItemState],
    goals: Sequence[Goal],
    now: datetime,
    memory: MemoryModel,
    *,
    tuning: Tuning | None = None,
    new_today: int = 0,
    focus: Focus | None = None,
    interleave_mixed: bool = True,
) -> SessionPlan:
    """Without a mission (mixed review):
      1. due reviews, most at risk first; 2. new units if every due review fits;
      3. subjects interleaved, opening and closing on units the learner probably knows.

    With a mission (focus), the whole session goes to it:
      0. weak prerequisites of the mission repaired first;
      1. due mission reviews; 2. new mission units in prerequisite order;
      3. extra practice on mission units that are not secure yet;
      ordered foundations first, one notion at a time, ending on a likely success.
      Other due reviews wait (they are counted, not lost).

    ``new_today``: new units already introduced in today's earlier sessions.
    ``interleave_mixed``: from the concentration profile; False groups a mixed
    review by subject (switching costs this learner too much).
    """
    t = tuning or DEFAULT_TUNING
    budget = learner.session_minutes * 60
    mission_budget = budget * t.mission.focus_share if focus else budget
    by_id = {i.ku.id: i for i in items}

    def in_scope(i: ItemState) -> bool:
        return focus is None or i.ku.id in focus.ku_ids

    depth = _depth_of(by_id)
    chosen: list[PlannedItem] = []
    taken: set[str] = set()
    used = 0.0

    def take(item: ItemState, kind: PlanKind, why: str, limit: float) -> bool:
        nonlocal used
        level: ProbeLevel = "recognize" if kind == "new" else probe_level_for(item.ku.kind, item.card, t.ladder)
        seconds = (
            learner.seconds_per_probe["recognize"] * t.planner.new_unit_cost
            if kind == "new"
            else learner.seconds_per_probe[level]
        )
        if used + seconds > limit:
            return False
        recall = memory.retrievability(item.card, now)
        chosen.append(PlannedItem(item.ku.id, item.ku.subject, item.ku.title, kind, level, recall, seconds, why))
        taken.add(item.ku.id)
        used += seconds
        return True

    # 0. Mission: repair weak foundations first.
    if focus is not None:
        scope_items = [i for i in items if in_scope(i)]
        prerequisites = _closure([p for i in scope_items for p in i.ku.prerequisites], by_id)
        weak = sorted(
            (
                by_id[pid]
                for pid in prerequisites
                if by_id[pid].card is not None and memory.retrievability(by_id[pid].card, now) < t.mission.repair_below_recall
            ),
            key=lambda p: depth(p.ku.id),
        )
        for p in weak:
            dependent = next((i for i in scope_items if p.ku.id in _closure(i.ku.prerequisites, by_id)), None)
            title = dependent.ku.title if dependent else "your mission"
            take(
                p, "repair", f'Needed for "{title}": recall is down to {pct(memory.retrievability(p.card, now))}', mission_budget
            )

    # 1. Due reviews, most at risk first.
    due = [
        _urgency(i, goals, now, memory, t) for i in items if i.card is not None and is_due(i.card, now) and i.ku.id not in taken
    ]
    deferred = 0
    for d in sorted((d for d in due if in_scope(d.item)), key=lambda d: -d.priority):
        if not take(d.item, "review", _why_review(d.item, d.recall, d.goal, now), mission_budget):
            deferred += 1

    # 2. New units, only if every due review fits.
    if deferred == 0:
        if learner.recent_accuracy < t.planner.pause_new_below:
            throttle = 0.0
        elif learner.recent_accuracy < t.planner.halve_new_below:
            throttle = 0.5
        else:
            throttle = 1.0
        new_cap = max(0, math.floor(learner.max_new_per_day * throttle) - new_today)
        introduced: dict[str, None] = {}

        def known(ku: KnowledgeUnit) -> bool:
            for pid in ku.prerequisites:
                p = by_id.get(pid)
                # A prerequisite outside the learner's units (learned long ago) is assumed known.
                if p is None or memory.retrievability(p.card, now) >= t.planner.prerequisite_recall:
                    continue
                # In a mission, a notion is learned in one go: a unit may follow a prerequisite
                # of the same notion introduced earlier in this session.
                if focus is not None and pid in introduced and p.ku.notion_id and p.ku.notion_id == ku.notion_id:
                    continue
                return False
            return True

        fresh = sorted(
            (
                (order, item, next_goal(item.ku, goals, now))
                for order, item in enumerate(items)
                if item.card is None and in_scope(item)
            ),
            key=lambda e: (
                to_utc(e[2].date).timestamp() if e[2] else math.inf,
                depth(e[1].ku.id) if focus else 0,
                -e[1].ku.importance,
                e[0],
            ),
        )
        # Repeated passes let a unit follow its same-notion prerequisite within the session.
        added = True
        while added and len(introduced) < new_cap:
            added = False
            for _, item, goal in fresh:
                if len(introduced) >= new_cap:
                    break
                if item.ku.id in introduced or not known(item.ku):
                    continue
                why = (
                    "New in your mission" if focus else f"New, counts for {goal.title}" if goal else "New from your latest lesson"
                )
                if not take(item, "new", why, mission_budget):
                    break
                introduced[item.ku.id] = None
                added = True

    # 3. Mission: extra practice on units that are not secure yet, until the session is full.
    if focus is not None:
        practice = sorted(
            (
                i
                for i in items
                if i.card is not None
                and in_scope(i)
                and i.ku.id not in taken
                and (i.card.stability or 0) < t.mission.secure_stability_days
            ),
            key=lambda i: memory.retrievability(i.card, now),
        )
        for p in practice:
            take(p, "practice", "Not secure yet: extra practice for your mission", mission_budget)

        # Full focus by default: a short mission makes a short session. Below 100%,
        # the remaining share keeps the most at-risk other reviews alive.
        if t.mission.focus_share < 1:
            for d in sorted((d for d in due if not in_scope(d.item) and d.item.ku.id not in taken), key=lambda d: -d.priority):
                take(d.item, "review", _why_review(d.item, d.recall, d.goal, now), budget)

    waiting = sum(1 for d in due if not in_scope(d.item) and d.item.ku.id not in taken) if focus else 0
    arranged = _arrange_focused(chosen, depth) if focus else _arrange_mixed(chosen, interleave_mixed)
    return SessionPlan(
        items=arranged,
        minutes=math.ceil(used / 60),
        deferred=deferred,
        waiting=waiting,
        subjects=list(dict.fromkeys(c.subject for c in chosen)),
        mission_id=focus.mission_id if focus else None,
    )


def _urgency(item: ItemState, goals: Sequence[Goal], now: datetime, memory: MemoryModel, t: Tuning) -> _Due:
    recall = memory.retrievability(item.card, now)
    target = target_retention(item.ku, goals, now, t.retention)
    goal = next_goal(item.ku, goals, now)
    days_to_goal = days_between(now, goal.date) if goal else math.inf
    window = t.retention.test_window_days
    goal_boost = 1 + t.planner.test_boost * max(0.0, window - days_to_goal) / window
    weight = (0, t.planner.weight_nice_to_know, t.planner.weight_expected, t.planner.weight_foundational)[item.ku.importance]
    return _Due(item, recall, goal, weight * goal_boost * max(0.01, target - recall + t.planner.risk_floor))


def _closure(ids: Collection[str], by_id: Mapping[str, ItemState]) -> dict[str, None]:
    """All transitive prerequisites of the given unit ids (only those the learner has), in discovery order."""
    seen: dict[str, None] = {}
    stack = list(ids)
    while stack:
        uid = stack.pop()
        item = by_id.get(uid)
        if item is None or uid in seen:
            continue
        seen[uid] = None
        stack.extend(item.ku.prerequisites)
    return seen


def _depth_of(by_id: Mapping[str, ItemState]) -> Callable[[str], int]:
    """Length of the longest prerequisite chain below a unit: 0 for foundations."""
    memo: dict[str, int] = {}

    def depth(uid: str, guard: set[str]) -> int:
        if uid in memo:
            return memo[uid]
        item = by_id.get(uid)
        if item is None or uid in guard:
            return 0
        guard.add(uid)
        d = max([-1, *(depth(p, guard) for p in item.ku.prerequisites)]) + 1
        memo[uid] = d
        return d

    return lambda uid: depth(uid, set())


def _why_review(item: ItemState, recall: float, goal: Goal | None, now: datetime) -> str:
    last = item.card.last_review if item.card else None
    hours = days_between(last, now) * 24 if last else 0.0
    days = round_half_up(hours / 24)
    if hours < 12:
        seen = "Seen earlier today: a second look after a break"
    elif days == 1:
        seen = "Seen yesterday"
    else:
        seen = f"Seen {days} days ago"
    parts = [seen, f"recall now about {pct(recall)}"]
    if goal is not None:
        in_days = math.ceil(days_between(now, goal.date))
        parts.append(f"{goal.title} in {in_days} day{'' if in_days == 1 else 's'}")
    return " · ".join(parts)


def _arrange_mixed(items: list[PlannedItem], interleave_subjects: bool) -> list[PlannedItem]:
    """Mixed review: an easy opener, subjects interleaved (telling similar things
    apart is part of the skill), and a likely success to close on."""
    reviews = sorted((i for i in items if i.kind == "review"), key=lambda i: -i.recall)
    opener = reviews.pop(0) if reviews else None
    closer = reviews.pop(0) if reviews else None
    rest = reviews + [i for i in items if i.kind == "new"]
    if interleave_subjects:
        middle = _interleave(rest, opener.subject if opener else None)
    else:
        middle = sorted(rest, key=lambda i: i.subject)
    return [i for i in (opener, *middle, closer) if i is not None]


_RANK = {"repair": 0, "review": 1, "new": 2, "practice": 3}


def _arrange_focused(items: list[PlannedItem], depth: Callable[[str], int]) -> list[PlannedItem]:
    """Mission: foundations first, then one notion at a time (blocked practice
    suits a skill being acquired), ending on a likely success."""

    def compare(a: PlannedItem, b: PlannedItem) -> int:
        by_rank = _RANK[a.kind] - _RANK[b.kind]
        by_depth = depth(a.ku_id) - depth(b.ku_id)
        if a.kind == "repair" or b.kind == "repair":
            return by_rank or by_depth
        return by_depth or by_rank

    ordered = sorted(items, key=cmp_to_key(compare))
    reviews = [i for i in ordered if i.kind in ("review", "practice")]
    if len(reviews) < 2:
        return ordered
    closer = max(reviews, key=lambda i: i.recall)
    return [i for i in ordered if i is not closer] + [closer]


def _interleave(items: list[PlannedItem], previous_subject: str | None) -> list[PlannedItem]:
    queues: dict[str, list[PlannedItem]] = {}
    for item in items:
        queues.setdefault(item.subject, []).append(item)
    out: list[PlannedItem] = []
    last = previous_subject
    while len(out) < len(items):
        open_queues = sorted(((s, q) for s, q in queues.items() if q), key=lambda e: -len(e[1]))
        subject, queue = next(((s, q) for s, q in open_queues if s != last), open_queues[0])
        out.append(queue.pop(0))
        last = subject
    return out
