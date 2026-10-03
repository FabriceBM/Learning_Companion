"""Target probability of recall when a unit comes back.

This is the main dial between "remember more" and "spend less time". Values: tuning.py.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime

from .clock import days_between
from .model import Goal, KnowledgeUnit
from .tuning import DEFAULT_TUNING, RetentionTuning, WorkloadTuning

RetentionPolicy = RetentionTuning

DEFAULT_RETENTION: RetentionPolicy = DEFAULT_TUNING.retention


def next_goal(ku: KnowledgeUnit, goals: Sequence[Goal], now: datetime) -> Goal | None:
    """The soonest test still ahead that this unit counts for."""
    ahead = [g for g in goals if g.id in ku.goal_ids and g.date > now]
    return min(ahead, key=lambda g: g.date, default=None)


def target_retention(
    ku: KnowledgeUnit,
    goals: Sequence[Goal],
    now: datetime,
    policy: RetentionPolicy = DEFAULT_RETENTION,
) -> float:
    goal = next_goal(ku, goals, now)
    if goal is not None and days_between(now, goal.date) <= policy.test_window_days:
        return policy.test
    if goal is None and ku.goal_ids and not ku.cumulative:
        return policy.maintenance
    if ku.importance == 3:
        return policy.foundational
    if ku.importance == 1:
        return policy.nice_to_know
    return policy.base


def relax_for_load(
    policy: RetentionPolicy,
    overload: float,
    workload: WorkloadTuning = DEFAULT_TUNING.workload,
) -> RetentionPolicy:
    """When the work needed keeps exceeding the agreed time budget, aim a little
    lower instead of piling up a backlog. Test targets are left alone.

    ``overload`` is the average (minutes needed / minutes budgeted) over the last week.
    """
    if overload <= workload.overload_threshold:
        return policy
    drop = min(workload.max_drop, (overload - 1) * workload.drop_per_overload)

    def floor(value: float) -> float:
        return max(policy.maintenance, value - drop)

    return replace(
        policy,
        base=floor(policy.base),
        foundational=floor(policy.foundational),
        nice_to_know=floor(policy.nice_to_know),
    )
