"""From what the learner did to an FSRS grade, and which question to ask."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from fsrs import Card, Rating

from .model import PROBE_LEVELS, Attempt, KnowledgeKind, Latency, ProbeLevel
from .tuning import DEFAULT_TUNING, LadderTuning


def grade_attempt(attempt: Attempt, latency_ms: Latency) -> Rating:
    """Turn an observed answer into an FSRS grade.

    Children are not asked to rate themselves ("Easy" is the fastest way out of
    a session, so self-ratings drift). The grade comes from correctness, hints
    and answer time compared with this learner's own typical speed.
    """
    if not attempt.correct and not attempt.near_miss:
        return Rating.Again
    if attempt.near_miss or attempt.hints_used > 0:
        return Rating.Hard
    slow = attempt.latency_ms > latency_ms.p75
    if slow or attempt.confidence == "unsure":
        return Rating.Hard
    fluent = attempt.latency_ms < latency_ms.p25 and attempt.confidence == "sure"
    # Picking the answer among choices is easier than producing it, so it never counts as Easy.
    if fluent and attempt.level != "recognize":
        return Rating.Easy
    return Rating.Good


LADDER_TOP: Mapping[KnowledgeKind, ProbeLevel] = {
    "term": "apply",  # use the word in a sentence
    "fact": "recall",
    "rule": "apply",  # apply the rule to a new sentence
    "procedure": "apply",  # a fresh generated exercise each time
    "concept": "explain",
    "formula": "apply",
    "verbatim": "apply",  # full recitation; cues fade by stability (by_heart.py)
    "label": "apply",  # the whole figure blanked
}


def probe_level_for(kind: KnowledgeKind, card: Card | None, ladder: LadderTuning = DEFAULT_TUNING.ladder) -> ProbeLevel:
    """Choose the question form from memory stability: recognise while the
    memory is fragile, then produce, then apply to new material, then explain."""
    stability = (card.stability if card is not None else None) or 0
    if stability < ladder.recall_from_days:
        wanted: ProbeLevel = "recognize"
    elif stability < ladder.apply_from_days:
        wanted = "recall"
    elif stability < ladder.explain_from_days:
        wanted = "apply"
    else:
        wanted = "explain"
    cap = LADDER_TOP[kind]
    return wanted if PROBE_LEVELS.index(wanted) <= PROBE_LEVELS.index(cap) else cap


@dataclass(frozen=True)
class ProbeRef:
    id: str
    level: ProbeLevel


def pick_probe(probes: Sequence[ProbeRef], level: ProbeLevel, last_asked_at: Mapping[str, float]) -> ProbeRef | None:
    """Pick the question to ask for a unit at a level: the least recently asked
    one, so practising a rule or a method cycles through varied items instead of
    repeating the one the learner has memorised. Falls back to the nearest easier
    level when none exists at this one."""
    for index in range(PROBE_LEVELS.index(level), -1, -1):
        candidates = [p for p in probes if p.level == PROBE_LEVELS[index]]
        if candidates:
            return min(candidates, key=lambda p: last_asked_at.get(p.id, float("-inf")))
    return probes[0] if probes else None
