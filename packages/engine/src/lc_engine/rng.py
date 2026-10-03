"""Small seeded random generator, so simulations and tests are reproducible."""

from __future__ import annotations

import math
from collections.abc import Callable

Rng = Callable[[], float]

_MASK = 0xFFFFFFFF


def _imul(a: int, b: int) -> int:
    return (a * b) & _MASK


def seeded_rng(seed: int) -> Rng:
    """Mulberry32: uniform floats in [0, 1), the same sequence on every platform."""
    state = seed & _MASK

    def next_value() -> float:
        nonlocal state
        state = (state + 0x6D2B79F5) & _MASK
        t = state
        t = _imul(t ^ (t >> 15), t | 1)
        t ^= (t + _imul(t ^ (t >> 7), t | 61)) & _MASK
        return ((t ^ (t >> 14)) & _MASK) / 4_294_967_296

    return next_value


def _normal(rng: Rng) -> float:
    return math.sqrt(-2 * math.log(1 - rng())) * math.cos(2 * math.pi * rng())


def _gamma(shape: float, rng: Rng) -> float:
    """Marsaglia-Tsang gamma sampler, valid for shape >= 1."""
    d = shape - 1 / 3
    c = 1 / math.sqrt(9 * d)
    while True:
        while True:
            x = _normal(rng)
            v = 1 + c * x
            if v > 0:
                break
        v = v * v * v
        u = rng()
        if u < 1 - 0.0331 * x**4:
            return d * v
        if math.log(u) < 0.5 * x * x + d * (1 - v + math.log(v)):
            return d * v


def sample_beta(a: float, b: float, rng: Rng) -> float:
    """Draw from Beta(a, b), a and b >= 1."""
    x = _gamma(a, rng)
    y = _gamma(b, rng)
    return x / (x + y)
