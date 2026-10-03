from engine_helpers import NOW, learner, studied, unit
from lc_engine import Attempt, Done, ItemState, MemoryModel, Rating, SessionRunner, plan_session

memory = MemoryModel()
SUBJECTS = ["Maths", "Spanish", "History"]


def backlog() -> list[ItemState]:
    """60 units reviewed ~a week ago with short intervals, so they are all due."""
    return [studied(unit(f"u{i}", subject=SUBJECTS[i % 3]), [Rating.Hard, Rating.Hard], 1, 6) for i in range(60)]


class TestPlanSession:
    def test_never_exceeds_the_time_budget_and_reports_what_it_deferred(self):
        plan = plan_session(learner(session_minutes=5), backlog(), [], NOW, memory)
        assert sum(i.seconds for i in plan.items) <= 5 * 60
        assert plan.deferred > 0
        assert not [i for i in plan.items if i.kind == "new"], "no new material while reviews are deferred"

    def test_interleaves_subjects(self):
        plan = plan_session(learner(session_minutes=8), backlog(), [], NOW, memory)
        for i in range(2, len(plan.items)):
            run = [p.subject for p in plan.items[i - 2 : i + 1]]
            assert len(set(run)) > 1, f"three {run[0]} in a row at {i}"

    def test_opens_and_closes_on_units_the_learner_probably_knows(self):
        plan = plan_session(learner(session_minutes=8), backlog(), [], NOW, memory)
        recalls = sorted((i.recall for i in plan.items if i.kind == "review"), reverse=True)
        assert plan.items[0].recall == recalls[0]
        assert plan.items[-1].recall == recalls[1]

    def test_waits_for_prerequisites_before_introducing_a_unit(self):
        base = unit("fractions-equivalent")
        following = unit("fractions-add", prerequisites=["fractions-equivalent"])
        plan = plan_session(learner(), [ItemState(base), ItemState(following)], [], NOW, memory)
        assert [i.ku_id for i in plan.items] == ["fractions-equivalent"]

    def test_introduces_nothing_new_when_the_learner_is_struggling(self):
        items = [ItemState(unit(f"n{i}")) for i in range(5)]
        plan = plan_session(learner(recent_accuracy=0.6), items, [], NOW, memory)
        assert plan.items == []


class TestSessionRunner:
    wrong = Attempt(correct=False, latency_ms=6000, level="recall")

    def plan(self):
        return plan_session(learner(session_minutes=6), backlog(), [], NOW, memory)

    def test_ends_kindly_after_a_run_of_misses(self):
        runner = SessionRunner(self.plan(), 600)
        step = runner.next()
        while not isinstance(step, Done):
            runner.answer(step.item, self.wrong, 10, step.retry)
            step = runner.next()
        assert step.reason == "ease-off"
        assert len(runner.results) == 5

    def test_slips_in_the_easiest_remaining_unit_after_three_misses(self):
        plan = self.plan()
        runner = SessionRunner(plan, 600)
        for _ in range(3):
            step = runner.next()
            assert not isinstance(step, Done)
            runner.answer(step.item, self.wrong, 10, step.retry)
        asked = {r.item.ku_id for r in runner.results}
        easiest = max(i.recall for i in plan.items if i.ku_id not in asked)
        step = runner.next()
        assert not isinstance(step, Done) and step.item.recall == easiest

    def test_stops_when_the_time_budget_is_used_even_with_items_left(self):
        runner = SessionRunner(self.plan(), 30)
        step = runner.next()
        while not isinstance(step, Done):
            runner.answer(step.item, Attempt(correct=True, latency_ms=6000, level="recall"), 12, step.retry)
            step = runner.next()
        assert step.reason == "time-budget"
