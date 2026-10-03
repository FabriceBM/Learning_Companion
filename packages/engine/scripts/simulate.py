"""60 school days, two synthetic learners, four subjects, five tests.

Compares the adaptive engine with a fixed ladder (Leitner/Duolingo-style
intervals 1-2-4-7-14-30-60 days that ignore who is learning), both with the
same 10-minute daily budget and the same new-material limit.

The learners are synthetic: each has a hidden "true" FSRS-6 memory that decides
whether an answer is right. The numbers show how the mechanics behave; they are
not evidence about real children.

    uv run packages/engine/scripts/simulate.py
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import datetime
from zoneinfo import ZoneInfo

from fsrs_rs_python import FSRS, MemoryState

from lc_engine import (
    DEFAULT_WEIGHTS,
    AdaptiveScheduler,
    Card,
    Goal,
    ItemState,
    KnowledgeUnit,
    Latency,
    LearnerProfile,
    MemoryModel,
    Rating,
    ReviewRecord,
    Rng,
    add_days,
    days_between,
    fit_weights,
    forgetting_curve,
    interval_days,
    plan_session,
    seeded_rng,
)

PARIS = ZoneInfo("Europe/Paris")
START = datetime(2026, 9, 7, 17, 0, tzinfo=PARIS)  # Monday, after school
DAYS = 60
SECONDS_PER_REVIEW = 12
REFIT_DAYS = (14, 28, 42)


def at_hour(dt: datetime, hour: int) -> datetime:
    return dt.replace(hour=hour, minute=0, second=0, microsecond=0)


def mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


# ---------------------------------------------------------------- curriculum


@dataclass(frozen=True)
class Lesson:
    id: str
    subject: str
    day: int
    cumulative: bool


SUBJECTS = [("Maths", 0, True), ("French", 1, True), ("Spanish", 2, True), ("History", 3, False)]

# One new lesson per subject per week, 12 units each: about 430 units in 60 days.
LESSONS = [
    Lesson(f"{subject.lower()}-{week + 1}", subject, week * 7 + offset, cumulative)
    for subject, offset, cumulative in SUBJECTS
    for week in range(9)
    if week * 7 + offset < DAYS
]


def lesson_ids(subject: str, weeks: list[int]) -> list[str]:
    return [f"{subject.lower()}-{w}" for w in weeks]


TESTS = [
    ("maths-1", "Maths test 1", 17, lesson_ids("Maths", [1, 2, 3])),
    ("french", "Dictation", 24, lesson_ids("French", [1, 2, 3, 4])),
    ("spanish", "Spanish quiz", 31, lesson_ids("Spanish", [1, 2, 3, 4, 5])),
    ("history", "History test", 45, lesson_ids("History", [3, 4, 5, 6, 7])),
    ("maths-2", "Maths test 2", 52, lesson_ids("Maths", [5, 6, 7, 8])),
]

# Tests are in the morning, before that day's after-school session.
GOALS = [Goal(tid, title, at_hour(add_days(START, day), 9)) for tid, title, day, _ in TESTS]

KINDS = {"Maths": "procedure", "History": "fact", "French": "rule", "Spanish": "term"}


def build_units(rng: Rng) -> list[tuple[KnowledgeUnit, Lesson]]:
    units = []
    for lesson in LESSONS:
        tests = [tid for tid, _, _, lessons in TESTS if lesson.id in lessons]
        earlier = [x for x in LESSONS if x.subject == lesson.subject and x.day < lesson.day]
        previous = earlier[-1] if earlier else None
        for i in range(12):
            r = rng()
            ku = KnowledgeUnit(
                id=f"{lesson.id}/{i}",
                subject=lesson.subject,
                kind=KINDS[lesson.subject],
                title=f"{lesson.id} #{i}",
                importance=3 if r < 0.2 else 2 if r < 0.85 else 1,
                # In maths, each lesson builds on the first unit of the previous one.
                prerequisites=[f"{previous.id}/0"] if lesson.subject == "Maths" and previous else [],
                goal_ids=tests,
                cumulative=lesson.cumulative,
            )
            units.append((ku, lesson))
    # In the order lessons were taught: every policy introduces new material in this order.
    return sorted(units, key=lambda u: u[1].day)


# ---------------------------------------------------------- synthetic minds


@dataclass
class Mind:
    label: str
    weights: list[float]

    def __post_init__(self) -> None:
        self.model = FSRS(self.weights)


def mind(label: str, initial_scale: float, growth_shift: float) -> Mind:
    """Hidden truth: scale initial stabilities and shift how fast memories consolidate."""
    w = list(DEFAULT_WEIGHTS)
    for i in range(4):
        w[i] *= initial_scale
    w[8] += growth_shift
    return Mind(label, w)


MINDS = [mind("A: forgets fast", 0.45, -0.45), mind("B: strong memory", 1.6, 0.3)]


@dataclass
class Truth:
    stability: float
    difficulty: float
    last: datetime


def answer(m: Mind, truth: Truth | None, at: datetime, rng: Rng) -> Rating:
    """The learner answers; the hidden memory decides."""
    if truth is None:
        # First meeting: the learner studies the card, then answers it once.
        r = rng()
        return Rating.Good if r < 0.75 else Rating.Hard if r < 0.92 else Rating.Again
    recall = forgetting_curve(m.weights, days_between(truth.last, at), truth.stability)
    if rng() >= recall:
        return Rating.Again
    if recall > 0.95 and rng() < 0.4:
        return Rating.Easy
    return Rating.Hard if recall < 0.75 else Rating.Good


def learn_truth(m: Mind, truth: Truth | None, at: datetime, grade: Rating) -> Truth:
    elapsed = max(0, round(days_between(truth.last, at))) if truth else 0
    state = MemoryState(truth.stability, truth.difficulty) if truth else None
    nxt = m.model.next_states(state, 0.9, elapsed)
    chosen = {Rating.Again: nxt.again, Rating.Hard: nxt.hard, Rating.Good: nxt.good, Rating.Easy: nxt.easy}[grade]
    return Truth(chosen.memory.stability, chosen.memory.difficulty, at)


def true_recall(m: Mind, truth: Truth | None, at: datetime) -> float:
    return forgetting_curve(m.weights, days_between(truth.last, at), truth.stability) if truth else 0.0


# ---------------------------------------------------------------- policies

PROFILE = LearnerProfile(
    id="sim",
    name="sim",
    session_minutes=10,
    sessions_per_day=1,
    min_gap_minutes=90,
    max_new_per_day=8,
    seconds_per_probe=dict.fromkeys(("recognize", "recall", "apply", "explain"), SECONDS_PER_REVIEW),
    latency_ms=Latency(3000, 9000),
    recent_accuracy=0.85,
)


@dataclass
class Policy:
    name: str
    plan: Callable[[datetime, list[KnowledgeUnit]], list[str]]
    record: Callable[[KnowledgeUnit, datetime, Rating], None]
    end_of_day: Callable[[int], None] = lambda day: None
    predict: Callable[[KnowledgeUnit, datetime], tuple[float, float]] | None = None
    mean_interval: Callable[[], float] | None = None


def engine(name: str, personalise: bool, test_aware: bool) -> Policy:
    """FSRS planner and scheduler; optionally refits weights to the learner and plans around tests."""
    goals = GOALS if test_aware else []
    cards: dict[str, Card] = {}
    population: dict[str, Card] = {}
    population_scheduler = AdaptiveScheduler(MemoryModel(), goals)
    log: list[ReviewRecord] = []
    recent: list[bool] = []
    intervals: list[float] = []
    reps: dict[str, int] = {}
    units: dict[str, KnowledgeUnit] = {}
    state = {"memory": MemoryModel()}
    state["scheduler"] = AdaptiveScheduler(state["memory"], goals)

    def plan(now: datetime, available: list[KnowledgeUnit]) -> list[str]:
        for ku in available:
            units[ku.id] = ku
        items = [ItemState(ku, cards.get(ku.id)) for ku in available]
        accuracy = sum(recent) / len(recent) if recent else 0.85
        learner = replace(PROFILE, recent_accuracy=accuracy)
        return [i.ku_id for i in plan_session(learner, items, goals, now, state["memory"]).items]

    def record(ku: KnowledgeUnit, at: datetime, grade: Rating) -> None:
        card = state["scheduler"].record(ItemState(ku, cards.get(ku.id)), at, grade)
        cards[ku.id] = card
        population[ku.id] = population_scheduler.record(ItemState(ku, population.get(ku.id)), at, grade)
        log.append(ReviewRecord(ku.id, at, grade))
        recent.append(grade != Rating.Again)
        if len(recent) > 50:
            recent.pop(0)
        reps[ku.id] = reps.get(ku.id, 0) + 1
        if reps[ku.id] >= 3:
            intervals.append(interval_days(card))

    def end_of_day(day: int) -> None:
        if not personalise or day not in REFIT_DAYS:
            return
        weights = fit_weights(log)
        if weights is None:
            return
        state["memory"] = MemoryModel(weights)
        state["scheduler"] = AdaptiveScheduler(state["memory"], goals)
        # The review log is the source of truth: replay it to rebuild memory states with the new weights.
        cards.clear()
        for r in sorted(log, key=lambda r: r.at):
            cards[r.ku_id] = state["scheduler"].record(ItemState(units[r.ku_id], cards.get(r.ku_id)), r.at, r.grade)
        intervals.clear()

    def predict(ku: KnowledgeUnit, at: datetime) -> tuple[float, float]:
        return (
            state["memory"].retrievability(cards.get(ku.id), at),
            population_scheduler.memory.retrievability(population.get(ku.id), at),
        )

    return Policy(name, plan, record, end_of_day, predict, lambda: mean(intervals))


def fixed_ladder() -> Policy:
    """Leitner/Duolingo-style: the same intervals for every learner, back to the start on a miss."""
    ladder = [1, 2, 4, 7, 14, 30, 60]
    state: dict[str, tuple[int, datetime]] = {}

    def plan(now: datetime, available: list[KnowledgeUnit]) -> list[str]:
        end_of_day = add_days(at_hour(now, 0), 1)
        due = sorted((ku for ku in available if ku.id in state and state[ku.id][1] < end_of_day), key=lambda ku: state[ku.id][1])
        budget = PROFILE.session_minutes * 60
        picked = [ku.id for ku in due[: budget // SECONDS_PER_REVIEW]]
        used = len(picked) * SECONDS_PER_REVIEW
        if len(picked) == len(due):
            for ku in [k for k in available if k.id not in state][: PROFILE.max_new_per_day]:
                if used + 2 * SECONDS_PER_REVIEW > budget:
                    break
                picked.append(ku.id)
                used += 2 * SECONDS_PER_REVIEW
        return picked

    def record(ku: KnowledgeUnit, at: datetime, grade: Rating) -> None:
        current = state.get(ku.id)
        step = 0 if current is None or grade == Rating.Again else min(current[0] + 1, len(ladder) - 1)
        state[ku.id] = (step, add_days(at, ladder[step]))

    return Policy("Fixed ladder", plan, record)


# ---------------------------------------------------------------- run


@dataclass
class Outcome:
    policy: str
    learner: str
    minutes_per_day: float
    tests: list[float]
    retained_at_end: float
    learned: int
    log_loss: tuple[float, float] | None = None
    mean_interval: float | None = None
    extra: dict = field(default_factory=dict)


def log_loss(rows: list[tuple[float, bool]]) -> float:
    def clamp(p: float) -> float:
        return min(0.999, max(0.001, p))

    return mean([-(math.log(clamp(p)) if y else math.log(1 - clamp(p))) for p, y in rows])


def run(policy: Policy, m: Mind, seed: int) -> Outcome:
    random.seed(seed)  # py-fsrs interval fuzz
    units = build_units(seeded_rng(seed))
    by_id = {ku.id: ku for ku, _ in units}
    truth: dict[str, Truth] = {}
    attendance = seeded_rng(seed + 1)
    answers = seeded_rng(seed + 2)
    minutes: list[float] = []
    tests: list[float] = []
    predictions: list[tuple[float, float, bool]] = []

    for day in range(DAYS):
        now = add_days(START, day)
        for _, _, test_day, lessons in TESTS:
            if test_day == day:
                tested = [ku for ku, lesson in units if lesson.id in lessons]
                tests.append(mean([true_recall(m, truth.get(ku.id), at_hour(now, 9)) for ku in tested]))

        skip = now.isoweekday() == 7 or attendance() < 0.1  # Sunday rest + the odd missed day
        if not skip:
            available = [ku for ku, lesson in units if lesson.day <= day]
            seconds = 0
            for uid in policy.plan(now, available):
                ku = by_id[uid]
                is_new = uid not in truth
                predicted = policy.predict(ku, now) if policy.predict else None
                grade = answer(m, truth.get(uid), now, answers)
                # Held-out check: predictions made before the answer, scored on the last 17 days.
                if not is_new and predicted and day >= DAYS - 17:
                    predictions.append((*predicted, grade != Rating.Again))
                truth[uid] = learn_truth(m, truth.get(uid), now, grade)
                policy.record(ku, now, grade)
                seconds += 2 * SECONDS_PER_REVIEW if is_new else SECONDS_PER_REVIEW
            minutes.append(seconds / 60)
        policy.end_of_day(day)

    end = add_days(START, DAYS)
    return Outcome(
        policy=policy.name,
        learner=m.label,
        minutes_per_day=mean(minutes),
        tests=tests,
        # Units never studied count as 0: time not spent on them is a real cost.
        retained_at_end=mean([true_recall(m, truth.get(ku.id), end) for ku, _ in units]),
        learned=sum(1 for ku, _ in units if ku.id in truth),
        log_loss=(log_loss([(p, y) for p, _, y in predictions]), log_loss([(q, y) for _, q, y in predictions]))
        if predictions
        else None,
        mean_interval=policy.mean_interval() if policy.mean_interval else None,
    )


def pct(x: float) -> str:
    return f"{round(x * 100)}%"


def table(rows: list[dict[str, str]]) -> None:
    headers = list(rows[0])
    widths = [max(len(h), *(len(r[h]) for r in rows)) for h in headers]
    print("  ".join(h.ljust(w) for h, w in zip(headers, widths, strict=True)))
    print("  ".join("-" * w for w in widths))
    for r in rows:
        print("  ".join(r[h].ljust(w) for h, w in zip(headers, widths, strict=True)))


def main() -> None:
    policies = [
        fixed_ladder,
        lambda: engine("FSRS, population weights", personalise=False, test_aware=False),
        lambda: engine("Adaptive (personal + test-aware)", personalise=True, test_aware=True),
    ]
    outcomes = [run(make(), m, 42) for m in MINDS for make in policies]

    unit_count = len(build_units(seeded_rng(42)))
    print(
        f"\n{DAYS} days · {unit_count} units in {len(LESSONS)} lessons · one {PROFILE.session_minutes}-min session a day"
        " · Sunday off, ~10% of days missed\n"
    )
    table(
        [
            {
                "learner": o.learner,
                "policy": o.policy,
                "min/day": f"{o.minutes_per_day:.1f}",
                "units studied": str(o.learned),
                "recall on test days": pct(mean(o.tests)),
                "worst test": pct(min(o.tests)),
                "all units, recall at day 60": pct(o.retained_at_end),
            }
            for o in outcomes
        ]
    )
    print("\nPersonalisation (adaptive engine; weights refitted on days 14, 28, 42):")
    table(
        [
            {
                "learner": o.learner,
                "mean interval, mature units": f"{o.mean_interval:.1f} days",
                "log loss, population weights": f"{o.log_loss[1]:.3f}",
                "log loss, personal weights": f"{o.log_loss[0]:.3f}",
            }
            for o in outcomes
            if o.policy.startswith("Adaptive") and o.log_loss
        ]
    )
    print("Log loss of recall predictions on the last 17 days (lower = the model knows this learner better).\n")


if __name__ == "__main__":
    main()
