"""The per-type rule: ask until i approvals in a row, then spot checks; one refusal revokes."""
import math
import random

import pytest

from clearance import params, rule


def state(stakes="low"):
    return rule.TypeState(key="file:write", stakes=stakes)


def approve_n(s, n, i):
    events = []
    for _ in range(n):
        events += rule.on_approval(s, i)
    return events


def test_a_new_type_asks():
    s = state()
    assert s.level == rule.ASK and rule.decide(s, 5, 0.1, random.Random(1)) == rule.ASK


def test_cleared_after_i_approvals_in_a_row():
    s = state()
    events = approve_n(s, 4, 5)
    assert s.level == rule.ASK and s.streak == 4 and not events
    events = rule.on_approval(s, 5)
    assert s.level == rule.CLEARED and [e["event"] for e in events] == ["cleared"]
    assert events[0]["approvals_in_a_row"] == 5


def test_spot_checks_once_cleared():
    s = state()
    approve_n(s, 5, 5)
    rng = random.Random(7)
    asked = sum(rule.decide(s, 5, 0.1, rng) == rule.SPOT for _ in range(20000))
    assert 0.09 < asked / 20000 < 0.11
    assert all(rule.decide(s, 5, 1.0, rng) == rule.SPOT for _ in range(10))


def test_refusal_while_asking_resets_the_streak():
    s = state("low")
    approve_n(s, 3, 5)
    rule.on_refusal(s, 5)
    assert s.streak == 0 and s.level == rule.ASK and not s.lengthened
    assert rule.required(s, 5) == 5


@pytest.mark.parametrize("stakes", ["medium", "high"])
def test_refusal_at_medium_or_high_stakes_lengthens_the_next_climb(stakes):
    s = state(stakes)
    rule.on_refusal(s, 8)
    assert s.lengthened and rule.required(s, 8) == math.ceil(1.25 * 8) == 10
    approve_n(s, 9, 8)
    assert s.level == rule.ASK
    rule.on_approval(s, 8)
    assert s.level == rule.CLEARED and not s.lengthened      # the lengthening does not carry over


def test_refused_spot_check_revokes():
    s = state("medium")
    approve_n(s, 5, 5)
    g = s.generation
    events = rule.on_refusal(s, 5)
    assert s.level == rule.ASK and s.streak == 0 and s.generation == g + 1 and s.lengthened
    assert [e["event"] for e in events] == ["revoked"] and events[0]["reason"] == "refused"


def test_low_stakes_revocation_is_not_lengthened():
    s = state("low")
    approve_n(s, 5, 5)
    rule.on_refusal(s, 5)
    assert s.level == rule.ASK and not s.lengthened


def test_flag_after_the_fact_revokes_like_a_refusal():
    s = state("medium")
    approve_n(s, 5, 5)
    events = rule.on_flag(s, 5, note="wrong recipient")
    assert s.level == rule.ASK and s.lengthened and events[0]["reason"] == "flagged"
    assert events[0]["note"] == "wrong recipient"


def test_streak_does_not_pile_up_beyond_what_is_required():
    s = state()
    approve_n(s, 50, 5)
    assert s.streak == 5


def test_manual_grant_clears_until_the_next_revocation():
    s = state()
    events = rule.on_approval(s, 5, manual=True)
    assert s.level == rule.CLEARED and s.manual and events[0]["event"] == "cleared" and events[0]["manual"]
    rule.on_refusal(s, 5)
    assert s.level == rule.ASK and not s.manual


def test_model_change_starts_over():
    s = state("high")
    rule.on_refusal(s, 5)
    approve_n(s, 7, 5)
    g = s.generation
    events = rule.on_model_change(s, old="model-a", new="model-b")
    assert (s.level, s.streak, s.lengthened, s.manual) == (rule.ASK, 0, False, False) and s.generation == g + 1
    assert events[0]["event"] == "reset" and events[0]["new_model"] == "model-b"


def test_neutral_answers_change_nothing():
    s = state()
    approve_n(s, 3, 5)
    assert rule.on_neutral(s, "timeout") == [] and s.streak == 3


def test_counters_for_display():
    s = state()
    approve_n(s, 5, 5)
    rule.on_refusal(s, 5)
    assert (s.approvals, s.refusals, s.revocations) == (5, 1, 1)


# --------------------------------------------------------------------------------------------------------------------
# The guarantee, by simulation through the rule itself
# --------------------------------------------------------------------------------------------------------------------
def _run(p, i, spot, n, seed):
    """A stable agent erring with probability p on each action; the owner catches every error it is asked about.
    Returns the share of the type's actions that were errors run without approval."""
    rng = random.Random(seed)
    s = state()
    escaped = 0
    for _ in range(n):
        error = rng.random() < p
        d = rule.decide(s, i, spot, rng)
        if d == rule.ALLOW:
            escaped += error
        elif error:
            rule.on_refusal(s, i)
        else:
            rule.on_approval(s, i)
    return escaped / n


def test_stable_agent_stays_under_the_accepted_risk():
    """Risk 1 in 50, one spot check in ten: i = 54; at the worst error rate, errors run unchecked about AOQL of the
    time (theory 2.0 %), and never much more."""
    risk, spot = 0.02, 0.1
    i = params.clearance_number(risk, spot)
    value, worst_p = params.aoql(i, spot)
    measured = _run(worst_p, i, spot, 400_000, seed=3)
    assert measured == pytest.approx(value, abs=0.002) and measured <= risk + 0.002


def test_a_reliable_agent_is_cleared_and_a_poor_one_is_not():
    i = params.clearance_number(0.02, 0.1)
    assert _run(0.0, i, 0.1, 10_000, seed=4) == 0.0
    poor = state()
    rng = random.Random(5)
    for _ in range(20_000):
        d = rule.decide(poor, i, 0.1, rng)
        (rule.on_refusal if rng.random() < 0.3 else rule.on_approval)(poor, i)
    assert poor.level == rule.ASK                   # 30 % errors: 54 approvals in a row essentially never happen
