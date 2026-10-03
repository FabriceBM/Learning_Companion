from dataclasses import fields

import pytest

from lc_engine import DEFAULT_TUNING, TUNING_SPEC, DailyLimits, Tuning, age_band, defaults_for_age, get_param, with_tuning


class TestAgeBands:
    def test_maps_children_10_to_13_onto_two_child_bands_and_parents_onto_the_adult_band(self):
        assert [age_band(a) for a in (10, 11, 12, 13, 40)] == ["child", "child", "young-teen", "young-teen", "adult"]

    def test_children_share_one_view_with_their_parents_parents_keep_their_own_learning_private(self):
        assert defaults_for_age(10).visibility == "family"
        assert defaults_for_age(13).visibility == "family"
        assert defaults_for_age(13).parental_consent
        assert defaults_for_age(40).visibility == "learner-only"

    def test_allows_up_to_five_sessions_of_up_to_15_minutes_for_a_child_and_no_more(self):
        from lc_engine import within_limits

        child = within_limits(
            11, DailyLimits(session_minutes=30, sessions_per_day=8, max_reminders_per_day=3, max_new_per_day=30)
        )
        assert child == DailyLimits(15, 5, 1, 10)
        parent = within_limits(40, DailyLimits(25, 3, 2, 12))
        assert parent == DailyLimits(25, 3, 2, 12)

    def test_never_allows_more_than_one_reminder_a_day_for_a_child(self):
        for age in range(10, 14):
            assert defaults_for_age(age).max_reminders_per_day == 1


class TestTuning:
    def test_documents_every_parameter_and_every_default_sits_inside_its_range(self):
        leaves = sorted(f"{g.name}.{k.name}" for g in fields(Tuning) for k in fields(getattr(DEFAULT_TUNING, g.name)))
        assert leaves == sorted(s.path for s in TUNING_SPEC)
        for spec in TUNING_SPEC:
            value = get_param(DEFAULT_TUNING, spec.path)
            assert spec.min <= value <= spec.max, f"{spec.path}={value} outside [{spec.min}, {spec.max}]"

    def test_merges_overrides_and_clamps_them_into_range(self):
        t = with_tuning({"retention": {"base": 0.99}, "session": {"stop_after_misses": 4}})
        assert t.retention.base == 0.97
        assert t.session.stop_after_misses == 4
        assert t.retention.test == DEFAULT_TUNING.retention.test
        assert DEFAULT_TUNING.retention.base == 0.9, "defaults are not mutated"

    def test_rejects_unknown_parameters(self):
        with pytest.raises(KeyError):
            with_tuning({"retention": {"nope": 1}})
