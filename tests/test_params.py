"""Series lengths (the study's formula), Wald steps and guarantees (CSP-1, Dodge 1943): the numbers a user sees
before choosing a risk."""
from fractions import Fraction

import pytest

from tenure import params
from tenure.params import ALPHA, BETA, PRESETS, required_n, study_n, wald_steps


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


def test_study_n_matches_the_study_formula():
    assert [study_n(Fraction(1, d)) for d in (20, 50, 100, 200, 1000)] == [21, 52, 105, 210, 1052]
    assert study_n(0.02) == 52   # floats go through Fraction(str(bar))


@pytest.mark.parametrize("bad", [0, 1, -0.1, 1.5, Fraction(1), Fraction(0)])
def test_study_n_rejects_a_bar_outside_zero_one(bad):
    with pytest.raises(ValueError):
        study_n(bad)


def test_required_n_is_none_when_capped():
    assert required_n(PRESETS["balanced"], "high") is None
    assert required_n(PRESETS["balanced"], "low") == 52


def test_wald_steps_reach_t2_after_12_and_18_successes():
    for stakes, expected in (("low", 12), ("medium", 18)):
        a, s, ln_b = wald_steps(stakes)
        assert a > 0 and s < 0 and ln_b < 0
        k = next(k for k in range(1, 100) if k * s <= ln_b)
        assert k == expected
    assert (ALPHA, BETA) == (0.05, 0.05)


def test_worst_case_when_the_agent_changes_after_tenure():
    """An agent that errs only on unchecked actions once cleared: (1 - f) / (f i + 1) of its actions."""
    assert params.worst_case(54, 0.1) == pytest.approx(0.9 / 6.4)
    assert params.worst_case(54, 1.0) == 0.0


def test_presets():
    """Three recommendations; high stakes stay capped (always asked) unless the careful preset lets them be earned."""
    assert set(params.PRESETS) == {"careful", "balanced", "fast"}
    assert params.DEFAULT_PRESET == "balanced"
    assert params.PRESETS["balanced"] == {"low": 1 / 50, "medium": 1 / 100, "high": None}
    assert params.PRESETS["fast"] == {"low": 1 / 20, "medium": 1 / 50, "high": None}
    assert params.PRESETS["careful"] == {"low": 1 / 100, "medium": 1 / 200, "high": 1 / 1000}


def test_describe_shows_the_guarantee_for_the_study_n():
    table = params.describe("balanced")
    assert table["low"]["n"] == 52 and table["medium"]["n"] == 105
    assert table["low"]["aoql"] == params.aoql(52, 0.1)[0]
    assert table["low"]["worst_case"] == pytest.approx(params.worst_case(52, 0.1))
    assert table["high"]["capped"] and table["high"]["n"] is None and table["high"]["aoql"] is None


def test_the_old_tenure_number_is_gone():
    """Series lengths come from the study's formula only (``study_n``); the CSP-1 search for i is removed."""
    assert not hasattr(params, "tenure_number")


def test_describe_has_no_alias_keys():
    for level in params.describe("balanced").values():
        assert set(level) == {"risk", "capped", "n", "aoql", "worst_case"}
