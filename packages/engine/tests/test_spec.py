"""The language-neutral spec: JSON cases in packages/engine/spec/.

Each case is an input and the expected output, recorded from the first
(TypeScript) engine before it was retired. Any implementation of the engine, in
any language, must pass them: they are the contract that lets a later Rust core
(or anything else) replace a module one at a time.

Times in the spec are UTC instants; the family's zone is Europe/Paris.
"""

from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fsrs import Card, State

import lc_engine as E

SPEC = Path(__file__).resolve().parents[1] / "spec"
PARIS = ZoneInfo("Europe/Paris")


def load(name: str) -> dict[str, Any]:
    return json.loads((SPEC / f"{name}.json").read_text(encoding="utf-8"))


def when(iso: str | None) -> datetime | None:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(PARIS) if iso else None


def close(actual: float, expected: float) -> bool:
    # ts-fsrs rounded recall to 8 decimals; py-fsrs keeps full precision.
    return math.isclose(actual, expected, rel_tol=1e-7, abs_tol=1e-7)


def card(snapshot: dict[str, Any] | None) -> Card | None:
    if snapshot is None:
        return None
    state = State(snapshot["state"])
    return Card(
        card_id=0,
        state=state,
        step=0 if state in (State.Learning, State.Relearning) else None,
        stability=snapshot["stability"],
        difficulty=snapshot["difficulty"],
        due=when(snapshot["due"]),
        last_review=when(snapshot["last_review"]),
    )


def ku(d: dict[str, Any]) -> E.KnowledgeUnit:
    return E.KnowledgeUnit(**d)


def items(rows: list[dict[str, Any]]) -> list[E.ItemState]:
    return [E.ItemState(ku(r["ku"]), card(r["card"])) for r in rows]


def learner(d: dict[str, Any]) -> E.LearnerProfile:
    return E.LearnerProfile(**{**d, "latency_ms": E.Latency(**d["latency_ms"])})


def goal(d: dict[str, Any]) -> E.Goal:
    return E.Goal(d["id"], d["title"], when(d["date"]))


def cases(name: str, key: str) -> list[Any]:
    rows = load(name)[key]
    return pytest.mark.parametrize("case", rows, ids=[str(i) for i in range(len(rows))])


# ---------------------------------------------------------------- rng


@cases("rng", "seeded")
def test_seeded_rng(case):
    rng = E.seeded_rng(case["seed"])
    assert [rng() for _ in case["values"]] == case["values"]


@cases("rng", "beta")
def test_sample_beta(case):
    rng = E.seeded_rng(case["seed"])
    for expected in case["values"]:
        assert close(E.sample_beta(case["a"], case["b"], rng), expected)


# ---------------------------------------------------------------- tuning


def test_tuning_defaults_and_ranges():
    spec = load("tuning")
    assert {p: E.get_param(E.DEFAULT_TUNING, p) for p in spec["defaults"]} == spec["defaults"]
    assert [(s.path, s.min, s.max, s.step) for s in E.TUNING_SPEC] == [
        (s["path"], s["min"], s["max"], s["step"]) for s in spec["spec"]
    ]


@cases("tuning", "with_tuning")
def test_with_tuning(case):
    tuned = E.with_tuning(case["overrides"])
    assert {p: E.get_param(tuned, p) for p in case["expect"]} == case["expect"]


@cases("tuning", "unknown")
def test_with_tuning_rejects_unknown(case):
    with pytest.raises(KeyError):
        E.with_tuning(case)


# ---------------------------------------------------------------- profiles


@cases("profiles", "age_band")
def test_age_band(case):
    assert E.age_band(case["age"]) == case["expect"]


@cases("profiles", "defaults_for_age")
def test_defaults_for_age(case):
    d = E.defaults_for_age(case["age"])
    expect = case["expect"]
    assert (d.band, d.session_minutes, list(d.session_range), d.sessions_per_day, list(d.sessions_per_day_range)) == (
        expect["band"],
        expect["session_minutes"],
        expect["session_range"],
        expect["sessions_per_day"],
        expect["sessions_per_day_range"],
    )
    assert (
        d.min_gap_minutes,
        d.max_new_per_day,
        d.max_reminders_per_day,
        list(d.answer_modes),
        d.visibility,
        d.parental_consent,
    ) == (
        expect["min_gap_minutes"],
        expect["max_new_per_day"],
        expect["max_reminders_per_day"],
        expect["answer_modes"],
        expect["visibility"],
        expect["parental_consent"],
    )


@cases("profiles", "within_limits")
def test_within_limits(case):
    got = E.within_limits(case["age"], E.DailyLimits(**case["chosen"]))
    assert got == E.DailyLimits(**case["expect"])


# ---------------------------------------------------------------- day


@cases("day", "session_gate")
def test_session_gate(case):
    today = E.DaySoFar(case["today"]["sessions_done"], when(case["today"].get("last_ended_at")))
    gate = E.session_gate(when(case["now"]), E.DayRules(**case["rules"]), today)
    assert gate.open == case["expect"]["open"]
    assert gate.next_at == when(case["expect"].get("next_at"))
    if not gate.open:
        assert gate.reason == case["expect"]["reason"]


@cases("day", "is_due")
def test_is_due(case):
    assert E.is_due(card(case["card"]), when(case["now"])) == case["expect"]


@cases("day", "next_useful_time")
def test_next_useful_time(case):
    assert E.next_useful_time(items(case["items"]), when(case["now"])) == when(case["expect"])


# ---------------------------------------------------------------- grading


@cases("grading", "grade_attempt")
def test_grade_attempt(case):
    a = case["attempt"]
    attempt = E.Attempt(
        correct=a["correct"],
        latency_ms=a["latency_ms"],
        level=a["level"],
        near_miss=a.get("near_miss", False),
        hints_used=a["hints_used"],
        confidence=a.get("confidence"),
    )
    assert E.grade_attempt(attempt, E.Latency(**case["latency_ms"])) == case["expect"]


@cases("grading", "probe_level_for")
def test_probe_level_for(case):
    stub = None if case["stability"] is None else Card(card_id=0, stability=case["stability"])
    assert E.probe_level_for(case["kind"], stub) == case["expect"]


@cases("grading", "pick_probe")
def test_pick_probe(case):
    probes = [E.ProbeRef(**p) for p in case["probes"]]
    picked = E.pick_probe(probes, case["level"], case["last_asked_at"])
    assert (picked.id if picked else None) == case["expect"]


# ---------------------------------------------------------------- retention


@cases("retention", "target_retention")
def test_target_retention(case):
    goals = [goal(g) for g in load("retention")["goals"]]
    assert E.target_retention(ku(case["ku"]), goals, when(case["now"])) == case["expect"]


@cases("retention", "relax_for_load")
def test_relax_for_load(case):
    relaxed = E.relax_for_load(E.DEFAULT_RETENTION, case["overload"])
    for key, value in case["expect"].items():
        assert close(getattr(relaxed, key), value), key


# ---------------------------------------------------------------- learning by heart


@cases("by_heart", "chunk_text")
def test_chunk_text(case):
    chunks = E.chunk_text(case["text"], case["chunk_words"])
    assert [(c.index, c.text, c.words) for c in chunks] == [(c["index"], c["text"], c["words"]) for c in case["expect"]]


@cases("by_heart", "cue")
def test_cue(case):
    assert E.cue(case["text"], case["level"]) == case["expect"]


@cases("by_heart", "cue_for")
def test_cue_for(case):
    stub = None if case["stability"] is None else Card(card_id=0, stability=case["stability"])
    assert E.cue_for(stub) == case["expect"]


def _unit_rows(units: list[E.KnowledgeUnit]) -> list[dict[str, Any]]:
    return [
        {
            "id": u.id,
            "subject": u.subject,
            "kind": u.kind,
            "title": u.title,
            "importance": u.importance,
            "prerequisites": list(u.prerequisites),
            "goal_ids": list(u.goal_ids),
            **({"notion_id": u.notion_id} if u.notion_id else {}),
            "cumulative": u.cumulative,
        }
        for u in units
    ]


@cases("by_heart", "by_heart_units")
def test_by_heart_units(case):
    chunks = E.chunk_text(case["text"], case["chunk_words"])
    units = E.by_heart_units(case["text_id"], case["title"], case["subject"], chunks, case["goal_ids"], case["notion_id"])
    assert _unit_rows(units) == case["expect"]


@cases("by_heart", "figure_units")
def test_figure_units(case):
    labels = [E.FigureLabel(lbl["id"], lbl["label"], E.Box(**lbl["box"])) for lbl in case["labels"]]
    assert _unit_rows(E.figure_units(case["figure_id"], case["title"], case["subject"], labels)) == case["expect"]


@cases("by_heart", "compare_recitation")
def test_compare_recitation(case):
    r = E.compare_recitation(case["expected"], case["given"], accents=case["accents"])
    assert close(r.ratio, case["expect"]["ratio"])
    assert r.missing == case["expect"]["missing"]


@cases("by_heart", "recitation_attempt")
def test_recitation_attempt(case):
    a = E.recitation_attempt(E.Recitation(case["ratio"], []), case["latency_ms"])
    assert (a.correct, a.near_miss, a.level, a.hints_used) == (
        case["expect"]["correct"],
        case["expect"]["near_miss"],
        case["expect"]["level"],
        case["expect"]["hints_used"],
    )


# ---------------------------------------------------------------- knowledge map


def test_map_structure():
    for name, rows in load("knowledge_map")["structure"].items():
        m = E.KnowledgeMap.load(name)
        for row in rows:
            assert sorted(m.ancestors(row["id"])) == row["ancestors"], row["id"]
            assert sorted(m.descendants(row["id"])) == row["descendants"], row["id"]
            assert m.depth(row["id"]) == row["depth"], row["id"]


@cases("knowledge_map", "learning_path")
def test_learning_path(case):
    m = E.KnowledgeMap.load(case["map"])
    known = set(case["known"])
    assert [n.id for n in m.learning_path(case["targets"], known.__contains__)] == case["expect"]


@cases("knowledge_map", "placement")
def test_placement(case):
    m = E.KnowledgeMap.load(case["map"]) if case["map"] else E.KnowledgeMap(E.Notion(**n) for n in case["notions"])
    check = E.PlacementCheck(m, case["scope"], case["max_questions"])
    truth = set(case["truth_known"])
    asked = []
    while (n := check.next()) is not None:
        asked.append(n.id)
        check.record(n.id, n.id in truth)
    result = check.result()
    expect = case["expect"]
    assert asked == expect["asked_ids"]
    assert (result.known, result.unknown, result.unsure, result.asked) == (
        expect["known"],
        expect["unknown"],
        expect["unsure"],
        expect["asked"],
    )


@cases("knowledge_map", "invalid")
def test_invalid_maps(case):
    with pytest.raises(ValueError):
        E.KnowledgeMap(E.Notion(**n) for n in case)


# ---------------------------------------------------------------- planner and session


def _planned_rows(plan_items: list[E.PlannedItem]) -> list[tuple[Any, ...]]:
    return [(i.ku_id, i.subject, i.title, i.kind, i.level, i.seconds, i.why) for i in plan_items]


def _expected_rows(rows: list[dict[str, Any]]) -> list[tuple[Any, ...]]:
    return [(i["ku_id"], i["subject"], i["title"], i["kind"], i["level"], i["seconds"], i["why"]) for i in rows]


@cases("planner", "scenarios")
def test_plan_session(case):
    focus = case.get("focus")
    plan = E.plan_session(
        learner(case["learner"]),
        items(case["items"]),
        [goal(g) for g in case["goals"]],
        when(case["now"]),
        E.MemoryModel(),
        tuning=E.with_tuning(case["tuning"]) if case.get("tuning") else None,
        new_today=case.get("new_today", 0),
        focus=E.Focus(focus["mission_id"], frozenset(focus["ku_ids"])) if focus else None,
        interleave_mixed=case.get("interleave_mixed", True),
    )
    expect = case["expect"]
    assert _planned_rows(plan.items) == _expected_rows(expect["items"])
    for got, row in zip(plan.items, expect["items"], strict=True):
        assert close(got.recall, row["recall"]), got.ku_id
    assert (plan.minutes, plan.deferred, plan.waiting, plan.subjects, plan.mission_id) == (
        expect["minutes"],
        expect["deferred"],
        expect["waiting"],
        expect["subjects"],
        expect.get("mission_id"),
    )


@cases("session", "runs")
def test_session_runner(case):
    rows = load("session")["plan"]
    plan = E.SessionPlan(
        items=[E.PlannedItem(**i) for i in rows["items"]],
        minutes=rows["minutes"],
        deferred=rows["deferred"],
        waiting=rows["waiting"],
        subjects=rows["subjects"],
    )
    rules = case.get("rules")
    runner = E.SessionRunner(
        plan, case["budget"], E.with_tuning({"session": rules}).session if rules else E.DEFAULT_TUNING.session
    )
    steps: list[dict[str, Any]] = []
    k = 0
    while True:
        if case.get("stop_after") == k:
            runner.stop()
        step = runner.next()
        if isinstance(step, E.Done):
            steps.append({"type": "done", "reason": step.reason})
            break
        steps.append({"type": "ask", "ku_id": step.item.ku_id, "retry": step.retry})
        correct = case["answers"][k % len(case["answers"])]
        runner.answer(step.item, E.Attempt(correct=correct, latency_ms=5000, level="recall"), case["seconds"], step.retry)
        k += 1
    assert steps == case["expect"]


# ---------------------------------------------------------------- missions


def _mission(d: dict[str, Any]) -> E.Mission:
    return E.Mission(
        id=d["id"],
        kind=d["kind"],
        title=d["title"],
        ku_ids=tuple(d["ku_ids"]),
        goal=goal(d["goal"]) if d.get("goal") else None,
        pushed_by=d.get("pushed_by"),
    )


@cases("missions", "sets")
def test_missions(case):
    missions = [_mission(m) for m in case["missions"]]
    xs = items(case["items"])
    now = when(case["now"])
    memory = E.MemoryModel()
    for mission, expect in zip(missions, case["progress"], strict=True):
        p = E.mission_progress(mission, xs, memory, now)
        assert (p.total, p.started, p.secure, p.complete) == (
            expect["total"],
            expect["started"],
            expect["secure"],
            expect["complete"],
        )
        assert close(p.readiness, expect["readiness"])
    ranked = E.suggest_missions(missions, xs, memory, now)
    assert [(s.mission.id, s.reason) for s in ranked] == [(s["mission_id"], s["reason"]) for s in case["expect"]]
    for s, expect in zip(ranked, case["expect"], strict=True):
        assert close(s.score, expect["score"]), s.mission.id


@cases("missions", "notion_status")
def test_notion_status(case):
    assert E.notion_status(items(case["units"]), E.MemoryModel(), when(case["now"])) == case["expect"]


# ---------------------------------------------------------------- reminders


def _settings(d: dict[str, Any]) -> E.NudgeSettings:
    return E.NudgeSettings(
        windows=[E.NudgeWindow(**w) for w in d["windows"]],
        max_per_day=d["max_per_day"],
        rest_days=d["rest_days"],
        intention=d.get("intention"),
    )


def _state(d: dict[str, Any]) -> E.NudgeState:
    return E.NudgeState(
        windows={k: E.WindowStats(**v) for k, v in d["windows"].items()},
        ignored_streak=d["ignored_streak"],
        days=[E.DayRecord(**r) for r in d["days"]],
    )


@cases("nudge", "decide")
def test_decide_nudge(case):
    ctx = case["ctx"]
    decision = E.decide_nudge(
        when(case["now"]),
        _settings(case["settings"]),
        _state(case["state"]),
        E.NudgeContext(
            session_done_today=ctx["session_done_today"],
            reminders_sent_today=ctx["reminders_sent_today"],
            plan_minutes=ctx["plan"]["minutes"],
            plan_subjects=ctx["plan"]["subjects"],
            rng=E.seeded_rng(case["seed"]),
        ),
    )
    expect = case["expect"]
    assert decision.send == expect["send"]
    if decision.send:
        assert (decision.window_id, decision.at, decision.text) == (expect["window_id"], when(expect["at"]), expect["text"])
    else:
        assert decision.reason == expect["reason"]


def test_record_nudge_outcome():
    state = E.NudgeState()
    for _ in range(12):
        state = E.record_nudge_outcome(state, "evening", True)
        state = E.record_nudge_outcome(state, "after-school", False)
    learned = load("nudge")["learned"]
    assert {k: (v.started, v.ignored) for k, v in state.windows.items()} == {
        k: (v["started"], v["ignored"]) for k, v in learned["windows"].items()
    }


@cases("nudge", "reminder_text")
def test_reminder_text(case):
    assert E.reminder_text(case["intention"], case["minutes"], case["subjects"]) == case["expect"]


# ---------------------------------------------------------------- concentration


def _profile(d: dict[str, Any]) -> E.ConcentrationProfile:
    return E.ConcentrationProfile(**{**d, "best_hours": tuple(d["best_hours"])})


@cases("concentration", "defaults")
def test_default_concentration(case):
    assert E.default_concentration(case["age"]) == _profile(case["expect"])


@cases("concentration", "estimate")
def test_estimate_concentration(case):
    logs = [
        E.SessionLog(
            when(s["started_at"]),
            [
                E.LoggedAnswer(when(a["at"]), a["correct"], a["latency_ms"], a["subject"], a.get("chunk_words"))
                for a in s["answers"]
            ],
        )
        for s in case["logs"]
    ]
    assert E.estimate_concentration(logs, _profile(case["prior"])) == _profile(case["expect"])


@cases("concentration", "apply")
def test_apply_concentration(case):
    applied = E.apply_concentration(_profile(case["profile"]), learner(case["learner"]))
    expect = case["expect"]
    assert (
        applied.learner.session_minutes,
        applied.learner.min_gap_minutes,
        applied.tuning.session.ease_off_after_misses,
        applied.tuning.session.stop_after_misses,
        applied.interleave_mixed,
        applied.chunk_words,
    ) == (
        expect["session_minutes"],
        expect["min_gap_minutes"],
        expect["ease_off_after_misses"],
        expect["stop_after_misses"],
        expect["interleave_mixed"],
        expect["chunk_words"],
    )
