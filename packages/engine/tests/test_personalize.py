import math

from engine_helpers import NOW
from lc_engine import Rating, ReviewRecord, add_days, fit_weights, seeded_rng


def test_waits_for_enough_history():
    assert fit_weights([ReviewRecord("a", NOW, Rating.Good)]) is None


def test_fits_21_fsrs6_weights_from_a_review_log():
    rng = seeded_rng(3)
    log = []
    for u in range(120):
        day = 0
        for gap in (0, 1, 3, 7, 15):
            day += gap
            log.append(ReviewRecord(f"u{u}", add_days(NOW, day), Rating.Again if rng() < 0.15 else Rating.Good))
    weights = fit_weights(log)
    assert weights is not None and len(weights) == 21
    assert all(math.isfinite(w) for w in weights)


def test_learns_that_a_fast_forgetter_forgets_fast():
    """A learner who misses half their first reviews gets a lower first-day stability than one who rarely does."""

    def history(miss_rate: float, seed: int) -> list[ReviewRecord]:
        rng = seeded_rng(seed)
        log = []
        for u in range(150):
            day = 0
            for gap in (0, 1, 3, 7):
                day += gap
                log.append(ReviewRecord(f"u{u}", add_days(NOW, day), Rating.Again if rng() < miss_rate else Rating.Good))
        return log

    forgetful = fit_weights(history(0.5, 1))
    steady = fit_weights(history(0.05, 2))
    assert forgetful[2] < steady[2], "initial stability after a first Good"
