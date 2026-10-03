from dataclasses import replace
from datetime import timedelta

from engine_helpers import at, learner
from lc_engine import LoggedAnswer, SessionLog, apply_concentration, default_concentration, estimate_concentration, seeded_rng


def sessions(span: float, switch_penalty: float) -> list[SessionLog]:
    """Synthetic sessions: accurate for ``span`` minutes, then sloppy; worse after a subject switch."""
    rng = seeded_rng(5)
    subjects = ["Maths", "Maths", "Spanish", "Spanish", "French"]
    logs = []
    for d in range(20):
        started_at = at(2026, 10, 1, 17) + timedelta(days=d)
        answers = []
        for i in range(30):
            minute = i / 2
            switched = i > 0 and subjects[i % 5] != subjects[(i - 1) % 5]
            p = (0.92 if minute < span else 0.6) - (switch_penalty if switched else 0)
            answers.append(
                LoggedAnswer(
                    at=started_at + timedelta(seconds=30 * i),
                    correct=rng() < p,
                    latency_ms=4000 if minute < span else 7000,
                    subject=subjects[i % 5],
                )
            )
        logs.append(SessionLog(started_at, answers))
    return logs


def test_starts_from_age_defaults():
    assert default_concentration(10).attention_span_minutes == 10
    assert default_concentration(40).chunk_words == 20


def test_learns_the_attention_span_and_switch_cost_from_sessions_pulled_toward_the_default():
    p = estimate_concentration(sessions(7, 0.3), default_concentration(12))
    assert 6 <= p.attention_span_minutes <= 9, f"span {p.attention_span_minutes}"
    assert p.switch_cost > 0.15, f"switch cost {p.switch_cost}"
    assert p.based_on_sessions == 20


def test_shapes_sessions_within_the_family_limits():
    p = replace(
        default_concentration(12), attention_span_minutes=8, switch_cost=0.25, recovery_minutes=120, frustration_after_misses=2
    )
    applied = apply_concentration(p, learner(session_minutes=12, min_gap_minutes=90))
    assert applied.learner.session_minutes == 8, "shorter than the family limit when focus fades sooner"
    assert applied.learner.min_gap_minutes == 120
    assert applied.tuning.session.ease_off_after_misses == 2
    assert not applied.interleave_mixed
    long = apply_concentration(replace(p, attention_span_minutes=30), learner(session_minutes=12))
    assert long.learner.session_minutes == 12, "never longer than the family limit"
