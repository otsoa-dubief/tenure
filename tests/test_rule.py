"""Rule B of the study for one action type: tiers, the Wald middle tier, trials after faults, two sessions, and
carry-over on trial after a model change."""
import json
import math
import random

import pytest

from clearance import params, rule

LOW, MEDIUM, HIGH = 52, 105, 1052       # series lengths: balanced low and medium, careful high (params.required_n)


def state(stakes="low", reversible=False, key=None):
    key = key or ("file:write" if reversible else "shell:make")
    return rule.TypeState(key=key, stakes=stakes, reversible=reversible)


def succeed(s, k, n, sessions=("a", "b"), source="approval"):
    """k verified successes, cycling through the given sessions; returns the events."""
    events = []
    for j in range(k):
        events += rule.on_success(s, n, session=sessions[j % len(sessions)], source=source)
    return events


def fault(s, n, source="refusal"):
    return rule.on_fault(s, n, session="a", source=source)


def kinds(events):
    return [e["event"] for e in events]


def moves(events):
    return [(e["event"], e.get("from"), e.get("to"), e.get("reason")) for e in events]


def climbed(stakes="low", reversible=False, n=LOW):
    """A type at T3: n successes from two sessions, and enough more for the Wald score to sit at its floor."""
    s = state(stakes, reversible)
    succeed(s, n + 30, n)
    assert s.tier == rule.T3
    return s


class Rng:
    """Hands out the given draws in order; any extra draw fails the test."""

    def __init__(self, *draws):
        self.draws = list(draws)

    def random(self):
        return self.draws.pop(0)


# --------------------------------------------------------------------------------------------------------------------
# The climb
# --------------------------------------------------------------------------------------------------------------------
def test_t3_after_n_successes_from_two_sessions():
    s = state("low")
    for _ in range(52):
        rule.on_success(s, 52, session="a", source="approval")
    assert s.tier == rule.T1 and s.series == 52 and s.sessions == ["a"]
    events = rule.on_success(s, 52, session="b", source="approval")
    assert s.tier == rule.T3 and sorted(s.sessions) == ["a", "b"]
    assert moves(events) == [("tier", rule.T1, rule.T3, "series")]
    assert events[0]["required"] == 52 and events[0]["sessions"] == 2


def test_series_capped_at_required():
    s = state("medium")
    for j in range(300):
        rule.on_success(s, MEDIUM, session="ab"[j % 2], source="approval")
        assert s.series <= rule.required(s, MEDIUM)
    assert s.series == MEDIUM and s.tier == rule.T3
    # The climb after a medium fault is capped at ceil(1.25 N), and the series goes back under N at T3.
    fault(s, MEDIUM)
    succeed(s, 3, MEDIUM)                                       # the trial
    for _ in range(200):
        rule.on_success(s, MEDIUM, session="a", source="approval")
        assert s.series <= rule.required(s, MEDIUM)
    assert s.series == 132 and s.tier == rule.T1 and s.lengthened
    rule.on_success(s, MEDIUM, session="b", source="approval")
    assert s.tier == rule.T3 and s.series == MEDIUM == rule.required(s, MEDIUM) and not s.lengthened
    succeed(s, 50, MEDIUM)
    assert s.series == MEDIUM


def test_reversible_low_reaches_t2_after_12_successes():
    s = state("low", reversible=True)
    assert succeed(s, 11, LOW) == [] and s.tier == rule.T1
    events = succeed(s, 1, LOW)
    assert s.tier == rule.T2 and moves(events) == [("tier", rule.T1, rule.T2, "wald")]
    m = state("medium", reversible=True)                        # 18 at medium stakes
    succeed(m, 17, MEDIUM)
    assert m.tier == rule.T1
    succeed(m, 1, MEDIUM)
    assert m.tier == rule.T2
    other = state("low", reversible=False)                      # irreversible: no middle tier
    succeed(other, 12, LOW)
    assert other.tier == rule.T1 and other.wald == 0.0
    succeed(other, 39, LOW)                                     # 51: one short of T3
    assert other.tier == rule.T1


def test_wald_floor():
    for stakes, n in (("low", LOW), ("medium", MEDIUM)):
        s = state(stakes, reversible=True)
        succeed(s, 100, n)
        a, _, ln_b = params.wald_steps(stakes)
        assert s.wald == pytest.approx(ln_b - a)


# --------------------------------------------------------------------------------------------------------------------
# The descent
# --------------------------------------------------------------------------------------------------------------------
def test_low_fault_at_t3_reversible_goes_to_t2_then_wald_decides():
    s = climbed("low", reversible=True)
    a, _, ln_b = params.wald_steps("low")
    assert s.wald == pytest.approx(ln_b - a)
    events = fault(s, LOW)
    assert s.tier == rule.T2 and moves(events) == [("tier", rule.T3, rule.T2, "fault")]
    assert s.wald == pytest.approx(ln_b) and s.trial_left == 0 and not s.lengthened
    fault(s, LOW)
    assert s.tier == rule.T1
    # At T2, the score decides: one low fault at the floor is absorbed (score = ln B, within the tolerance).
    t2 = state("low", reversible=True)
    succeed(t2, 30, LOW, sessions=("a",))
    assert t2.tier == rule.T2 and t2.wald == pytest.approx(ln_b - a)
    assert fault(t2, LOW) == [] and t2.tier == rule.T2
    # From T3 the fall is one tier even when the score is above ln B (a short series after faults: fast preset, 21).
    short = state("low", reversible=True)
    for _ in range(3):
        fault(short, 21)
    succeed(short, 21, 21)
    assert short.tier == rule.T3 and short.wald > ln_b
    fault(short, 21)
    assert short.tier == rule.T2
    fault(short, 21)
    assert short.tier == rule.T1


def test_low_fault_at_t3_irreversible_goes_to_t1():
    s = climbed("low", reversible=False)
    events = fault(s, LOW)
    assert s.tier == rule.T1 and moves(events) == [("tier", rule.T3, rule.T1, "fault")]
    assert s.trial_left == 0 and not s.lengthened and not s.unresolved_fault


@pytest.mark.parametrize("reversible,k,start", [(True, 5, "T1"), (True, 20, "T2"), (True, 110, "T3"),
                                                (False, 110, "T3")])
def test_medium_fault_opens_trial_and_lengthens(reversible, k, start):
    s = state("medium", reversible)
    succeed(s, k, MEDIUM)
    assert s.tier == getattr(rule, start)
    events = fault(s, MEDIUM)
    assert s.tier == rule.T1 and s.trial_left == 3 and s.lengthened and s.unresolved_fault
    assert ("trial", "none", "open", "fault") in moves(events)
    assert rule.required(s, MEDIUM) == math.ceil(1.25 * MEDIUM) == 132
    succeed(s, 3, MEDIUM)                                       # the trial passes
    assert s.trial_left == 0 and not s.unresolved_fault
    succeed(s, 131, MEDIUM)
    assert s.tier != rule.T3
    succeed(s, 1, MEDIUM)
    assert s.tier == rule.T3 and not s.lengthened and rule.required(s, MEDIUM) == MEDIUM


def test_series_frozen_during_trial_and_wait():
    s = state("medium", reversible=True)
    succeed(s, 10, MEDIUM)
    fault(s, MEDIUM)
    assert (s.trial_left, s.series, s.sessions) == (3, 0, [])
    frozen = (s.series, list(s.sessions), s.wald, s.tier)
    assert succeed(s, 2, MEDIUM, sessions=("c", "d")) == []
    assert s.trial_left == 1 and (s.series, s.sessions, s.wald, s.tier) == frozen and s.successes == 12
    events = succeed(s, 1, MEDIUM)
    assert moves(events) == [("trial", "open", "none", "passed")]
    assert s.trial_left == 0 and not s.unresolved_fault and (s.series, s.sessions, s.wald) == frozen[:3]
    # A new fault opens a new trial; a fault during the trial fails it.
    fault(s, MEDIUM)
    assert s.trial_left == 3
    succeed(s, 1, MEDIUM)
    events = fault(s, MEDIUM)
    assert (s.trial_left, s.trial_wait) == (0, 50) and s.unresolved_fault
    assert ("trial", "open", "wait", "failed") in moves(events)
    # The wait: successes count in the statistics only, then the 50th counted action reopens the trial.
    frozen = (s.series, list(s.sessions), s.wald, s.tier)
    for i in range(49):
        assert succeed(s, 1, MEDIUM, sessions=("c",)) == []
        assert rule.count_action(s) == []
        if i == 19:                                             # a fault during the wait leaves the wait as it is
            assert fault(s, MEDIUM) == [] and (s.trial_left, s.trial_wait, s.faults) == (0, 30, 4)
            frozen = (s.series, list(s.sessions), s.wald, s.tier)
    assert (s.trial_left, s.trial_wait) == (0, 1) and (s.series, s.sessions, s.wald, s.tier) == frozen
    events = rule.count_action(s)
    assert (s.trial_left, s.trial_wait) == (3, 0)
    assert moves(events) == [("trial", "wait", "open", "wait over")]
    assert rule.count_action(s) == [] and s.trial_left == 3     # only the wait is counted


@pytest.mark.parametrize("stakes,reversible,n", [("low", False, LOW), ("low", True, LOW), ("medium", False, MEDIUM),
                                                 ("medium", True, MEDIUM), ("high", False, HIGH)])
def test_any_fault_resets_series_and_sessions(stakes, reversible, n):
    s = state(stakes, reversible)
    succeed(s, 30, n)
    assert s.series == 30 and sorted(s.sessions) == ["a", "b"]
    fault(s, n)
    assert s.series == 0 and s.sessions == []


# --------------------------------------------------------------------------------------------------------------------
# The decision
# --------------------------------------------------------------------------------------------------------------------
def test_decide(monkeypatch):
    monkeypatch.setattr(random, "random", lambda: pytest.fail("decide used the global random"))
    t1 = state("low", reversible=True)
    t2 = state("low", reversible=True)
    succeed(t2, 12, LOW)
    t3 = climbed("low", reversible=True)
    assert (t1.tier, t2.tier, t3.tier) == (rule.T1, rule.T2, rule.T3)
    # Capped: always asks.
    assert rule.decide(t3, None, 0.1, suspended=False, rng=Rng()) == rule.ASK
    # Suspended: asks at every tier.
    for s in (t1, t2, t3):
        assert rule.decide(s, LOW, 0.1, suspended=True, rng=Rng()) == rule.ASK
    # By tier.
    assert rule.decide(t1, LOW, 0.1, suspended=False, rng=Rng()) == rule.ASK
    assert rule.decide(t2, LOW, 0.1, suspended=False, rng=Rng()) == rule.NOTIFY
    assert rule.decide(t3, LOW, 0.1, suspended=False, rng=Rng(0.05)) == rule.SPOT
    assert rule.decide(t3, LOW, 0.1, suspended=False, rng=Rng(0.1)) == rule.ALLOW
    assert rule.decide(t3, LOW, 0.1, suspended=False, rng=Rng(0.5)) == rule.ALLOW
    # An open trial, then the wait after a failed trial: asks.
    m = climbed("medium", reversible=True, n=MEDIUM)
    fault(m, MEDIUM)
    assert m.trial_left == 3 and rule.decide(m, MEDIUM, 0.1, suspended=False, rng=Rng()) == rule.ASK
    succeed(m, 1, MEDIUM)
    fault(m, MEDIUM)
    assert m.trial_wait == 50 and rule.decide(m, MEDIUM, 0.1, suspended=False, rng=Rng()) == rule.ASK
    for tier in (rule.T2, rule.T3):                             # whatever the stored tier
        for pending in ({"trial_left": 2}, {"trial_wait": 7}):
            s = rule.TypeState("file:write", "low", reversible=True, tier=tier, series=LOW, **pending)
            assert rule.decide(s, LOW, 0.1, suspended=False, rng=Rng()) == rule.ASK


# --------------------------------------------------------------------------------------------------------------------
# A model change: carry-over on trial
# --------------------------------------------------------------------------------------------------------------------
def test_carry_over_takes_half_and_marks_it_provisional():
    old = climbed("low", reversible=True)
    a, _, ln_b = params.wald_steps("low")
    assert old.series == 52 and old.wald == pytest.approx(ln_b - a)
    new = rule.carry_over(old, n_new=LOW, veto=False, strict=False)
    assert new is not old and (new.key, new.stakes, new.reversible) == (old.key, old.stakes, old.reversible)
    assert (new.series, new.provisional, new.sessions, new.tier) == (26, 26, [], rule.T1)
    assert new.wald == old.wald / 2
    assert (new.successes, new.faults, new.neutrals, new.spot_checks) == (0, 0, 0, 0)    # the new agent's own
    assert (new.trial_left, new.trial_wait, new.lengthened, new.unresolved_fault) == (0, 0, False, False)
    assert old.series == 52 and old.tier == rule.T3                                         # untouched
    succeed(new, 3, LOW)
    assert new.tier == rule.T1
    succeed(new, 1, LOW)
    assert new.tier == rule.T2
    # Half, capped at the new series length (here the fast preset's 21); still no T3 before two new sessions.
    fast = rule.carry_over(old, n_new=21, veto=False, strict=False)
    assert (fast.series, fast.provisional, fast.tier) == (21, 21, rule.T1)
    succeed(fast, 1, 21, sessions=("c",))
    assert fast.tier == rule.T1
    succeed(fast, 1, 21, sessions=("d",))
    assert fast.tier == rule.T3 and fast.provisional == 21


def fresh(new, old):
    return ((new.key, new.stakes, new.reversible) == (old.key, old.stakes, old.reversible) and new.tier == rule.T1
            and (new.series, new.sessions, new.wald, new.provisional) == (0, [], 0.0, 0)
            and (new.lengthened, new.trial_wait) == (False, 0)
            and (new.successes, new.faults, new.neutrals, new.spot_checks) == (0, 0, 0, 0))


def test_carry_over_never_for_high_vetoed_or_strict():
    low = climbed("low", reversible=True)
    high = climbed("high", n=HIGH)
    for old, n_new, veto, strict in [(high, HIGH, False, False), (low, LOW, True, False), (low, LOW, False, True),
                                     (low, None, False, False)]:                         # last: capped now
        new = rule.carry_over(old, n_new=n_new, veto=veto, strict=strict)
        assert fresh(new, old) and new.trial_left == 0 and not new.unresolved_fault     # a clean record owes nothing
    # Strict mode is the study: every medium or high fault on the old record becomes a trial, even a passed one.
    m = state("medium", reversible=True)
    succeed(m, 10, MEDIUM)
    fault(m, MEDIUM)
    succeed(m, 3 + 40, MEDIUM)                                  # trial passed, climbing again
    assert m.faults == 1 and not m.unresolved_fault and m.series == 40
    new = rule.carry_over(m, n_new=MEDIUM, veto=False, strict=True)
    assert fresh(new, m) and (new.trial_left, new.unresolved_fault) == (3, True)
    assert rule.carry_over(m, n_new=MEDIUM, veto=True, strict=False).trial_left == 0
    # Low faults never become trials.
    lo = state("low")
    succeed(lo, 5, LOW)
    fault(lo, LOW)
    assert rule.carry_over(lo, n_new=LOW, veto=False, strict=True).trial_left == 0
    # A fault whose trial is not passed yet (open, or waiting after a failure) is never escaped by a model change.
    open_trial = state("medium", reversible=True)
    fault(open_trial, MEDIUM)
    waiting = state("medium")
    fault(waiting, MEDIUM)
    fault(waiting, MEDIUM)
    high_fault = state("high")
    fault(high_fault, HIGH)
    assert waiting.trial_wait == 50
    for old, n_new in ((open_trial, MEDIUM), (waiting, MEDIUM), (high_fault, HIGH)):
        for veto, strict in ((False, False), (True, False), (False, True)):
            new = rule.carry_over(old, n_new=n_new, veto=veto, strict=strict)
            assert (new.trial_left, new.trial_wait, new.unresolved_fault) == (3, 0, True)
            assert (new.series, new.provisional, new.tier) == (0, 0, rule.T1)


def test_carry_over_keeps_bad_evidence():
    old = state("low", reversible=True)
    succeed(old, 3, LOW)
    fault(old, LOW)
    a, step, _ = params.wald_steps("low")
    assert old.wald == pytest.approx(3 * step + a) and old.wald > 0
    assert rule.carry_over(old, n_new=LOW, veto=False, strict=False).wald == old.wald


def test_provisional_confirmed_when_own_successes_reach_it():
    new = rule.carry_over(climbed("low", reversible=True), n_new=LOW, veto=False, strict=False)
    assert new.provisional == 26
    events = succeed(new, 25, LOW)
    assert "confirmed" not in kinds(events) and new.provisional == 26
    events = succeed(new, 1, LOW)
    confirmed = [e for e in events if e["event"] == "confirmed"]
    assert len(confirmed) == 1 and confirmed[0]["type"] == "file:write" and confirmed[0]["provisional"] == 26
    assert new.provisional == 0
    assert "confirmed" not in kinds(succeed(new, 50, LOW))
    # The first medium or high fault withdraws the carry-over entirely; a low fault does not.
    m = rule.carry_over(climbed("medium", reversible=True, n=MEDIUM), n_new=MEDIUM, veto=False, strict=False)
    assert m.provisional == 52
    fault(m, MEDIUM)
    assert (m.provisional, m.series) == (0, 0) and m.wald > 0
    assert "confirmed" not in kinds(succeed(m, 200, MEDIUM))
    lo = rule.carry_over(climbed("low", reversible=True), n_new=LOW, veto=False, strict=False)
    fault(lo, LOW)
    assert lo.provisional == 26


def test_guarantee_conditional_while_provisional():
    old = climbed("low", reversible=True)
    new = rule.carry_over(old, n_new=LOW, veto=False, strict=False)
    assert rule.guarantee(new, LOW, 0.1) == {"aoql": params.aoql(LOW, 0.1)[0],
                                             "worst_case": params.worst_case(LOW, 0.1), "conditional": True}
    assert rule.guarantee(old, LOW, 0.1)["conditional"] is False
    succeed(new, 26, LOW)
    assert new.provisional == 0 and rule.guarantee(new, LOW, 0.1)["conditional"] is False
    assert rule.guarantee(new, None, 0.1) == {"capped": True}


# --------------------------------------------------------------------------------------------------------------------
# The rest of the interface
# --------------------------------------------------------------------------------------------------------------------
def test_state_round_trip():
    s = climbed("medium", reversible=True, n=MEDIUM)
    rule.on_neutral(s, "timeout")
    d = json.loads(json.dumps(s.to_dict()))
    back = rule.TypeState.from_dict({**d, "unknown": 1})
    assert back == s and back.sessions is not s.sessions
    assert rule.TypeState.from_dict({"key": "file:write", "stakes": "low"}) == rule.TypeState("file:write", "low")
    assert (rule.T1, rule.T2, rule.T3) == ("ask", "notify", "alone")
    assert (rule.ASK, rule.NOTIFY, rule.ALLOW, rule.SPOT) == ("ask", "notify", "allow", "spot")


def test_neutral_changes_nothing_but_its_counter():
    s = state("medium", reversible=True)
    succeed(s, 2, MEDIUM)
    succeed(s, 1, MEDIUM, source="spot")
    fault(s, MEDIUM, source="spot")
    before = s.to_dict()
    assert rule.on_neutral(s, "timeout") == []
    after = s.to_dict()
    assert after.pop("neutrals") == 1 and {**before, "neutrals": None} == {**after, "neutrals": None}
    assert (s.successes, s.faults, s.neutrals, s.spot_checks) == (3, 1, 1, 2)
    assert s.trial_left == 3                                    # a neutral outcome is not a trial action


def test_revoke_back_to_t1_without_escaping_a_trial():
    s = climbed("low", reversible=True)
    events = rule.revoke(s)
    assert moves(events) == [("revoked", rule.T3, rule.T1, "owner")]
    assert (s.tier, s.series, s.sessions, s.wald) == (rule.T1, 0, [], 0.0)
    succeed(s, 11, LOW)                                         # the score's credit is gone too
    assert s.tier == rule.T1
    succeed(s, 1, LOW)
    assert s.tier == rule.T2
    m = state("medium")
    fault(m, MEDIUM)
    rule.revoke(m)
    assert (m.trial_left, m.lengthened, m.unresolved_fault, m.faults) == (3, True, True, 1)
    c = rule.carry_over(climbed("low", reversible=True), n_new=LOW, veto=False, strict=False)
    rule.revoke(c)
    assert c.provisional == 0


def test_capped_type_learns_from_faults_only():
    s = state("high")
    assert succeed(s, 10, None) == []
    assert (s.series, s.sessions, s.tier, s.successes) == (0, [], rule.T1, 10)
    fault(s, None)
    assert (s.trial_left, s.lengthened, s.unresolved_fault) == (3, True, True)
    succeed(s, 3, None)
    assert s.trial_left == 0 and not s.unresolved_fault
    with pytest.raises(ValueError):
        rule.required(s, None)


def test_sessions_are_distinct_and_at_most_ten():
    s = state("low")
    succeed(s, 30, LOW, sessions=tuple(f"s{i}" for i in range(15)))
    assert len(s.sessions) == 10 and len(set(s.sessions)) == 10
    blank = state("low")
    succeed(blank, 60, LOW, sessions=("",))                     # no session id proves nothing
    assert blank.sessions == [] and blank.tier == rule.T1


def test_events_hold_only_types_tiers_reasons_and_counts():
    secret = "3f9a1c0b7e2d"
    allowed = {"event", "type", "stakes", "from", "to", "reason", "required", "sessions", "left", "wait",
               "provisional", "successes"}
    events = []
    s = state("medium", reversible=True)
    events += succeed(s, 140, MEDIUM, sessions=(secret, "5b0e8d2a91c4"))
    events += fault(s, MEDIUM)
    events += succeed(s, 1, MEDIUM, sessions=(secret,))
    events += fault(s, MEDIUM)
    for _ in range(50):
        events += rule.count_action(s)
    events += succeed(s, 3, MEDIUM, sessions=(secret,))
    events += rule.revoke(s)
    c = rule.carry_over(climbed("low", reversible=True), n_new=LOW, veto=False, strict=False)
    events += succeed(c, 30, LOW, sessions=(secret, "5b0e8d2a91c4"))
    assert {"tier", "trial", "confirmed", "revoked"} == set(kinds(events))
    for e in events:
        assert set(e) <= allowed and secret not in json.dumps(e)
