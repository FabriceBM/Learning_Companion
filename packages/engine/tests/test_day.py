from engine_helpers import at, learner, unit
from lc_engine import (
    AdaptiveScheduler,
    DayRules,
    DaySoFar,
    ItemState,
    MemoryModel,
    Rating,
    next_useful_time,
    plan_session,
    session_gate,
)


def hm(h: int, m: int = 0):
    return at(2026, 10, 3, h, m)


RULES = DayRules(sessions_per_day=4, min_gap_minutes=90)


def test_opens_a_session_only_after_a_break_and_only_up_to_the_daily_number():
    assert session_gate(hm(9), RULES, DaySoFar(0)).open
    too_soon = session_gate(hm(10), RULES, DaySoFar(1, hm(9, 10)))
    assert not too_soon.open
    assert too_soon.next_at == hm(10, 40)
    assert session_gate(hm(11), RULES, DaySoFar(1, hm(9, 10))).open
    assert not session_gate(hm(20), RULES, DaySoFar(4, hm(17))).open


def test_brings_a_unit_missed_in_the_morning_back_for_a_second_look_later_the_same_day():
    memory = MemoryModel(same_day_gap_minutes=90)
    scheduler = AdaptiveScheduler(memory)
    ku = unit("tener", subject="Spanish")
    missed = ItemState(ku, scheduler.record(ItemState(ku), hm(9), Rating.Again))

    def plan(now):
        return plan_session(learner(sessions_per_day=4), [missed], [], now, memory)

    assert plan(hm(10)).items == [], "not before the break"
    assert next_useful_time([missed], hm(10)) == hm(10, 30)
    later = plan(hm(11))
    assert [i.ku_id for i in later.items] == ["tener"]
    assert "earlier today" in later.items[0].why


def test_shares_the_new_unit_quota_across_the_day():
    memory = MemoryModel()
    items = [ItemState(unit(f"n{i}")) for i in range(10)]
    first = plan_session(learner(max_new_per_day=6), items, [], hm(9), memory)
    later = plan_session(learner(max_new_per_day=6), items, [], hm(15), memory, new_today=4)
    assert sum(1 for i in first.items if i.kind == "new") == 6
    assert sum(1 for i in later.items if i.kind == "new") == 2
