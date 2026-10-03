"""Every fine-tuning knob of the engine, in one place.

Defaults come from the learning-science literature or from the simulation; each
one can be changed per family (or per learner) within its range.
``docs/PARAMETERS.md`` is generated from TUNING_SPEC (scripts/params.py).

Time limits a family sets for each learner (session length, sessions per day,
break, reminders, new units per day) live in profiles.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields, replace


@dataclass(frozen=True)
class RetentionTuning:
    base: float = 0.9
    """Target probability of recall when a unit comes back."""
    foundational: float = 0.92
    nice_to_know: float = 0.85
    test_window_days: int = 7
    """Days before a test during which its units aim higher."""
    test: float = 0.95
    maintenance: float = 0.8
    """One-off material whose tests are all past."""


@dataclass(frozen=True)
class WorkloadTuning:
    overload_threshold: float = 1.1
    """Relax everyday targets when needed time / budget stays above this."""
    drop_per_overload: float = 0.05
    max_drop: float = 0.06


@dataclass(frozen=True)
class LadderTuning:
    """Memory stability (days) from which each harder question form is used."""

    recall_from_days: float = 3
    apply_from_days: float = 10
    explain_from_days: float = 30


@dataclass(frozen=True)
class PlannerTuning:
    weight_nice_to_know: float = 0.7
    weight_expected: float = 1
    weight_foundational: float = 1.4
    test_boost: float = 1
    """Extra priority for a unit whose test is tomorrow (fades over the test window)."""
    risk_floor: float = 0.05
    """Added to (target - recall) so units at target still get some priority."""
    prerequisite_recall: float = 0.8
    """A prerequisite counts as known from this predicted recall."""
    pause_new_below: float = 0.7
    """No new material below this recent accuracy..."""
    halve_new_below: float = 0.8
    """...and half as much below this one."""
    new_unit_cost: float = 2
    """A new unit takes this many times a recognition question (study + answer)."""


@dataclass(frozen=True)
class SessionTuning:
    ease_off_after_misses: int = 3
    stop_after_misses: int = 5


@dataclass(frozen=True)
class MissionTuning:
    focus_share: float = 1
    """Share of a mission session spent on the mission; the rest goes to the most at-risk other reviews."""
    secure_stability_days: float = 7
    """A mission unit is secure once its memory stability reaches this many days."""
    repair_below_recall: float = 0.8
    """Prerequisites below this recall are repaired first."""


@dataclass(frozen=True)
class ReminderTuning:
    self_start_share: float = 0.8
    """Reminders pause once the child starts on their own on this share of active days..."""
    lookback_days: int = 14
    """...over this many days..."""
    min_active_days: int = 7
    """...with at least this many active days."""
    backoff_after_ignored: int = 3
    stop_after_ignored: int = 6
    follow_window_minutes: int = 30
    """A reminder counts as followed if a session starts within this many minutes."""


@dataclass(frozen=True)
class MemoryTuning:
    maximum_interval_days: int = 365
    min_reviews_to_fit: int = 400
    refit_every_days: int = 7


@dataclass(frozen=True)
class ByHeartTuning:
    key_words_from_days: float = 2
    """Memory stability (days) from which key words are blanked instead of showing first letters..."""
    recite_from_days: float = 5
    """...and from which the chunk is recited with nothing shown."""
    pass_ratio: float = 0.95
    """Share of words recited in order to count as correct..."""
    near_miss_ratio: float = 0.85
    """...and as a near miss."""


@dataclass(frozen=True)
class ConcentrationTuning:
    prior_weight: float = 5
    """How many sessions the age default is worth when blending it with the learner's data."""
    attention_drop_points: float = 0.15
    """Accuracy drop (points) that marks the end of focus within a session."""
    latency_rise: float = 0.4
    """Rise in answer time that marks the end of focus."""
    chunk_success_target: float = 0.7
    """A chunk size holds when this share of first studies succeed."""
    group_above_switch_cost: float = 0.15
    """Above this switch cost, mixed reviews are grouped by subject."""


@dataclass(frozen=True)
class Tuning:
    retention: RetentionTuning = RetentionTuning()
    workload: WorkloadTuning = WorkloadTuning()
    ladder: LadderTuning = LadderTuning()
    planner: PlannerTuning = PlannerTuning()
    session: SessionTuning = SessionTuning()
    mission: MissionTuning = MissionTuning()
    reminders: ReminderTuning = ReminderTuning()
    memory: MemoryTuning = MemoryTuning()
    by_heart: ByHeartTuning = ByHeartTuning()
    concentration: ConcentrationTuning = ConcentrationTuning()


DEFAULT_TUNING = Tuning()


@dataclass(frozen=True)
class ParamSpec:
    path: str
    label: str
    min: float
    max: float
    step: float
    why: str
    """Why the default is what it is."""


def _p(path: str, label: str, lo: float, hi: float, step: float, why: str) -> ParamSpec:
    return ParamSpec(path, label, lo, hi, step, why)


TUNING_SPEC: tuple[ParamSpec, ...] = (
    _p(
        "retention.base",
        "Target recall, everyday units",
        0.75,
        0.97,
        0.01,
        "Above ~0.9 the review load grows steeply for little gain (FSRS workload curves).",
    ),
    _p(
        "retention.foundational",
        "Target recall, foundational units",
        0.75,
        0.97,
        0.01,
        "Other units build on these, so forgetting them costs more.",
    ),
    _p(
        "retention.nice_to_know",
        "Target recall, nice-to-know units",
        0.7,
        0.95,
        0.01,
        "Cheaper upkeep for material that matters less.",
    ),
    _p(
        "retention.test_window_days",
        "Test window (days)",
        1,
        21,
        1,
        "A week of higher targets before a test, not more: earlier cramming fades.",
    ),
    _p("retention.test", "Target recall before a test", 0.85, 0.98, 0.01, "Aim high only when it is about to be checked."),
    _p("retention.maintenance", "Target recall after a one-off test", 0.6, 0.9, 0.01, "Keeps old chapters alive at little cost."),
    _p(
        "workload.overload_threshold",
        "Overload threshold (needed / budget)",
        1,
        2,
        0.05,
        "Relax targets when the work needed keeps exceeding the time agreed.",
    ),
    _p(
        "workload.drop_per_overload",
        "Target drop per unit of overload",
        0,
        0.2,
        0.01,
        "Gentle: a 50% overload lowers targets by 0.025.",
    ),
    _p("workload.max_drop", "Largest target drop", 0, 0.15, 0.01, "Never below the maintenance level."),
    _p(
        "ladder.recall_from_days",
        "Recall questions from (stability, days)",
        1,
        14,
        1,
        "Pick among choices while a memory is fragile, then produce it.",
    ),
    _p(
        "ladder.apply_from_days",
        "Apply questions from (stability, days)",
        3,
        30,
        1,
        "Use on new material once recall is reliable (desirable difficulty).",
    ),
    _p(
        "ladder.explain_from_days",
        "Explain questions from (stability, days)",
        7,
        90,
        1,
        "Explaining why is the deepest check, kept for stable knowledge.",
    ),
    _p("planner.weight_nice_to_know", "Priority weight, nice to know", 0.1, 2, 0.1, "Relative priority when time is short."),
    _p("planner.weight_expected", "Priority weight, expected", 0.1, 2, 0.1, "Reference weight."),
    _p("planner.weight_foundational", "Priority weight, foundational", 0.1, 3, 0.1, "Foundations first when time is short."),
    _p(
        "planner.test_boost",
        "Priority boost the day before a test",
        0,
        3,
        0.1,
        "1 doubles the priority on the eve of the test, fading over the test window.",
    ),
    _p("planner.risk_floor", "Priority floor", 0, 0.2, 0.01, "Units right at their target still get some priority."),
    _p(
        "planner.prerequisite_recall",
        "Prerequisite counts as known from recall",
        0.5,
        0.95,
        0.05,
        "New units wait until what they build on is known.",
    ),
    _p(
        "planner.pause_new_below",
        "Pause new material below accuracy",
        0.4,
        0.9,
        0.05,
        "Struggling means consolidate first, not add more.",
    ),
    _p(
        "planner.halve_new_below",
        "Halve new material below accuracy",
        0.5,
        0.95,
        0.05,
        "Most answers should succeed: learning is fastest around 85% success.",
    ),
    _p("planner.new_unit_cost", "Time cost of a new unit (× a question)", 1, 4, 0.5, "Studying the card, then answering it."),
    _p(
        "session.ease_off_after_misses",
        "Easier unit after this many misses in a row",
        2,
        6,
        1,
        "Rebuild confidence before continuing.",
    ),
    _p(
        "session.stop_after_misses",
        "End the session after this many misses in a row",
        3,
        10,
        1,
        "Past this point, re-teaching beats more questions.",
    ),
    _p(
        "mission.focus_share",
        "Share of a mission session on the mission",
        0.5,
        1,
        0.05,
        "1 = full focus; lower keeps a few at-risk reviews from other subjects alive.",
    ),
    _p(
        "mission.secure_stability_days",
        "Mission unit is secure from (stability, days)",
        3,
        30,
        1,
        "Needs correct answers on separate days (successive relearning), not one good session.",
    ),
    _p(
        "mission.repair_below_recall",
        "Repair prerequisites below recall",
        0.5,
        0.95,
        0.05,
        "Fix the foundations before building on them.",
    ),
    _p(
        "reminders.self_start_share",
        "Pause reminders from this self-start share",
        0.5,
        1,
        0.05,
        "The habit has formed; the reminder has done its job.",
    ),
    _p("reminders.lookback_days", "Self-start measured over (days)", 7, 28, 1, "Two weeks smooths out holidays and busy days."),
    _p("reminders.min_active_days", "Minimum active days before pausing", 3, 14, 1, "Do not conclude from too few days."),
    _p("reminders.backoff_after_ignored", "Every other day after this many ignored", 2, 10, 1, "Back off, never escalate."),
    _p(
        "reminders.stop_after_ignored",
        "Stop reminding after this many ignored",
        3,
        15,
        1,
        "Then parents see it in the weekly summary instead.",
    ),
    _p(
        "reminders.follow_window_minutes",
        "Reminder followed if a session starts within (min)",
        10,
        120,
        5,
        "Used to learn which time slot works for each child.",
    ),
    _p(
        "memory.maximum_interval_days",
        "Longest gap between reviews (days)",
        30,
        3650,
        5,
        "A yearly check even on very stable memories.",
    ),
    _p(
        "memory.min_reviews_to_fit",
        "Reviews needed before personal fitting",
        100,
        2000,
        50,
        "Below this, defaults predict better than a fit.",
    ),
    _p(
        "memory.refit_every_days",
        "Refit personal weights every (days)",
        1,
        30,
        1,
        "Weekly is enough; memory habits change slowly.",
    ),
    _p(
        "by_heart.key_words_from_days",
        "Blank key words from (stability, days)",
        0.5,
        7,
        0.5,
        "First letters while the text is fresh, then only the small words stay.",
    ),
    _p(
        "by_heart.recite_from_days",
        "Recite with nothing shown from (stability, days)",
        1,
        21,
        1,
        "Fading cues: the support disappears as memory takes over.",
    ),
    _p(
        "by_heart.pass_ratio",
        "Recitation correct from (share of words in order)",
        0.8,
        1,
        0.01,
        "Word for word means nearly every word, in order.",
    ),
    _p(
        "by_heart.near_miss_ratio",
        "Recitation near miss from",
        0.6,
        0.98,
        0.01,
        "Close enough to come back soon, not from scratch.",
    ),
    _p("concentration.prior_weight", "Age default worth (sessions)", 1, 30, 1, "A few odd days must not swing the profile."),
    _p(
        "concentration.attention_drop_points",
        "Focus ends at an accuracy drop of",
        0.05,
        0.4,
        0.05,
        "15 points below the session start is a clear dip.",
    ),
    _p(
        "concentration.latency_rise",
        "Focus ends at an answer-time rise of",
        0.1,
        1,
        0.05,
        "Slowing down by 40% is the other sign of fatigue.",
    ),
    _p(
        "concentration.chunk_success_target",
        "Chunk size holds from first-study success of",
        0.5,
        0.95,
        0.05,
        "Bigger chunks while 70% stick on first study; smaller below.",
    ),
    _p(
        "concentration.group_above_switch_cost",
        "Group mixed reviews by subject above switch cost",
        0,
        0.5,
        0.01,
        "Interleaving helps most learners; not one who loses 15 points per switch.",
    ),
)

_SPEC_BY_PATH = {spec.path: spec for spec in TUNING_SPEC}


def get_param(tuning: Tuning, path: str) -> float:
    group, key = path.split(".")
    return getattr(getattr(tuning, group), key)


def with_tuning(overrides: Mapping[str, Mapping[str, float]] | None = None, base: Tuning = DEFAULT_TUNING) -> Tuning:
    """Merge overrides onto ``base``, clamping every value into its allowed range.

    >>> with_tuning({"retention": {"base": 0.99}}).retention.base
    0.97
    """
    groups = {f.name: getattr(base, f.name) for f in fields(Tuning)}
    for group, values in (overrides or {}).items():
        for key, value in values.items():
            spec = _SPEC_BY_PATH.get(f"{group}.{key}")
            if spec is None:
                raise KeyError(f"Unknown parameter {group}.{key}")
            clamped = min(spec.max, max(spec.min, value))
            groups[group] = replace(groups[group], **{key: clamped})
    return Tuning(**groups)
