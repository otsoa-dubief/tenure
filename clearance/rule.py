# Copyright 2026 Otsoa Dubief
# SPDX-License-Identifier: Apache-2.0
"""The rule for one action type: rule B of the preregistered earned-autonomy study, with the middle tier of its
amendment A1.

Tiers:

- T1, ask: every action of the type asks the owner first.
- T2, notify: the agent acts, then the owner is notified and can undo. Only for reversible types at low or medium
  stakes.
- T3, alone: the agent acts alone; a random share of its actions (spot checks) still asks.

Two measures per type, both updated by every verified outcome:

- The series counts verified successes in a row, at any tier, capped at the required length: ``n`` from
  ``params.required_n``, or ceil(1.25 n) for the climb that follows a medium or high fault. A full series that
  holds successes from at least two distinct sessions gives T3.
- The Wald score of amendment A1 leads a reversible type to T2. A success adds ``s`` (negative), down to the floor
  ln B - a; a low-stakes fault adds ``a``; a medium or high fault sets it to max(score, 0) + a. The type climbs to
  T2 once the score is at most ln B: 12 successes from scratch at low stakes, 18 at medium stakes. The score is
  kept at T3 too, for the way back down.

Every fault resets the series and its sessions. A medium or high fault sends the type back to T1 from any tier,
lengthens the next climb (this does not pile up) and opens a trial: the type asks until it has 3 verified successes,
and neutral outcomes count neither way. A fault during the trial fails it; the trial reopens after the 50 executed
actions of the type that follow the failing one, and a fault during that wait opens no new trial. While a trial is
open, and during that wait, successes count in the statistics only: the series and the score stay frozen. A
low-stakes fault at T3 goes down one tier, to T2 for a reversible type and to T1 otherwise; at T2, the score decides
between T2 and T1. A medium or high fault also stays in the agent's memory (``unresolved_fault``), even once its
trial is passed: the fault remains on the record (study, piece 7).

A model change makes a new agent (``carry_over``). By default, half of the old series is carried over and marked
provisional, with half of a negative score; a positive score, which is bad evidence, is kept whole. Each of the new
agent's own successes in the series confirms one carried success, and the carry-over is confirmed when none is
left; successes during a trial confirm nothing. The carry-over lives in the series, so the first fault of any stakes
withdraws it, together with the score credit it brought. There is no carry-over at high stakes, when the public
benchmarks veto it, or in strict mode: those start over, as in the study. In every mode, a medium or high fault in
the old agent's memory becomes a trial for the new agent, and only that trial, once passed by an agent with no such
fault of its own, erases it (piece 8).

A capped type (``n`` is None) always asks and never climbs: its successes only count in ``successes``, and its faults
apply in full, so its tier can still drop. When the settings change, ``reevaluate`` caps the series at the new
length and drops a T3 type whose series no longer meets it, or that is now capped. Looser settings never promote a
type by themselves: the next success does.

Neutral outcomes (timeouts, cancellations, unverifiable results) change nothing but their counter.

The functions mutate the state and return the derived events to log, for display only: ``tier``, ``trial``,
``confirmed`` and ``revoked``. An event holds the type, its stakes, tiers, reasons and counts, nothing else.
"""
from __future__ import annotations

import math
import random
import time
from dataclasses import asdict, dataclass, field

from . import params

T1, T2, T3 = "ask", "notify", "alone"                            # tiers
ASK, NOTIFY, ALLOW, SPOT = "ask", "notify", "allow", "spot"      # decisions

LENGTHEN = 1.25        # the climb after a medium or high fault needs ceil(1.25 n); 1.25 is exact in binary
TRIAL = 3              # actions in a trial, all of which must succeed
WAIT = 50              # actions of the type to count after a failed trial before it reopens
SESSIONS = 2           # distinct sessions needed in the series that reaches T3
MAX_SESSIONS = 10      # session ids kept per type
CARRY = 0.5            # share of the series, and of a negative score, carried over to a new agent
TOL = 1e-12            # tolerance when comparing Wald scores
GRAVE = ("medium", "high")

_RANK = {T1: 1, T2: 2, T3: 3}
_NONE, _OPEN, _WAIT = "none", "open", "wait"                     # trial statuses, in trial events


@dataclass
class TypeState:
    # identity
    key: str
    stakes: str                        # "low" | "medium" | "high"
    reversible: bool = False
    # tier and series
    tier: str = T1
    series: int = 0
    sessions: list[str] = field(default_factory=list)       # distinct sessions in the series, at most 10
    # Wald score of the middle tier (reversible types at low or medium stakes; 0.0 otherwise)
    wald: float = 0.0
    # descent
    lengthened: bool = False           # the next climb needs ceil(1.25 n)
    trial_left: int = 0                # successes still needed by the open trial
    trial_wait: int = 0                # actions still to count before a failed trial reopens
    unresolved_fault: bool = False     # a medium or high fault in memory: kept when its trial is passed, erased
                                       # only by the trial a model change opens
    # carry-over
    provisional: int = 0               # carried-over successes not yet matched by the agent's own series successes
    # counters (the agent's own)
    successes: int = 0
    faults: int = 0
    neutrals: int = 0
    spot_checks: int = 0
    changed_at: float = 0.0            # time of the last derived event, or of the carry-over that made the state

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "TypeState":
        known = cls.__dataclass_fields__
        kw = {k: v for k, v in d.items() if k in known}
        if "sessions" in kw:
            kw["sessions"] = list(kw["sessions"] or [])
        return cls(**kw)


def required(s: TypeState, n: int) -> int:
    """Series length the type needs for T3: ``n``, or ceil(1.25 n) during the climb after a medium or high fault."""
    if n is None:
        raise ValueError("a capped type has no series length")
    return math.ceil(LENGTHEN * n) if s.lengthened else n


def _middle(s: TypeState) -> bool:
    """The type has the middle tier: reversible, at a stakes level with Wald settings (low or medium)."""
    return s.reversible and s.stakes in params.WALD


def _own_grave_fault(s: TypeState) -> bool:
    """The agent made a medium or high fault on this type itself (a type's faults all share its stakes)."""
    return s.stakes in GRAVE and s.faults > 0


def _target(s: TypeState, n: int | None) -> str:
    if n is not None and s.series >= required(s, n) and len(s.sessions) >= SESSIONS:
        return T3
    if _middle(s) and s.wald <= params.wald_steps(s.stakes)[2] + TOL:
        return T2
    return T1


def _event(s: TypeState, name: str, **data) -> dict:
    s.changed_at = time.time()
    return {"event": name, "type": s.key, "stakes": s.stakes, **data}


def _move(s: TypeState, name: str, old: str, new: str, reason: str, **counts) -> dict:
    return _event(s, name, **{"from": old, "to": new, "reason": reason}, **counts)


def _climb(s: TypeState, n: int | None) -> list[dict]:
    """Move up to the tier the record now supports. A capped type never climbs; tiers only go down through faults,
    revocations and stricter settings."""
    if n is None:
        return []
    target = _target(s, n)
    if _RANK[target] <= _RANK[s.tier]:
        return []
    old, counts = s.tier, {}
    if target == T3:
        counts = {"required": required(s, n), "sessions": len(s.sessions)}
        if s.lengthened:                   # the lengthened climb is done: the next ones need n again
            s.lengthened = False
            s.series = min(s.series, n)
    s.tier = target
    return [_move(s, "tier", old, target, "series" if target == T3 else "wald", **counts)]


def _confirm(s: TypeState) -> list[dict]:
    """One own success in the series confirms one carried success; the carry-over is confirmed when none is left."""
    if s.provisional <= 0:
        return []
    s.provisional = min(s.provisional - 1, s.series)
    return [] if s.provisional else [_event(s, "confirmed")]


def decide(s: TypeState, n: int | None, spot: float, *, suspended: bool, rng: random.Random) -> str:
    """ASK, NOTIFY, ALLOW or SPOT for the next action of the type. Only T3 draws from ``rng``, once."""
    if n is None or suspended or s.trial_left > 0 or s.trial_wait > 0:
        return ASK
    if s.tier == T3:
        return SPOT if rng.random() < spot else ALLOW
    if s.tier == T2 and _middle(s):
        return NOTIFY
    return ASK


def on_success(s: TypeState, n: int | None, *, session: str, source: str) -> list[dict]:
    """A verified success. ``session`` is the anonymised session id; ``source`` "spot" marks a spot check.

    During a trial it only counts toward the trial, and during the wait after a failed trial it only counts in the
    statistics. A capped type (``n`` is None) never climbs: its success only counts in ``successes``. Otherwise the
    success enters the series, with its session, and the score, and confirms one carried success if any is left.
    """
    s.successes += 1
    if source == "spot":
        s.spot_checks += 1
    events = []
    if s.trial_left > 0:
        s.trial_left -= 1
        if s.trial_left == 0:
            # Without a medium or high fault of its own, the agent's only possible trial is the one a model change
            # opened: passing it erases the fault inherited in memory. Its own faults stay in memory.
            if not _own_grave_fault(s):
                s.unresolved_fault = False
            events.append(_move(s, "trial", _OPEN, _NONE, "passed"))
            events += _climb(s, n)
    elif s.trial_wait == 0 and n is not None:
        s.series = min(s.series + 1, required(s, n))
        if session and session not in s.sessions:
            s.sessions.append(session)
            del s.sessions[:-MAX_SESSIONS]
        if _middle(s):
            a, step, ln_b = params.wald_steps(s.stakes)
            s.wald = max(s.wald + step, ln_b - a)
        events += _climb(s, n)
        events += _confirm(s)
    return events


def on_fault(s: TypeState, n: int | None, *, session: str, source: str) -> list[dict]:
    """A verified fault: a refusal, a failed automatic check, an undo or a flag. ``source`` "spot" marks a spot check.

    The series and its sessions restart, and with them a carry-over, which lived in the series; the score credit it
    brought goes too (the score becomes max(score, 0) + a, as after a medium or high fault), so the new agent never
    regains T2 faster than in strict mode. A medium or high fault sends the type to T1, lengthens the next climb,
    stays in memory and opens a trial; during a trial, any fault fails it, and a fault during the wait after a failed
    trial leaves the wait as it is. A low-stakes fault goes down at most one tier. Faults apply in full to a capped
    type too.
    """
    s.faults += 1
    if source == "spot":
        s.spot_checks += 1
    grave, in_trial, old, borrowed = s.stakes in GRAVE, s.trial_left > 0, s.tier, s.provisional > 0
    s.series, s.sessions, s.provisional = 0, [], 0
    if _middle(s):
        a = params.wald_steps(s.stakes)[0]
        s.wald = (max(s.wald, 0.0) if grave or borrowed else s.wald) + a
    if grave:
        s.tier, s.lengthened, s.unresolved_fault = T1, True, True
    else:
        target = _target(s, n)
        if _RANK[target] < _RANK[s.tier]:
            lowest = T2 if s.tier == T3 and _middle(s) else T1
            s.tier = max(target, lowest, key=_RANK.__getitem__)
    events = [_move(s, "tier", old, s.tier, "fault")] if s.tier != old else []
    if in_trial:
        s.trial_left, s.trial_wait = 0, WAIT
        events.append(_move(s, "trial", _OPEN, _WAIT, "failed", wait=WAIT))
    elif grave and s.trial_wait == 0:
        s.trial_left = TRIAL
        events.append(_move(s, "trial", _NONE, _OPEN, "fault", left=TRIAL))
    return events


def on_neutral(s: TypeState, reason: str) -> list[dict]:
    """A timeout, a cancellation, an answer from no one or an unverifiable result: nothing is learned."""
    s.neutrals += 1
    return []


def count_action(s: TypeState) -> list[dict]:
    """One more executed action of the type: runs the wait after a failed trial.

    The hooks, and the replay, call it after the outcome of each executed action of the type: a success, a fault, or
    a neutral outcome from a tool failure. Never for a timeout, an expired ask or a cancelled one, and not for the
    action whose fault failed the trial (``on_fault`` then returns a ``trial`` event with the reason "failed"): the
    wait counts the 50 executed actions after that one, and the trial reopens with the 51st.
    """
    if s.trial_wait <= 0:
        return []
    s.trial_wait -= 1
    if s.trial_wait:
        return []
    s.trial_left = TRIAL
    return [_move(s, "trial", _WAIT, _OPEN, "wait over", left=TRIAL)]


def carry_over(old: TypeState, *, n_new: int | None, veto: bool, strict: bool) -> TypeState:
    """The new agent's state for a type, after a model or provider change. ``old`` is left untouched.

    By default, half of the old series is carried over as provisional (capped at ``n_new``), with half of a negative
    score; a positive score is kept whole, and the tier is computed again (no T3 before two new sessions). At high
    stakes, under a veto, in strict mode or when the type is now capped, the new agent starts fresh. In every mode, a
    medium or high fault in the old agent's memory (even one whose trial it passed) becomes a trial for the new
    agent, with the fault still in memory until that trial is passed; low-stakes faults disappear. The new state's
    counters start at zero: they belong to the new agent.
    """
    new = TypeState(key=old.key, stakes=old.stakes, reversible=old.reversible, changed_at=time.time())
    if old.unresolved_fault:
        new.trial_left, new.unresolved_fault = TRIAL, True
    if strict or veto or old.stakes == "high" or n_new is None:
        return new
    new.series = new.provisional = min(math.floor(old.series * CARRY), n_new)
    new.wald = old.wald * CARRY if old.wald < 0 else old.wald
    new.tier = _target(new, n_new)
    return new


def reevaluate(s: TypeState, n: int | None) -> list[dict]:
    """The settings changed: ``n`` is the type's new series length, or None when it is now capped.

    With a series length, the series is first capped at it, and the provisional part with the series. A T3 type
    whose series no longer meets the required length, or that is now capped, then drops: to T2 if it has the middle
    tier and its score is at most ln B, to T1 otherwise. Looser settings never promote a type by themselves: the next
    success does. The hooks and the replay call this whenever the settings change.
    """
    if n is not None:
        s.series = min(s.series, required(s, n))
        s.provisional = min(s.provisional, s.series)
    if s.tier != T3 or (n is not None and s.series >= required(s, n)):
        return []
    s.tier = T2 if _middle(s) and s.wald <= params.wald_steps(s.stakes)[2] + TOL else T1
    counts = {} if n is None else {"required": required(s, n)}
    return [_move(s, "tier", T3, s.tier, "settings", **counts)]


def rebase(s: TypeState) -> list[dict]:
    """The type's stakes changed (an owner's override, or arguments that raise or lower them): evidence counts only at
    the stakes it was earned at. The series, its sessions and the carried-over part start over, the Wald score loses
    its credit but keeps a fault's penalty (max(score, 0): the error stays), and the tier returns to T1; an open
    trial, its wait, a lengthened climb and the faults in memory stay. Call it before applying the first outcome at
    the new stakes (the hooks and the replay both do)."""
    old = s.tier
    s.tier, s.series, s.sessions, s.provisional, s.wald = T1, 0, [], 0, max(s.wald, 0.0)
    return [_move(s, "tier", old, T1, "stakes")]


def revoke(s: TypeState) -> list[dict]:
    """The owner takes the type's autonomy back: T1, no series and no score credit, no carry-over.

    It is not a fault: an open trial, its wait and a lengthened climb stay as they are.
    """
    old = s.tier
    s.tier, s.series, s.sessions, s.provisional = T1, 0, [], 0
    s.wald = max(s.wald, 0.0)
    return [_move(s, "revoked", old, T1, "owner")]


def guarantee(s: TypeState, n: int | None, spot: float) -> dict:
    """The type's guarantee for its series length and the spot-check rate, from ``params`` only."""
    if n is None:
        return {"capped": True}
    return {"aoql": params.aoql(n, spot)[0], "worst_case": params.worst_case(n, spot), "conditional": s.provisional > 0}
