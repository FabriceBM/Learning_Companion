"""Adaptive engine of the family learning companion.

Memory model (FSRS-6), retention policy, session planner, missions, knowledge
map and placement check, learning by heart, concentration profile, reminders.
Pure Python: it runs on the phone (offline) and on the server unchanged.
"""

from fsrs import Card, Rating, State

from .by_heart import (
    CUE_LEVELS,
    Box,
    Chunk,
    CueLevel,
    FigureLabel,
    Recitation,
    by_heart_units,
    chunk_text,
    compare_recitation,
    cue,
    cue_for,
    figure_units,
    recitation_attempt,
    recitation_words,
)
from .clock import add_days, days_between, start_of_day, to_utc
from .concentration import (
    Applied,
    ConcentrationProfile,
    LoggedAnswer,
    SessionLog,
    apply_concentration,
    default_concentration,
    estimate_concentration,
)
from .day import DayRules, DaySoFar, SessionGate, is_due, next_useful_time, session_gate
from .grading import LADDER_TOP, ProbeRef, grade_attempt, pick_probe, probe_level_for
from .knowledge_map import (
    KnowledgeMap,
    Notion,
    NotionStatus,
    PlacementCheck,
    PlacementResult,
    load_notions,
    notion_status,
)
from .memory import DEFAULT_WEIGHTS, MemoryModel, forgetting_curve, interval_days
from .missions import (
    MIXED_REVIEW,
    Mission,
    MissionProgress,
    Suggestion,
    by_heart_mission,
    mission_for_test,
    mission_progress,
    pushed_mission,
    suggest_missions,
    to_focus,
    topic_mission,
)
from .model import (
    PROBE_LEVELS,
    Attempt,
    Goal,
    Grade,
    ItemState,
    KnowledgeKind,
    KnowledgeUnit,
    Latency,
    LearnerProfile,
    ProbeLevel,
)
from .nudge import (
    DayRecord,
    NudgeContext,
    NudgeDecision,
    NudgeSettings,
    NudgeState,
    NudgeWindow,
    WindowStats,
    decide_nudge,
    record_nudge_outcome,
    reminder_text,
)
from .personalize import MIN_REVIEWS_TO_FIT, ReviewRecord, fit_weights
from .planner import Focus, PlannedItem, SessionPlan, plan_session
from .profiles import BANDS, AgeBand, BandDefaults, DailyLimits, age_band, defaults_for_age, within_limits
from .retention import DEFAULT_RETENTION, RetentionPolicy, next_goal, relax_for_load, target_retention
from .rng import Rng, sample_beta, seeded_rng
from .scheduler import AdaptiveScheduler
from .session import Ask, Done, SessionResult, SessionRunner, SessionStep
from .tuning import DEFAULT_TUNING, TUNING_SPEC, ParamSpec, Tuning, get_param, with_tuning

__all__ = [name for name in dir() if not name.startswith("_")]
