"""When each unit comes back for one learner."""

from __future__ import annotations

from collections.abc import Sequence
from copy import copy
from datetime import datetime

from fsrs import Card, Rating

from .clock import add_days, days_between, local, start_of_day, to_utc
from .memory import MemoryModel
from .model import Goal, ItemState
from .retention import DEFAULT_RETENTION, RetentionPolicy, next_goal, target_retention


class AdaptiveScheduler:
    """The memory model gives the interval for the unit's target retention, then
    test dates can pull it earlier."""

    def __init__(self, memory: MemoryModel, goals: Sequence[Goal] = (), policy: RetentionPolicy = DEFAULT_RETENTION) -> None:
        self.memory = memory
        self.goals = tuple(goals)
        self.policy = policy

    def record(self, item: ItemState, at: datetime, grade: Rating) -> Card:
        """Apply one graded answer and return the unit's new memory state and due date."""
        target = target_retention(item.ku, self.goals, at, self.policy)
        card = self.memory.review(item.card, at, grade, target)
        goal = next_goal(item.ku, self.goals, at)
        return self._fit_to_goal(card, goal) if goal is not None else card

    def _fit_to_goal(self, card: Card, goal: Goal) -> Card:
        """If the normal interval would jump past a test and recall on test day
        would be below the test target, bring the review forward to 1-2 days
        before the test. A night of sleep between the last review and the test helps."""
        if card.due <= goal.date:
            return card
        if self.memory.retrievability(card, goal.date) >= self.policy.test:
            return card
        reviewed_at = local(card.last_review or card.due, goal.date)
        lead = 2 if days_between(reviewed_at, goal.date) >= 3 else 1
        due = max(add_days(reviewed_at, 1), add_days(start_of_day(goal.date), -lead))
        # The test is tomorrow morning: today's review was the last useful one.
        if due >= goal.date:
            return card
        moved = copy(card)
        moved.due = to_utc(due)
        return moved
