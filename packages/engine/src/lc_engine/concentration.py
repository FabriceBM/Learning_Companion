"""How a learner concentrates, learned from their own sessions.

It drives how long sessions are, how big a chunk to learn by heart, whether to
mix subjects, when to ease off, and how long a break should be. Each value
starts from an age default and moves toward the learner's data as sessions
accumulate (shrinkage), so a few odd days don't swing it.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from itertools import pairwise

from .clock import round_half_up
from .model import LearnerProfile
from .profiles import AgeBand, age_band
from .tuning import DEFAULT_TUNING, ConcentrationTuning, Tuning, with_tuning


@dataclass(frozen=True)
class ConcentrationProfile:
    attention_span_minutes: float
    """Minutes of good focus before accuracy or speed drops."""
    chunk_words: int
    """Words per by-heart chunk retained after one study."""
    switch_cost: float
    """Accuracy lost right after switching subject (0.1 = 10 points)."""
    best_hours: tuple[int, ...]
    """Hours of the day with the best results, e.g. (17, 18)."""
    recovery_minutes: float
    """Break after which results are back to normal."""
    frustration_after_misses: int
    """Misses in a row after which the next answer is usually missed too."""
    based_on_sessions: int = 0
    """Sessions the estimate is based on (0 = age defaults only)."""


_DEFAULTS: dict[AgeBand, ConcentrationProfile] = {
    "child": ConcentrationProfile(10, 8, 0.1, (17,), 90, 3),
    "young-teen": ConcentrationProfile(12, 12, 0.08, (17, 18), 90, 3),
    "adult": ConcentrationProfile(20, 20, 0.05, (20,), 60, 4),
}


def default_concentration(age: float) -> ConcentrationProfile:
    return _DEFAULTS[age_band(age)]


@dataclass(frozen=True)
class LoggedAnswer:
    at: datetime
    correct: bool
    latency_ms: float
    subject: str
    chunk_words: int | None = None
    """For by-heart chunks answered the first time: the chunk's size in words."""


@dataclass(frozen=True)
class SessionLog:
    started_at: datetime
    answers: Sequence[LoggedAnswer] = field(default_factory=tuple)


def _median(xs: Sequence[float]) -> float:
    if not xs:
        return math.nan
    s = sorted(xs)
    m = len(s) // 2
    return s[m] if len(s) % 2 else (s[m - 1] + s[m]) / 2


def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else math.nan


def _minutes(a: datetime, b: datetime) -> float:
    return (b - a).total_seconds() / 60


def _shrink(observed: float, n: float, prior: float, k: float) -> float:
    """Pull an observed value toward the prior: ``n`` observations against a prior worth ``k``."""
    return (n * observed + k * prior) / (n + k) if math.isfinite(observed) and n > 0 else prior


def estimate_concentration(
    logs: Sequence[SessionLog],
    prior: ConcentrationProfile,
    t: ConcentrationTuning = DEFAULT_TUNING.concentration,
) -> ConcentrationProfile:
    k = t.prior_weight
    sessions = [s for s in logs if len(s.answers) >= 6]
    n = len(sessions)

    # Attention span: pooled over sessions, the first minute where accuracy stays well below the
    # start (two minutes running) or answer time rises well above it.
    buckets: dict[int, tuple[list[float], list[float]]] = {}
    for s in sessions:
        for a in s.answers:
            correct, latency = buckets.setdefault(math.floor(_minutes(s.started_at, a.at)), ([], []))
            correct.append(1 if a.correct else 0)
            latency.append(a.latency_ms)
    early = [x for m in (0, 1, 2) for x in buckets.get(m, ([], []))[0]]
    early_latency = _median([x for m in (0, 1, 2) for x in buckets.get(m, ([], []))[1]])
    last_minute = max([-1, *buckets])
    span = math.nan
    if len(early) >= 10:
        acc_early = _mean(early)

        def low(m: int) -> bool:
            b = buckets.get(m)
            return b is not None and len(b[0]) >= 3 and acc_early - _mean(b[0]) >= t.attention_drop_points

        span = last_minute + 1  # censored: no drop seen
        for m in range(3, last_minute + 1):
            slower = _median(buckets.get(m, ([], []))[1]) >= early_latency * (1 + t.latency_rise)
            if (low(m) and (low(m + 1) or m == last_minute)) or slower:
                span = m
                break

    # Chunk size: largest chunk size whose first study usually holds.
    first_tries = [a for s in sessions for a in s.answers if a.chunk_words is not None]
    chunk = math.nan
    for size in sorted({a.chunk_words for a in first_tries if a.chunk_words is not None}):
        tries = [a for a in first_tries if a.chunk_words == size]
        if len(tries) >= 3 and _mean([1 if a.correct else 0 for a in tries]) >= t.chunk_success_target:
            chunk = size

    # Switch cost: accuracy right after changing subject versus staying on it.
    after: list[float] = []
    same: list[float] = []
    for s in sessions:
        for prev, a in pairwise(s.answers):
            (same if a.subject == prev.subject else after).append(1 if a.correct else 0)
    switch_cost = max(0.0, _mean(same) - _mean(after)) if len(after) >= 10 and len(same) >= 10 else math.nan

    # Best hours: hours with at least 10 answers and the highest accuracy.
    by_hour: dict[int, list[float]] = {}
    for s in sessions:
        for a in s.answers:
            by_hour.setdefault(a.at.hour, []).append(1 if a.correct else 0)
    ranked = sorted(((h, v) for h, v in by_hour.items() if len(v) >= 10), key=lambda e: -_mean(e[1]))
    best_hours = tuple(sorted(h for h, _ in ranked[:2])) if ranked else prior.best_hours

    # Recovery: shortest break after which a session starts as well as the learner does on average.
    overall = _mean([1 if a.correct else 0 for s in sessions for a in s.answers])
    ordered = sorted(sessions, key=lambda s: s.started_at)
    by_gap: dict[int, list[float]] = {}
    for prev, s in pairwise(ordered):
        gap = _minutes(prev.answers[-1].at, s.started_at)
        if gap > 12 * 60:
            continue  # only breaks within a day
        bucket = next((b for b in (30, 60, 90, 120, 180, 240) if gap <= b), 240)
        by_gap.setdefault(bucket, []).extend(1 if a.correct else 0 for a in s.answers[:3])
    recovered = [b for b, v in by_gap.items() if len(v) >= 6 and _mean(v) >= overall * 0.95]
    recovery = min(recovered) if recovered else math.nan

    # Frustration: smallest run of misses after which the next answer is usually a miss.
    frustration = math.nan
    for run in range(2, 7):
        following: list[float] = []
        for s in sessions:
            for i in range(run, len(s.answers)):
                if all(not a.correct for a in s.answers[i - run : i]):
                    following.append(0 if s.answers[i].correct else 1)
        if len(following) >= 5 and _mean(following) >= 0.6:
            frustration = run
            break

    def weight(value: float, count: float) -> float:
        return 0 if math.isnan(value) else count

    return ConcentrationProfile(
        attention_span_minutes=round_half_up(_shrink(span, weight(span, n), prior.attention_span_minutes, k)),
        chunk_words=round_half_up(_shrink(chunk, min(n, len(first_tries) / 3) if first_tries else 0, prior.chunk_words, k)),
        switch_cost=round_half_up(_shrink(switch_cost, weight(switch_cost, n), prior.switch_cost, k) * 100) / 100,
        best_hours=best_hours,
        recovery_minutes=round_half_up(_shrink(recovery, weight(recovery, len(by_gap)), prior.recovery_minutes, k)),
        frustration_after_misses=round_half_up(_shrink(frustration, weight(frustration, n), prior.frustration_after_misses, k)),
        based_on_sessions=n,
    )


@dataclass(frozen=True)
class Applied:
    learner: LearnerProfile
    tuning: Tuning
    interleave_mixed: bool
    chunk_words: int


def apply_concentration(profile: ConcentrationProfile, learner: LearnerProfile, tuning: Tuning = DEFAULT_TUNING) -> Applied:
    """Apply a profile within the family's limits: sessions no longer than the
    attention span, breaks at least as long as recovery, ease-off at the learner's
    frustration point, and mixed reviews grouped by subject when switching costs
    this learner too much."""
    return Applied(
        learner=replace(
            learner,
            session_minutes=max(5, min(learner.session_minutes, profile.attention_span_minutes)),
            min_gap_minutes=max(learner.min_gap_minutes, profile.recovery_minutes),
        ),
        tuning=with_tuning(
            {
                "session": {
                    "ease_off_after_misses": profile.frustration_after_misses,
                    "stop_after_misses": profile.frustration_after_misses + 2,
                }
            },
            tuning,
        ),
        interleave_mixed=profile.switch_cost <= tuning.concentration.group_above_switch_cost,
        chunk_words=profile.chunk_words,
    )
