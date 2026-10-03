"""Fit the memory model to one learner's own history.

The review log is the source of truth; memory states are derived from it. The
optimizer is fsrs-rs (the one Anki uses), through its Python binding: install
the ``fit`` extra (``lc-engine[fit]``). It runs on the server, weekly.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from fsrs import Rating

from .clock import days_between, local, round_half_up, start_of_day
from .tuning import DEFAULT_TUNING

MIN_REVIEWS_TO_FIT = DEFAULT_TUNING.memory.min_reviews_to_fit
"""Below this, population (or family) defaults predict better than a fit."""


@dataclass(frozen=True)
class ReviewRecord:
    """One graded answer."""

    ku_id: str
    at: datetime
    grade: Rating


def fit_weights(
    log: Sequence[ReviewRecord],
    min_reviews: int | None = None,
    same_day_reviews: bool = False,
) -> list[float] | None:
    """FSRS-6 weights (21 numbers) fitted to one learner's review log, or None
    while the log is too short. ``same_day_reviews``: True when the learner has
    several sessions a day."""
    if len(log) < (min_reviews if min_reviews is not None else MIN_REVIEWS_TO_FIT):
        return None
    try:
        from fsrs_rs_python import DEFAULT_PARAMETERS, FSRS, FSRSItem, FSRSReview
    except ImportError as error:  # pragma: no cover - depends on the install
        raise RuntimeError("Personal fitting needs the optimizer: pip install 'lc-engine[fit]'") from error

    by_unit: dict[str, list[ReviewRecord]] = {}
    for r in log:
        by_unit.setdefault(r.ku_id, []).append(r)

    # One training item per review: the unit's history up to and including it.
    items = []
    for reviews in by_unit.values():
        reviews.sort(key=lambda r: r.at)
        history = []
        previous: datetime | None = None
        for r in reviews:
            if previous is None:
                delta = 0
            else:
                delta = max(0, round_half_up(days_between(start_of_day(previous), start_of_day(local(r.at, previous)))))
            history.append(FSRSReview(int(r.grade), delta))
            previous = r.at
            if len(history) >= 2:
                items.append(FSRSItem(list(history)))

    return list(FSRS(DEFAULT_PARAMETERS).compute_parameters(items, enable_short_term=same_day_reviews))
