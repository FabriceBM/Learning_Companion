"""The data the engine works on.

Every subject is treated as "a language": a word, a spelling rule, a date, a
formula and a method are all units of knowledge with their own memory curve.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from fsrs import Card, Rating

KnowledgeKind = Literal[
    "term",  # vocabulary, definitions: "photosynthèse", "tener"
    "fact",  # dates, places, constants
    "rule",  # grammar, spelling, sign rules (with exceptions)
    "procedure",  # methods: adding fractions, solving an equation
    "concept",  # ideas that need explaining: why the seasons change
    "formula",
    "verbatim",  # learned word for word: a poem, a definition (by_heart.py)
    "label",  # a label on a map or diagram, learned by blanking it (by_heart.py)
]

ProbeLevel = Literal["recognize", "recall", "apply", "explain"]
"""Question forms, from easiest to hardest. The same unit climbs this ladder as
its memory gets more stable (desirable difficulty), so the child is never
drilled on the identical flashcard forever."""

PROBE_LEVELS: tuple[ProbeLevel, ...] = ("recognize", "recall", "apply", "explain")

Importance = Literal[1, 2, 3]
"""1 = nice to know, 2 = expected, 3 = foundational (other units build on it)."""

Grade = Rating
"""Again, Hard, Good, Easy: always derived from what the learner did (grading.py), never self-rated."""


@dataclass(frozen=True)
class KnowledgeUnit:
    id: str
    subject: str
    kind: KnowledgeKind
    title: str
    importance: Importance = 2
    prerequisites: Sequence[str] = ()
    """Units that should be stable before this one is introduced."""
    goal_ids: Sequence[str] = ()
    """Tests or projects this unit counts for."""
    notion_id: str | None = None
    """The notion on the knowledge map this unit belongs to (knowledge_map.py)."""
    cumulative: bool = True
    """Cumulative knowledge (times tables, conjugations) keeps a normal retention
    target after its tests; one-off material drops to a cheap maintenance level."""

    def __post_init__(self) -> None:
        object.__setattr__(self, "prerequisites", tuple(self.prerequisites))
        object.__setattr__(self, "goal_ids", tuple(self.goal_ids))


@dataclass(frozen=True)
class Goal:
    """A dated assessment: a class test, an oral, a recitation."""

    id: str
    title: str
    date: datetime


@dataclass(frozen=True)
class Latency:
    """Answer-time quartiles (ms), used to tell fluent answers from laboured ones."""

    p25: float = 3000
    p75: float = 9000


DEFAULT_SECONDS_PER_PROBE: Mapping[ProbeLevel, float] = {"recognize": 8, "recall": 12, "apply": 20, "explain": 35}


@dataclass(frozen=True)
class LearnerProfile:
    id: str
    name: str
    session_minutes: float = 10
    """Length of one session, agreed between child and parent; the planner never exceeds it."""
    sessions_per_day: int = 2
    """Most sessions in a day, each at least ``min_gap_minutes`` after the previous one."""
    min_gap_minutes: float = 90
    max_new_per_day: int = 10
    """New units per day, across all of the day's sessions."""
    seconds_per_probe: Mapping[ProbeLevel, float] = field(default_factory=lambda: dict(DEFAULT_SECONDS_PER_PROBE))
    """Typical seconds per question at each level, learned from the learner's history."""
    latency_ms: Latency = Latency()
    recent_accuracy: float = 0.85
    """Accuracy over the last ~50 answers; throttles new material when the learner is struggling."""
    weights: Sequence[float] | None = None
    """FSRS-6 weights fitted to this learner's history; None means population defaults."""


@dataclass(frozen=True)
class ItemState:
    """A unit together with this learner's memory of it."""

    ku: KnowledgeUnit
    card: Card | None = None
    """None until the unit has been studied once."""


@dataclass(frozen=True)
class Attempt:
    """What actually happened when the learner answered. Grading is objective, never self-rated."""

    correct: bool
    latency_ms: float
    level: ProbeLevel
    near_miss: bool = False
    """Right idea with a small slip (a typo when the unit is not about spelling)."""
    hints_used: int = 0
    confidence: Literal["sure", "unsure"] | None = None
    """Optional "sure / not sure" tap before the answer is revealed (trains calibration)."""
