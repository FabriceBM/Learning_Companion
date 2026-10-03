"""One learner's memory model (FSRS-6, via py-fsrs)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta

from fsrs import Card, Rating, Scheduler

from .clock import days_between, to_utc
from .tuning import DEFAULT_TUNING

DEFAULT_WEIGHTS: tuple[float, ...] = tuple(Scheduler().parameters)
"""FSRS-6 population defaults (21 weights)."""


def forgetting_curve(weights: Sequence[float], elapsed_days: float, stability: float) -> float:
    """FSRS-6 power forgetting curve: probability of recall after ``elapsed_days``."""
    decay = -weights[20]
    factor = 0.9 ** (1 / decay) - 1
    return (1 + factor * elapsed_days / stability) ** decay


class MemoryModel:
    """Answers two questions for one learner: "how likely is recall right now?"
    and "after this answer, when should we ask again so that recall is still at
    the target probability?". The weights start at population defaults and are
    refitted to the learner's own review history (personalize.py).

    With several sessions a day, pass ``same_day_gap_minutes``: a new or missed
    unit then comes back after that break for a second look the same day
    (new unit: two steps; missed unit: one). With one session a day, retries
    happen inside the session and the memory model only schedules whole days.
    """

    def __init__(
        self,
        weights: Sequence[float] | None = None,
        *,
        same_day_gap_minutes: float | None = None,
        maximum_interval_days: int | None = None,
        fuzz: bool = True,
    ) -> None:
        self.weights = tuple(weights) if weights is not None else DEFAULT_WEIGHTS
        self.same_day_gap_minutes = same_day_gap_minutes
        self.maximum_interval_days = maximum_interval_days or DEFAULT_TUNING.memory.maximum_interval_days
        # Fuzz spreads due dates so a lesson learned in one go doesn't all fall due on one day.
        self.fuzz = fuzz
        self._schedulers: dict[float, Scheduler] = {}

    def retrievability(self, card: Card | None, at: datetime) -> float:
        """Probability of recall at ``at``; 0 for a unit never studied."""
        if card is None or card.last_review is None or card.stability is None:
            return 0.0
        elapsed = max(0.0, days_between(card.last_review, at))
        return forgetting_curve(self.weights, elapsed, card.stability)

    def review(self, card: Card | None, at: datetime, grade: Rating, retention: float) -> Card:
        """Apply one graded answer. The next due date aims for recall = ``retention``."""
        when = to_utc(at)
        current = card if card is not None else Card(card_id=0, due=when)
        reviewed, _log = self._scheduler(retention).review_card(current, Rating(grade), when)
        return reviewed

    def _scheduler(self, retention: float) -> Scheduler:
        key = round(retention, 2)
        scheduler = self._schedulers.get(key)
        if scheduler is None:
            gap = self.same_day_gap_minutes
            step = (timedelta(minutes=gap),) if gap is not None else ()
            scheduler = Scheduler(
                parameters=self.weights,
                desired_retention=key,
                learning_steps=step * 2,
                relearning_steps=step,
                maximum_interval=int(self.maximum_interval_days),
                enable_fuzzing=self.fuzz,
            )
            self._schedulers[key] = scheduler
        return scheduler


def interval_days(card: Card) -> float:
    """Days from the last review to the next one."""
    if card.last_review is None:
        return 0.0
    return days_between(card.last_review, card.due)
