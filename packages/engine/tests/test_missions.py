import re

from engine_helpers import NOW, learner, studied, unit
from lc_engine import (
    MIXED_REVIEW,
    Goal,
    ItemState,
    KnowledgeMap,
    MemoryModel,
    Rating,
    add_days,
    mission_for_test,
    mission_progress,
    plan_session,
    pushed_mission,
    suggest_missions,
    to_focus,
    topic_mission,
    with_tuning,
)

memory = MemoryModel()
TEST = Goal("fractions-test", "Maths test", add_days(NOW, 4))


def world() -> list[ItemState]:
    """Fractions (two studied, one weak base, two new) plus plenty of due Spanish and History."""
    base = studied(unit("equivalent", title="Equivalent fractions", importance=3), [Rating.Hard], 1, 9)  # forgotten
    return [
        base,
        # Reviewed yesterday: not due yet, not secure either (extra practice in a mission).
        studied(
            unit("add-same", title="Add, same denominator", prerequisites=["equivalent"], goal_ids=[TEST.id]), [Rating.Good], 1, 1
        ),
        studied(
            unit("add-multiple", title="Add, multiple denominator", prerequisites=["equivalent"], goal_ids=[TEST.id]),
            [Rating.Good],
            1,
            3,
        ),
        ItemState(unit("subtract", title="Subtract fractions", prerequisites=["add-same"], goal_ids=[TEST.id])),
        ItemState(unit("compare", title="Compare fractions", prerequisites=["equivalent"], goal_ids=[TEST.id])),
        *(
            studied(unit(f"other{i}", subject="Spanish" if i % 2 else "History"), [Rating.Hard, Rating.Hard], 1, 6)
            for i in range(30)
        ),
    ]


def test_a_mission_session_stays_on_the_mission_other_reviews_wait():
    items = world()
    mission = mission_for_test(TEST, items)
    plan = plan_session(learner(session_minutes=10), items, [TEST], NOW, memory, focus=to_focus(mission))
    scope = {*mission.ku_ids, "equivalent"}
    assert all(i.ku_id in scope for i in plan.items), [i.ku_id for i in plan.items]
    assert plan.waiting > 0, "the other due reviews are counted as waiting"


def test_repairs_a_weak_prerequisite_first_then_builds_on_it():
    items = world()
    plan = plan_session(learner(), items, [TEST], NOW, memory, focus=to_focus(mission_for_test(TEST, items)))
    assert plan.items[0].ku_id == "equivalent"
    assert plan.items[0].kind == "repair"


def test_fills_a_mission_session_with_extra_practice_until_the_time_is_used():
    items = world()
    plan = plan_session(learner(session_minutes=10), items, [TEST], NOW, memory, focus=to_focus(mission_for_test(TEST, items)))
    assert any(i.kind == "practice" for i in plan.items)


def test_can_keep_a_few_at_risk_reviews_alive_when_focus_is_below_100_percent():
    items = world()
    plan = plan_session(
        learner(session_minutes=10),
        items,
        [TEST],
        NOW,
        memory,
        focus=to_focus(mission_for_test(TEST, items)),
        tuning=with_tuning({"mission": {"focus_share": 0.6}}),
    )
    assert any(i.ku_id.startswith("other") for i in plan.items)


def test_learns_a_notion_in_one_go_a_unit_can_follow_its_same_notion_prerequisite():
    def notion(uid: str, prerequisites=()):
        return unit(uid, notion_id="negatives", prerequisites=prerequisites)

    items = [ItemState(notion("neg/1")), ItemState(notion("neg/2", ["neg/1"])), ItemState(notion("neg/3", ["neg/1"]))]
    mission = topic_mission("neg", "Negative numbers", items, lambda i: True)
    focused = plan_session(learner(), items, [], NOW, memory, focus=to_focus(mission))
    mixed = plan_session(learner(), items, [], NOW, memory)
    assert [i.ku_id for i in focused.items] == ["neg/1", "neg/2", "neg/3"]
    assert [i.ku_id for i in mixed.items] == ["neg/1"], "outside a mission, dependents wait for a later session"


def test_a_notion_pushed_by_parents_becomes_a_mission_over_its_learning_path():
    french = KnowledgeMap.load("french-core")
    path = french.learning_path(["passe-simple"], lambda nid: nid in ("verb-groups", "present-indicative"))
    assert [n.id for n in path] == ["passe-simple"]
    items = [ItemState(unit(f"ps/{k}", subject="French", notion_id="passe-simple")) for k in (1, 2, 3)]
    mission = pushed_mission("passe-simple", "Passé simple", [n.id for n in path], items, "your parents")
    assert len(mission.ku_ids) == 3
    ranked = suggest_missions([MIXED_REVIEW, mission], items, memory, NOW)
    pushed = next(r for r in ranked if r.mission.kind == "pushed")
    assert "Pushed by your parents" in pushed.reason


def test_a_mixed_review_interleaves_everything_that_is_due():
    items = world()
    plan = plan_session(learner(), items, [TEST], NOW, memory, focus=to_focus(MIXED_REVIEW))
    assert plan.waiting == 0
    assert len({i.subject for i in plan.items}) > 1


def test_suggests_the_close_test_first_and_tracks_progress():
    items = world()
    spanish = topic_mission("spanish", "Spanish verbs", items, lambda i: i.ku.subject == "Spanish")
    ranked = suggest_missions([MIXED_REVIEW, spanish, mission_for_test(TEST, items)], items, memory, NOW)
    assert ranked[0].mission.kind == "test"
    assert re.search(r"In 4 days", ranked[0].reason)
    p = mission_progress(mission_for_test(TEST, items), items, memory, NOW)
    assert (p.total, p.started, p.complete) == (4, 2, False)
