from engine_helpers import NOW, learner, studied, unit
from lc_engine import (
    DEFAULT_RETENTION,
    AdaptiveScheduler,
    Attempt,
    Goal,
    ItemState,
    MemoryModel,
    ProbeRef,
    Rating,
    add_days,
    days_between,
    grade_attempt,
    interval_days,
    pick_probe,
    probe_level_for,
    relax_for_load,
    target_retention,
)

LATENCY = learner().latency_ms


def attempt(**overrides) -> Attempt:
    return Attempt(**{"correct": True, "latency_ms": 5000, "level": "recall", **overrides})


class TestGradeAttempt:
    def test_wrong_answer_is_again(self):
        assert grade_attempt(attempt(correct=False), LATENCY) == Rating.Again

    def test_a_hint_or_a_near_miss_is_hard(self):
        assert grade_attempt(attempt(hints_used=1), LATENCY) == Rating.Hard
        assert grade_attempt(attempt(correct=False, near_miss=True), LATENCY) == Rating.Hard

    def test_slow_for_this_learner_is_hard(self):
        assert grade_attempt(attempt(latency_ms=12_000), LATENCY) == Rating.Hard

    def test_fast_and_sure_is_easy_except_when_picking_among_choices(self):
        assert grade_attempt(attempt(latency_ms=2000, confidence="sure"), LATENCY) == Rating.Easy
        assert grade_attempt(attempt(latency_ms=2000, confidence="sure", level="recognize"), LATENCY) == Rating.Good


def test_probe_level_climbs_the_ladder_as_memory_stabilises_capped_by_the_kind_of_knowledge():
    fragile = studied(unit("a", kind="concept"), [Rating.Good]).card
    solid = studied(unit("b", kind="concept"), [Rating.Good, Rating.Good, Rating.Good, Rating.Easy], 20).card
    assert probe_level_for("concept", None) == "recognize"
    assert probe_level_for("concept", fragile) == "recognize"
    assert probe_level_for("concept", solid) == "explain"
    assert probe_level_for("fact", solid) == "recall"


class TestTargetRetention:
    test = Goal("t1", "History test", add_days(NOW, 4))

    def test_aims_higher_in_the_week_before_a_test(self):
        assert target_retention(unit("a", goal_ids=["t1"]), [self.test], NOW) == DEFAULT_RETENTION.test

    def test_drops_one_off_material_to_maintenance_after_its_test(self):
        after = add_days(NOW, 10)
        assert target_retention(unit("a", goal_ids=["t1"], cumulative=False), [self.test], after) == DEFAULT_RETENTION.maintenance
        assert target_retention(unit("b", goal_ids=["t1"], cumulative=True), [self.test], after) == DEFAULT_RETENTION.base

    def test_relaxes_everyday_targets_under_sustained_overload_never_tests(self):
        relaxed = relax_for_load(DEFAULT_RETENTION, 1.8)
        assert relaxed.base < DEFAULT_RETENTION.base
        assert relaxed.base >= DEFAULT_RETENTION.maintenance
        assert relaxed.test == DEFAULT_RETENTION.test


class TestAdaptiveScheduler:
    def test_pulls_a_review_to_just_before_a_test_when_recall_would_be_too_low_on_the_day(self):
        ku = unit("tener", goal_ids=["quiz"])
        item = studied(ku, [Rating.Good, Rating.Good], 3, 5)
        free = AdaptiveScheduler(MemoryModel(fuzz=False)).record(item, NOW, Rating.Good)

        # A quiz three quarters of the way into the normal interval, outside the one-week test window.
        quiz = Goal("quiz", "Spanish quiz", add_days(NOW, 0.75 * days_between(NOW, free.due)))
        assert days_between(NOW, quiz.date) > DEFAULT_RETENTION.test_window_days
        assert MemoryModel().retrievability(free, quiz.date) < DEFAULT_RETENTION.test

        fitted = AdaptiveScheduler(MemoryModel(fuzz=False), [quiz]).record(item, NOW, Rating.Good)
        assert fitted.due < quiz.date, "the review now lands before the quiz"
        assert days_between(fitted.due, quiz.date) <= 2.5, "and close to it"

    def test_gives_a_fast_forgetter_shorter_intervals_than_a_strong_memory(self):
        weak = MemoryModel(
            [
                0.1,
                0.4,
                0.8,
                4,
                6.4133,
                0.8334,
                3.0194,
                0.001,
                1.4,
                0.1666,
                0.796,
                1.4835,
                0.0614,
                0.2629,
                1.6483,
                0.6014,
                1.8729,
                0.5425,
                0.0912,
                0.0658,
                0.1542,
            ]
        )
        strong = MemoryModel()

        def interval_after_three_goods(memory: MemoryModel) -> float:
            scheduler = AdaptiveScheduler(memory)
            item = ItemState(unit("x"))
            when = NOW
            for _ in range(3):
                item = ItemState(item.ku, scheduler.record(item, when, Rating.Good))
                when = item.card.due
            return interval_days(item.card)

        assert interval_after_three_goods(weak) < interval_after_three_goods(strong)


class TestPickProbe:
    probes = (
        ProbeRef("chanter-ils", "apply"),
        ProbeRef("finir-nous", "apply"),
        ProbeRef("etre-il", "apply"),
        ProbeRef("ending-er", "recognize"),
    )

    def test_cycles_through_varied_questions_least_recently_asked_first(self):
        asked = {"chanter-ils": 3, "finir-nous": 1}
        assert pick_probe(self.probes, "apply", asked).id == "etre-il"
        asked["etre-il"] = 5
        assert pick_probe(self.probes, "apply", asked).id == "finir-nous"

    def test_falls_back_to_an_easier_level_when_needed(self):
        assert pick_probe(self.probes, "recall", {}).id == "ending-er"
