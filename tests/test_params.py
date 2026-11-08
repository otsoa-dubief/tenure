"""Clearance numbers and guarantees (CSP-1, Dodge 1943): the numbers a user sees before choosing a risk."""
import math

import pytest

from clearance import params


def _aoql_grid(i, spot, step=1e-5, top=0.5):
    """Average outgoing quality limit by brute force: the worst stationary error rate p over a dense grid."""
    best = 0.0
    p = step
    while p < top:
        u = (1 - p) ** i
        best = max(best, p * (1 - spot) * u / (spot + (1 - spot) * u))
        p += step
    return best


@pytest.mark.parametrize("i,spot", [(9, 0.1), (54, 0.1), (110, 0.1), (220, 0.05), (1100, 0.1)])
def test_aoql_matches_a_brute_force_search(i, spot):
    value, worst_p = params.aoql(i, spot)
    assert value == pytest.approx(_aoql_grid(i, spot), rel=1e-4)
    assert 0 < worst_p < 0.5


@pytest.mark.parametrize("risk,spot", [(0.05, 0.1), (0.02, 0.1), (0.01, 0.1), (0.005, 0.1), (0.001, 0.1),
                                       (0.02, 0.05), (0.02, 0.2)])
def test_clearance_number_is_the_smallest_that_keeps_the_risk(risk, spot):
    i = params.clearance_number(risk, spot)
    assert params.aoql(i, spot)[0] <= risk
    assert i == math.ceil(1 / risk) - 1 or params.aoql(i - 1, spot)[0] > risk


def test_clearance_numbers_shown_to_users():
    """With one spot check in ten, about 1.1 / risk approvals in a row: 54 for 1 in 50, 110 for 1 in 100."""
    assert [params.clearance_number(r, 0.1) for r in (0.02, 0.01, 0.005)] == [54, 110, 220]


def test_worst_case_when_the_agent_changes_after_clearance():
    """An agent that errs only on unchecked actions once cleared: (1 - f) / (f i + 1) of its actions."""
    assert params.worst_case(54, 0.1) == pytest.approx(0.9 / 6.4)
    assert params.worst_case(54, 1.0) == 0.0


@pytest.mark.parametrize("bad", [0, 1, -0.1, 1.5, float("nan")])
def test_risk_and_spot_rate_are_checked(bad):
    with pytest.raises(ValueError):
        params.clearance_number(bad, 0.1)
    with pytest.raises(ValueError):
        params.clearance_number(0.02, bad if bad != 1 else 0)


def test_presets():
    """Three recommendations; high stakes stay capped (always asked) unless the careful preset lets them be earned."""
    assert set(params.PRESETS) == {"careful", "balanced", "fast"}
    assert params.DEFAULT_PRESET == "balanced"
    assert params.PRESETS["balanced"] == {"low": 1 / 50, "medium": 1 / 100, "high": None}
    assert params.PRESETS["fast"] == {"low": 1 / 20, "medium": 1 / 50, "high": None}
    assert params.PRESETS["careful"] == {"low": 1 / 100, "medium": 1 / 200, "high": 1 / 1000}
    table = params.describe("balanced", 0.1)
    assert table["low"]["approvals"] == 54 and table["medium"]["approvals"] == 110
    assert table["high"]["capped"] and table["high"]["approvals"] is None
    assert table["low"]["guarantee"] <= 1 / 50 and table["low"]["worst_case"] == pytest.approx(params.worst_case(54, 0.1))
