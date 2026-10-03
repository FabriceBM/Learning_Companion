from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from companion.companion import Companion
from companion.store import Store

PARIS = ZoneInfo("Europe/Paris")


class Clock:
    def __init__(self, start: datetime) -> None:
        self.t = start

    def __call__(self) -> datetime:
        return self.t

    def advance(self, **delta) -> None:
        self.t += timedelta(**delta)


@pytest.fixture
def setup(tmp_path):
    clock = Clock(datetime(2026, 10, 5, 17, 0, tzinfo=PARIS))
    store = Store(tmp_path / "test.db")
    return clock, store, Companion(store, age=12, now=clock)


def play(run, clock, answer):
    """Answer every card with answer(prompt) until the session ends; returns the prompts seen."""
    seen = []
    while (prompt := run.next()) is not None:
        seen.append(prompt)
        clock.advance(seconds=20)
        run.answer(answer(prompt), latency_ms=5000, seconds=20)
    return seen


def perfect(prompt):
    if prompt.question:
        return prompt.question.answer
    return prompt.study_text or ""


def test_suggests_both_use_cases_and_a_mixed_review(setup):
    _, _, app = setup
    kinds = [s.mission.kind for s in app.suggestions()]
    assert {"by-heart", "pushed", "mixed"} <= set(kinds)


def test_by_heart_session_studies_then_recites_with_first_letters(setup):
    clock, store, app = setup
    run = app.start("by-heart:corbeau")
    prompts = play(run, clock, perfect)
    assert prompts, "a first session has something to learn"
    first = prompts[0]
    assert first.study_text.startswith("Maître Corbeau")
    assert first.cue_level == "first-letters" and first.cue_text.startswith("M_____ C______")
    assert run.done is not None
    assert store.review_count("child") == len({p.ku_id for p in prompts})


def test_the_review_log_survives_a_restart_and_rebuilds_memory(setup, tmp_path):
    clock, _, app = setup
    play(app.start("by-heart:corbeau"), clock, perfect)
    studied = set(app.cards)
    reopened = Companion(Store(tmp_path / "test.db"), age=12, now=clock)
    assert set(reopened.cards) == studied
    for ku_id in studied:
        assert reopened.cards[ku_id].stability == pytest.approx(app.cards[ku_id].stability)


def test_a_missed_recitation_shows_the_missing_words_and_comes_back(setup):
    _, _, app = setup
    run = app.start("by-heart:corbeau")
    prompt = run.next()
    feedback = run.answer("Maître Corbeau sur un arbre", latency_ms=8000, seconds=30)
    assert not feedback.correct
    assert "perché" in feedback.missing
    retries = [p for p in iter(run.next, None) if p.retry]
    assert retries and retries[0].ku_id == prompt.ku_id


def test_pushed_notion_practice_checks_accents_and_varies_questions(setup):
    _, _, app = setup
    run = app.start("pushed:passe-simple")
    prompt = run.next()
    assert prompt.question is not None
    no_accent = prompt.question.answer.replace("è", "e").replace("â", "a").replace("î", "i").replace("û", "u")
    feedback = run.answer(no_accent, latency_ms=4000, seconds=10)
    if no_accent != prompt.question.answer:
        assert feedback.near_miss and not feedback.correct
    asked = [prompt.question.id]
    while (p := run.next()) is not None:
        asked.append(p.question.id)
        run.answer(p.question.answer, latency_ms=4000, seconds=10)
    assert len(asked) == len(set(asked)) or len(asked) > 3


def test_a_break_between_sessions_and_a_daily_limit(setup):
    clock, store, app = setup
    store.set("sessions_per_day", "2")
    app = Companion(store, age=12, now=clock)
    assert app.gate().open
    play(app.start("by-heart:corbeau"), clock, perfect)
    gate = app.gate()
    assert not gate.open and "break" in gate.reason
    clock.advance(minutes=95)
    assert app.gate().open
    play(app.start("pushed:passe-simple"), clock, lambda p: p.question.answer if p.question else "")
    clock.advance(minutes=200)
    assert not app.gate().open, "two sessions is the family's limit today"


def test_a_session_cut_short_still_counts_for_the_day(setup):
    clock, store, app = setup
    run = app.start("by-heart:corbeau")
    run.next()
    run.answer("Maître Corbeau", latency_ms=5000, seconds=20)  # then the app is closed
    reopened = Companion(store, age=12, now=clock)
    assert reopened.sessions_today() == 1
    assert not reopened.gate().open, "the break starts from the last answer"


def test_second_look_later_the_same_day(setup):
    clock, _, app = setup
    play(app.start("by-heart:corbeau"), clock, lambda p: "")  # everything missed
    nxt = app.next_useful()
    assert nxt is not None and nxt.date() == clock.t.date(), "missed chunks come back today, after the break"
