"""What the screens call: the engine plus the phone's storage, with no UI code.

Kept apart from Flet so it is tested like the engine (app/tests).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from lc_engine import (
    MIXED_REVIEW,
    AdaptiveScheduler,
    Ask,
    Attempt,
    DayRules,
    DaySoFar,
    Done,
    ItemState,
    LearnerProfile,
    MemoryModel,
    Mission,
    PlannedItem,
    ProbeRef,
    Rating,
    SessionGate,
    SessionPlan,
    SessionRunner,
    Suggestion,
    apply_concentration,
    compare_recitation,
    cue,
    cue_for,
    default_concentration,
    defaults_for_age,
    grade_attempt,
    next_useful_time,
    pick_probe,
    plan_session,
    recitation_attempt,
    recitation_words,
    session_gate,
    suggest_missions,
    to_focus,
)

from .content import Content, Question, sample_content
from .store import Store


@dataclass(frozen=True)
class Prompt:
    """One card on screen."""

    ku_id: str
    title: str
    position: str
    """e.g. "3 / 9"."""
    retry: bool
    study_text: str | None = None
    """First meeting with a by-heart chunk: read it, then recite."""
    cue_text: str | None = None
    """By heart: the text with the cue level applied."""
    cue_level: str | None = None
    question: Question | None = None


@dataclass(frozen=True)
class Feedback:
    correct: bool
    near_miss: bool
    expected: str
    missing: tuple[str, ...] = ()


class Companion:
    def __init__(
        self,
        store: Store,
        *,
        learner_id: str = "child",
        age: int = 12,
        tz: str = "Europe/Paris",
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.store = store
        self.learner_id = learner_id
        self.tz = ZoneInfo(tz)
        self._now = now or (lambda: datetime.now(self.tz))
        band = defaults_for_age(age)
        base = LearnerProfile(
            id=learner_id,
            name=store.get("name", "Léa"),
            session_minutes=band.session_minutes,
            sessions_per_day=int(store.get("sessions_per_day", str(band.sessions_per_day))),
            min_gap_minutes=band.min_gap_minutes,
            max_new_per_day=band.max_new_per_day,
        )
        applied = apply_concentration(default_concentration(age), base)
        self.learner = applied.learner
        self.tuning = applied.tuning
        self.interleave = applied.interleave_mixed
        self.content: Content = sample_content(applied.chunk_words)
        self.memory = MemoryModel(learner_weights(store, learner_id), same_day_gap_minutes=self.learner.min_gap_minutes)
        self.scheduler = AdaptiveScheduler(self.memory)
        self.cards: dict[str, object] = {}
        self.last_asked: dict[str, float] = {}
        self._replay()

    # ------------------------------------------------------------ state

    def now(self) -> datetime:
        return self._now()

    def _replay(self) -> None:
        """Memory states are derived from the review log, never stored."""
        units = {u.id: u for u in self.content.units}
        for r in self.store.reviews(self.learner_id):
            if r.ku_id in units:
                item = ItemState(units[r.ku_id], self.cards.get(r.ku_id))  # type: ignore[arg-type]
                self.cards[r.ku_id] = self.scheduler.record(item, r.at, Rating(r.grade))
            if r.question_id:
                self.last_asked[r.question_id] = r.at.timestamp()

    @property
    def items(self) -> list[ItemState]:
        return [ItemState(u, self.cards.get(u.id)) for u in self.content.units]  # type: ignore[arg-type]

    def missions(self) -> list[Mission]:
        out = [Mission(mid, kind, title, tuple(ids)) for mid, (kind, title, ids) in self.content.missions.items()]  # type: ignore[arg-type]
        return [*out, MIXED_REVIEW]

    def suggestions(self) -> list[Suggestion]:
        return suggest_missions(self.missions(), self.items, self.memory, self.now(), self.tuning)

    def gate(self) -> SessionGate:
        now = self.now()
        today = self.store.sessions_on(self.learner_id, now)
        ended = [e for _, e, _ in today if e]
        rules = DayRules(self.learner.sessions_per_day, self.learner.min_gap_minutes)
        return session_gate(now, rules, DaySoFar(len(today), max(ended) if ended else None))

    def sessions_today(self) -> int:
        return len(self.store.sessions_on(self.learner_id, self.now()))

    def new_today(self) -> int:
        today = self.now().date()
        first_seen: dict[str, datetime] = {}
        for r in self.store.reviews(self.learner_id):
            first_seen.setdefault(r.ku_id, r.at)
        return sum(1 for at in first_seen.values() if at.astimezone(self.tz).date() == today)

    def next_useful(self) -> datetime | None:
        return next_useful_time(self.items, self.now())

    # ------------------------------------------------------------ a session

    def start(self, mission_id: str) -> Run:
        mission = next(m for m in self.missions() if m.id == mission_id)
        plan = plan_session(
            self.learner,
            self.items,
            [],
            self.now(),
            self.memory,
            tuning=self.tuning,
            new_today=self.new_today(),
            focus=to_focus(mission),
            interleave_mixed=self.interleave,
        )
        return Run(self, mission, plan.items)


class Run:
    """One session, card by card."""

    def __init__(self, companion: Companion, mission: Mission, planned: list[PlannedItem]) -> None:
        self.c = companion
        self.mission = mission
        self.planned = planned
        self.runner = SessionRunner(_plan(planned), companion.learner.session_minutes * 60, companion.tuning.session)
        self.session_id = companion.store.start_session(companion.learner_id, mission.id, companion.now())
        self.answers = 0
        self.correct = 0
        self._current: Ask | None = None
        self._question: Question | None = None
        self.done: Done | None = None

    @property
    def empty(self) -> bool:
        return not self.planned

    def next(self) -> Prompt | None:
        step = self.runner.next()
        if isinstance(step, Done):
            self.done = step
            self.finish()
            return None
        self._current = step
        item = step.item
        position = f"{min(len(self.runner.results) + 1, len(self.planned))} / {len(self.planned)}"
        text = self.c.content.texts.get(item.ku_id)
        if text is not None:
            card = self.c.cards.get(item.ku_id)
            level = cue_for(card, self.c.tuning.by_heart)  # type: ignore[arg-type]
            if level == "read":
                # First meeting: study the full text, then recite it with first letters as support.
                return Prompt(
                    item.ku_id,
                    item.title,
                    position,
                    step.retry,
                    study_text=text,
                    cue_text=cue(text, "first-letters"),
                    cue_level="first-letters",
                )
            return Prompt(item.ku_id, item.title, position, step.retry, cue_text=cue(text, level), cue_level=level)
        questions = self.c.content.questions[item.ku_id]
        level = "recognize" if item.level == "recognize" else "recall"
        probe = pick_probe([ProbeRef(q.id, q.level) for q in questions], level, self.c.last_asked)  # type: ignore[arg-type]
        self._question = next(q for q in questions if probe and q.id == probe.id)
        return Prompt(item.ku_id, item.title, position, step.retry, question=self._question)

    def answer(self, given: str, latency_ms: int, seconds: float) -> Feedback:
        assert self._current is not None, "call next() first"
        step = self._current
        ku_id = step.item.ku_id
        text = self.c.content.texts.get(ku_id)
        if text is not None:
            result = compare_recitation(text, given)
            # Long texts take longer: judge speed per five words, as for a short answer.
            per_chunk = latency_ms / max(1.0, len(text.split()) / 5)
            attempt = recitation_attempt(result, per_chunk, self.c.tuning.by_heart)
            written = recitation_words(text)
            feedback = Feedback(attempt.correct, attempt.near_miss, text, tuple(written[i] for i in result.missing_at))
            question_id = None
        else:
            q = self._question
            assert q is not None
            exact = compare_recitation(q.answer, given, accents=True).ratio == 1 and given.strip() != ""
            close = compare_recitation(q.answer, given).ratio == 1 and given.strip() != ""
            attempt = Attempt(
                correct=exact, near_miss=close and not exact, latency_ms=latency_ms, level="recognize" if q.choices else "recall"
            )
            feedback = Feedback(exact, close and not exact, q.answer)
            question_id = q.id
        self.runner.answer(step.item, attempt, seconds, step.retry)
        self.answers += 1
        self.correct += int(attempt.correct)
        if not step.retry:
            # A retry in the same session helps the learner but is not sent to the memory model.
            grade = grade_attempt(attempt, self.c.learner.latency_ms)
            now = self.c.now()
            self.c.store.add_review(self.c.learner_id, ku_id, now, int(grade), latency_ms, question_id)
            item = ItemState(next(u for u in self.c.content.units if u.id == ku_id), self.c.cards.get(ku_id))  # type: ignore[arg-type]
            self.c.cards[ku_id] = self.c.scheduler.record(item, now, grade)
        if question_id:
            self.c.last_asked[question_id] = self.c.now().timestamp()
        return feedback

    def stop(self) -> None:
        self.runner.stop()

    def finish(self) -> None:
        self.c.store.end_session(self.session_id, self.c.now(), self.answers)


def _plan(items: list[PlannedItem]) -> SessionPlan:
    return SessionPlan(items=items, minutes=0, deferred=0, waiting=0, subjects=[])


def learner_weights(store: Store, learner_id: str) -> list[float] | None:
    """Weights the server fitted for this learner, if any (stored as comma-separated numbers)."""
    raw = store.get(f"weights:{learner_id}")
    return [float(x) for x in raw.split(",")] if raw else None


__all__ = ["Companion", "Feedback", "Prompt", "Run"]
