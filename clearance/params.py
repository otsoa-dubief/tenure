# Copyright 2026 Otsoa Dubief
# SPDX-License-Identifier: Apache-2.0
"""How many approvals in a row before an action type is cleared, for the risk a user accepts.

clearance runs Dodge's continuous sampling plan CSP-1 (1943) on each action type: every action of the type asks the
owner until ``i`` actions in a row have been approved (the clearance number); after that, a random fraction ``f`` of
the type's actions still asks (spot checks), and one refusal sends the type back to asking every time.

Errors the owner catches never run: an asked action that is refused is blocked. The only errors that run without
approval are the unchecked ones once the type is cleared. Their long-run share of the type's actions is the
average outgoing quality (AOQ). For an agent whose error rate ``p`` is stable,

    AOQ(p) = p (1 - f) u / (f + (1 - f) u),  u = (1 - p)^i,

and its maximum over ``p`` is the AOQL, the guarantee shown to users. ``clearance_number`` picks the smallest ``i``
whose AOQL stays at or under the accepted risk. For an agent that changes after clearance and errs only where it is
not checked, the share is at most ``(1 - f) / (f i + 1)`` until the first caught error revokes the clearance.
"""
from __future__ import annotations

import math
from fractions import Fraction
from functools import lru_cache

# Recommendations shown by `/clearance setup`: accepted share of errors that run without approval, per stakes level.
# None = capped: the type always asks, whatever its record.
PRESETS = {
    "careful": {"low": 1 / 100, "medium": 1 / 200, "high": 1 / 1000},
    "balanced": {"low": 1 / 50, "medium": 1 / 100, "high": None},
    "fast": {"low": 1 / 20, "medium": 1 / 50, "high": None},
}
DEFAULT_PRESET = "balanced"
DEFAULT_SPOT = 0.1          # one cleared action in ten still asks
LEVELS = ("low", "medium", "high")


# Detection rate of the preregistered study; series length N = ceil(1 / (DETECTION * bar)) - 1.
DETECTION = Fraction(95, 100)
# Wald sequential test for the middle tier: (pb, pm) = (acceptable, unacceptable) error rate per stakes.
WALD = {"low": (0.10, 0.30), "medium": (0.05, 0.20)}
ALPHA = BETA = 0.05


def study_n(bar) -> int:
    """Series length: consecutive approvals needed for a bar (accepted share of unchecked errors), in exact fractions."""
    b = bar if isinstance(bar, Fraction) else Fraction(str(bar))
    if not 0 < b < 1:
        raise ValueError(f"bar must be between 0 and 1 (exclusive), got {bar!r}")
    return math.ceil(1 / (DETECTION * b)) - 1


def required_n(risks: dict, stakes: str):
    """Series length for a stakes level, or None when that level is capped (always asks)."""
    bar = risks.get(stakes)
    return None if bar is None else study_n(bar)


def wald_steps(stakes: str) -> tuple[float, float, float]:
    """(a, s, ln_b): a failure adds a, a success adds s (negative); the lower boundary is ln_b."""
    pb, pm = WALD[stakes]
    return math.log(pm / pb), math.log((1 - pm) / (1 - pb)), math.log(BETA / (1 - ALPHA))


def _check(risk: float, spot: float) -> None:
    if not (isinstance(risk, (int, float)) and 0 < risk < 1):
        raise ValueError(f"risk must be between 0 and 1 (exclusive), got {risk!r}")
    if not (isinstance(spot, (int, float)) and 0 < spot <= 1):
        raise ValueError(f"spot-check rate must be in (0, 1], got {spot!r}")


def aoq(p: float, i: int, spot: float) -> float:
    u = (1 - p) ** i
    return p * (1 - spot) * u / (spot + (1 - spot) * u)


@lru_cache(maxsize=4096)
def aoql(i: int, spot: float) -> tuple[float, float]:
    """(AOQL, the stable error rate that reaches it). AOQ is unimodal in p: golden-section search on (0, 1)."""
    if spot >= 1:
        return 0.0, 0.0
    lo, hi = 0.0, 1.0
    g = (math.sqrt(5) - 1) / 2
    a, b = hi - g * (hi - lo), lo + g * (hi - lo)
    fa, fb = aoq(a, i, spot), aoq(b, i, spot)
    for _ in range(200):
        if fa < fb:
            lo, a, fa = a, b, fb
            b = lo + g * (hi - lo)
            fb = aoq(b, i, spot)
        else:
            hi, b, fb = b, a, fa
            a = hi - g * (hi - lo)
            fa = aoq(a, i, spot)
    p = (lo + hi) / 2
    return aoq(p, i, spot), p


@lru_cache(maxsize=1024)
def clearance_number(risk: float, spot: float = DEFAULT_SPOT) -> int:
    """Smallest i, from ceil(1 / risk) - 1 up, whose AOQL is at most ``risk``."""
    _check(risk, spot)
    i = max(1, math.ceil(1 / risk) - 1)
    while aoql(i, spot)[0] > risk:
        i += 1
    return i


def worst_case(i: int, spot: float) -> float:
    """Share of errors that run unchecked for an agent that turns bad once cleared, until its first caught error."""
    return (1 - spot) / (spot * i + 1)


def describe(preset_or_risks, spot: float = DEFAULT_SPOT) -> dict:
    """Per stakes level: accepted risk, series length N, guarantee (aoql) and worst case for that N, or capped.

    ``approvals`` and ``guarantee`` are kept as aliases of ``n`` and ``aoql`` for current callers.
    """
    risks = PRESETS[preset_or_risks] if isinstance(preset_or_risks, str) else dict(preset_or_risks)
    out = {}
    for level in LEVELS:
        n = required_n(risks, level)
        if n is None:
            out[level] = dict(risk=None, capped=True, n=None, aoql=None, worst_case=None,
                              approvals=None, guarantee=None)
            continue
        g = aoql(n, spot)[0]
        out[level] = dict(risk=risks[level], capped=False, n=n, aoql=g, worst_case=worst_case(n, spot),
                          approvals=n, guarantee=g)
    return out
