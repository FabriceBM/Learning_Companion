"""Run one session from a plan, adapting inside it."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .model import Attempt
from .planner import PlannedItem, SessionPlan
from .tuning import DEFAULT_TUNING, SessionTuning

DoneReason = Literal["plan-complete", "time-budget", "child-stopped", "ease-off"]


@dataclass(frozen=True)
class Ask:
    item: PlannedItem
    retry: bool
    type: Literal["ask"] = "ask"


@dataclass(frozen=True)
class Done:
    reason: DoneReason
    message: str
    type: Literal["done"] = "done"


SessionStep = Ask | Done


@dataclass(frozen=True)
class SessionResult:
    item: PlannedItem
    attempt: Attempt
    retry: bool
    """Second try within the same session: shown to help, not sent to the memory model."""


class SessionRunner:
    """Missed units come back once at the end, a run of misses brings an easier
    unit, and the session ends when the time budget is used, whatever is left.

    After ``ease_off_after_misses`` misses in a row an easier unit slips in; after
    ``stop_after_misses`` the session ends kindly.
    """

    def __init__(self, plan: SessionPlan, budget_seconds: float, rules: SessionTuning = DEFAULT_TUNING.session) -> None:
        self.results: list[SessionResult] = []
        self._queue: list[tuple[PlannedItem, bool]] = [(item, False) for item in plan.items]
        self._budget_seconds = budget_seconds
        self._rules = rules
        self._elapsed_seconds = 0.0
        self._miss_streak = 0
        self._stopped = False

    def next(self) -> SessionStep:
        if self._stopped:
            return Done("child-stopped", "Stopped. Everything left moves to another day.")
        if self._miss_streak >= self._rules.stop_after_misses:
            return Done("ease-off", "Tough set today. Stopping here is the right call; these come back with a new explanation.")
        if self._elapsed_seconds >= self._budget_seconds:
            return Done("time-budget", "That's today's plan done. The rest moves to another day.")
        if not self._queue:
            return Done("plan-complete", "That's it for today.")
        if self._miss_streak >= self._rules.ease_off_after_misses:
            self._move_easiest_to_front()
        item, retry = self._queue.pop(0)
        return Ask(item, retry)

    def answer(self, item: PlannedItem, attempt: Attempt, seconds: float, retry: bool = False) -> None:
        self._elapsed_seconds += seconds
        self.results.append(SessionResult(item, attempt, retry))
        if attempt.correct:
            self._miss_streak = 0
            return
        self._miss_streak += 1
        if not retry:
            self._queue.append((item, True))

    def stop(self) -> None:
        """The learner can always stop, with no penalty."""
        self._stopped = True

    def _move_easiest_to_front(self) -> None:
        best = -1
        for index, (item, retry) in enumerate(self._queue):
            if not retry and (best < 0 or item.recall > self._queue[best][0].recall):
                best = index
        if best > 0:
            self._queue.insert(0, self._queue.pop(best))
