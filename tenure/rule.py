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
  holds successes from enough distinct sessions gives T3 (rule B/2: two, three at medium stakes, none over half).
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

Simple mode (``SIMPLE_VERSION``, the default since 1.4) keeps the numbers and drops the rest. A type at low or medium
stakes that carries no outbound verb runs freely until its first fault. That fault sends a reversible type to T2 with
its score at the bar (ln B), any other to T1; a fault at T2 sends it to T1 whatever its score (which still takes the
step ``a``), and approvals bring it back to T2 as above. A series of ``n`` verified successes, an act-then-tell action left
undone through its undo window counting as one (``unseen``), gives the type its freedom back (T3, which never draws a
spot check there). No trial, wait, lengthening, session condition or guarantee; high stakes and outbound verbs always
ask. A person may also free a kind at once (``owner_free``) or pin it to ask until freed again (``owner_pin``): the
``trust`` ledger event, which the study rule never reads. ``outcome`` applies one outcome under either mode, for the hooks and the replay alike.

The functions mutate the state and return the derived events to log, for display only: ``tier``, ``trial``,
``confirmed`` and ``revoked``. An event holds the type, its stakes, tiers, reasons and counts, nothing else.
"""
from __future__ import annotations

import math
import random
import time
from dataclasses import asdict, dataclass, field

from . import params

VERSION = "study-rule-B/2"    # B/2 (1.3): sessions per stakes, no session over half the series, seen T2 successes
SIMPLE_VERSION = "simple/1"   # simple mode (1.4): free until a fault, notified after one, asks after a second
VERSIONS = ("study-rule-B/1", VERSION, SIMPLE_VERSION)   # a B/1 ledger replays under B/2: same settings reading
SIMPLE, STUDY = "simple", "study"                         # modes
T1, T2, T3 = "ask", "notify", "alone"                            # tiers
ASK, NOTIFY, ALLOW, SPOT = "ask", "notify", "allow", "spot"      # decisions
WATCH = "watch"        # trusted start: act like Hermes alone, with an undo when the files can be saved

LENGTHEN = 1.25        # the climb after a medium or high fault needs ceil(1.25 n); 1.25 is exact in binary
TRIAL = 3              # actions in a trial, all of which must succeed
WAIT = 50              # actions of the type to count after a failed trial before it reopens
SESSIONS = 2           # distinct sessions needed in the series that reaches T3, at low stakes
SESSIONS_BY_STAKES = {"low": 2, "medium": 3, "high": 3}   # rule B/2: more conversations where more is at stake
MAX_SHARE = 0.5        # rule B/2: no session gives more than half of the series (a 51 + 1 split is one context)
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
    session_runs: list = field(default_factory=list)       # the series' own successes, oldest first, as
                                                           # [session, count] runs (rule B/2; "" = no session)
    # Wald score of the middle tier (reversible types at low or medium stakes; 0.0 otherwise)
    wald: float = 0.0
    # descent
    lengthened: bool = False           # the next climb needs ceil(1.25 n)
    trial_left: int = 0                # successes still needed by the open trial
    trial_wait: int = 0                # actions still to count before a failed trial reopens
    unresolved_fault: bool = False     # a medium or high fault in memory: kept when its trial is passed, erased
                                       # only by the trial a model change opens
    distrusted: bool = False           # a fault or a revoke happened: the trusted start no longer covers the type
    pinned: bool = False               # simple mode: the owner said the kind always asks first, until freed again
    owner_freed: bool = False          # simple mode: the owner freed a kind tenure cannot undo (``owner_free`` with
                                       # undo False), until its next fault: it runs with no undo
    # carry-over
    provisional: int = 0               # carried-over successes not yet matched by the agent's own series successes
    # counters (the agent's own)
    successes: int = 0
    faults: int = 0
    neutrals: int = 0
    excused: int = 0                   # faults the owner excused afterwards (protocol 0.2): counted among neutrals
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
        if "distrusted" not in kw:         # a state stored before the trusted start: a fault on record ends it
            kw["distrusted"] = bool(kw.get("faults"))
        return cls(**kw)


def sessions_needed(stakes: str) -> int:
    return SESSIONS_BY_STAKES.get(stakes, SESSIONS)


def _add_run(s: TypeState, session: str) -> None:
    """One more own success of the series, in session ``session``; the oldest leave when the series is capped."""
    runs = s.session_runs
    if runs and runs[-1][0] == session:
        runs[-1][1] += 1
    else:
        runs.append([session, 1])


def _trim_runs(s: TypeState) -> None:
    """Keep the runs to the series' own successes (its length less the carried part): the oldest leave first. Called
    after every change of the series' length (a capped series, a carried success confirmed, stricter settings)."""
    runs = s.session_runs
    own = sum(r[1] for r in runs)
    while runs and own > max(s.series - s.provisional, 0):
        runs[0][1] -= 1
        own -= 1
        if runs[0][1] == 0:
            runs.pop(0)


def session_counts(s: TypeState) -> dict:
    out: dict = {}
    for k, v in s.session_runs:
        if k:
            out[k] = out.get(k, 0) + v
    return out


def sessions_met(s: TypeState) -> bool:
    """The series spans enough conversations (rule B/2): at least ``sessions_needed(stakes)`` distinct ones among the
    agent's own successes still in the series, and none gives more than half of them (rounded up: 11 of 21); the
    successes without a session count as one more block. The part carried from another model is the study's own
    carry-over, confirmed by these new sessions: it is not a session."""
    counts = session_counts(s)
    if len(counts) < sessions_needed(s.stakes):
        return False
    own = sum(v for _, v in s.session_runs)
    blocks = list(counts.values()) + [sum(v for k, v in s.session_runs if not k)]
    return max(blocks) <= math.ceil(MAX_SHARE * max(own, 1))


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
    if n is not None and s.series >= required(s, n) and sessions_met(s):
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
        counts = {"required": required(s, n), "sessions": len(session_counts(s))}
        if s.lengthened:                   # the lengthened climb is done: the next ones need n again
            s.lengthened = False
            s.series = min(s.series, n)
            _trim_runs(s)
            target = _target(s, n)         # the shorter series must still meet the sessions rule (B/2)
            if _RANK[target] <= _RANK[s.tier]:
                return []
    s.tier = target
    return [_move(s, "tier", old, target, "series" if target == T3 else "wald", **counts)]


def _confirm(s: TypeState) -> list[dict]:
    """One own success in the series confirms one carried success; the carry-over is confirmed when none is left."""
    if s.provisional <= 0:
        return []
    s.provisional = min(s.provisional - 1, s.series)
    return [] if s.provisional else [_event(s, "confirmed")]


def decide(s: TypeState, n: int | None, spot: float, *, suspended: bool, rng: random.Random,
           mode: str = STUDY) -> str:
    """ASK, NOTIFY, ALLOW or SPOT for the next action of the type. Only T3 draws from ``rng``, once. In simple mode
    nothing is drawn: a free type asks here and the hooks run it as Hermes would (``trusted``), and a type simple mode
    never frees (high stakes, an outbound verb) asks."""
    if n is None or suspended or s.trial_left > 0 or s.trial_wait > 0:
        return ASK
    if mode == SIMPLE:
        return NOTIFY if s.tier == T2 and _middle(s) and simple_eligible(s, n) and not s.pinned else ASK
    if s.tier == T3:
        return SPOT if rng.random() < spot else ALLOW
    if s.tier == T2 and _middle(s):
        return NOTIFY
    return ASK


def effective_tier(s: TypeState, n: int | None, stakes: str) -> str:
    """The tier that would actually run an action of this type at ``stakes`` today: the stored tier, held to the same
    guards as ``decide`` plus the decision-time check (``_earned``): a capped type, evidence earned at other stakes,
    an open trial or wait, a series shorter than today's requirement, or a Wald score above
    the middle tier's bar all ask (T1). Reads only; it changes nothing."""
    if n is None or s.stakes != stakes or s.trial_left > 0 or s.trial_wait > 0:
        return T1
    if s.tier == T3 and s.series >= required(s, n):     # the sessions gate the climb, not keeping T3
        return T3
    if s.tier == T2 and _middle(s) and s.wald <= params.wald_steps(s.stakes)[2] + TOL:
        return T2
    return T1


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
        _add_run(s, session)
        if _middle(s):
            a, step, ln_b = params.wald_steps(s.stakes)
            s.wald = max(s.wald + step, ln_b - a)
        events += _confirm(s)
        _trim_runs(s)                      # the series' own runs first: the climb checks the sessions on them (B/2)
        events += _climb(s, n)
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
    s.distrusted = True
    if source == "spot":
        s.spot_checks += 1
    grave, in_trial, old, borrowed = s.stakes in GRAVE, s.trial_left > 0, s.tier, s.provisional > 0
    s.series, s.sessions, s.provisional = 0, [], 0
    s.session_runs = []
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


def on_trusted_success(s: TypeState, *, source: str) -> list[dict]:
    """A verified success of a type the trusted start covers: statistics only. Trust is given, not earned: the series
    and the score stay as they are, so no tier is reached without a person's approvals (after a first fault)."""
    s.successes += 1
    if source == "spot":
        s.spot_checks += 1
    return []


def on_neutral(s: TypeState, reason: str) -> list[dict]:
    """A timeout, a cancellation, an answer from no one or an unverifiable result: nothing is learned.

    An excused fault (``reason`` "excused", replayed in its place) is neutral for everything it cost (the score, the
    tier drop, the trial, the lost trusted start), but the series still restarts, as CSP-1 restarts it at every
    detected defect: an excuse given by mistake never carries a run of successes past a real error. A type at T3 then
    stands at T2 when it has the middle tier, else T1: an empty series cannot keep acting alone."""
    s.neutrals += 1
    if reason != "excused":
        return []
    old = s.tier
    s.series, s.sessions, s.provisional, s.session_runs = 0, [], 0, []
    if s.tier == T3:                                # T2 only where its score holds, as reevaluate checks
        s.tier = T2 if _middle(s) and s.wald <= params.wald_steps(s.stakes)[2] + TOL else T1
    return [_move(s, "tier", old, s.tier, "excused")] if s.tier != old else []


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
    new = TypeState(key=old.key, stakes=old.stakes, reversible=old.reversible, changed_at=time.time(),
                    distrusted=old.distrusted)    # a fault on the type in this profile outlives the model
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
        _trim_runs(s)
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
    s.session_runs = []
    s.owner_freed = False              # a person's word was given at the old stakes
    return [_move(s, "tier", old, T1, "stakes")]


def revoke(s: TypeState) -> list[dict]:
    """The owner takes the type's autonomy back: T1, no series and no score credit, no carry-over.

    It is not a fault: an open trial, its wait and a lengthened climb stay as they are.
    """
    old = s.tier
    s.tier, s.series, s.sessions, s.provisional = T1, 0, [], 0
    s.session_runs = []
    s.wald = max(s.wald, 0.0)
    s.distrusted = True
    s.owner_freed = False              # simple mode: the owner takes back a freedom given by hand too
    return [_move(s, "revoked", old, T1, "owner")]


def simple_eligible(s: TypeState, n: int | None) -> bool:
    """Simple mode may free the type: low or medium stakes, not capped, no outbound verb in its key."""
    return n is not None and s.stakes in ("low", "medium") and params.simple_covers(s.key)


def trusted(s: TypeState, n: int | None, start: str | None, mode: str = STUDY) -> bool:
    """The trusted start covers the type: ``start`` is "trusted", no fault or revoke on it in the profile, low or
    medium stakes, not capped, no trial. Such a type asks nothing Hermes alone would not ask. In simple mode: a type
    simple mode may free that is free, never faulted or revoked, or back at T3."""
    if mode == SIMPLE:
        return (simple_eligible(s, n) and not s.trial_left and not s.trial_wait and not s.pinned
                and (not s.distrusted or s.tier == T3))
    return trusted_start(s, n, start)


def trusted_start(s: TypeState, n: int | None, start: str | None) -> bool:
    """``trusted`` in study mode: the trusted start covers the type."""
    return (start == "trusted" and not s.distrusted and n is not None and s.stakes in ("low", "medium")
            and not s.trial_left and not s.trial_wait and trust_covers(s.key))


def trust_covers(key: str) -> bool:
    """The kinds of action the trusted start may cover (``params.trust_covers``)."""
    return params.trust_covers(key)


def guarantee(s: TypeState, n: int | None, spot: float) -> dict:
    """The type's guarantee for its series length and the spot-check rate, from ``params`` only."""
    if n is None:
        return {"capped": True}
    return {"aoql": params.aoql(n, spot)[0], "worst_case": params.worst_case(n, spot), "missed": params.missed(),
            "conditional": s.provisional > 0}


# ------------------------------------------------------------------------------------------------- simple mode
def mode_of(settings_event: dict | None) -> str:
    """The mode a ``settings`` ledger event was recorded under: its rule version tells."""
    return SIMPLE if (settings_event or {}).get("rule") == SIMPLE_VERSION else STUDY


def _simple_success(s: TypeState, n: int | None, *, source: str) -> list[dict]:
    """Simple mode, a verified success of a type that is not free: the series (no session condition) and the score.
    A full series frees the type (T3); a score at the bar takes a T1 type to T2."""
    s.successes += 1
    if source == "spot":
        s.spot_checks += 1
    if not simple_eligible(s, n) or s.pinned:     # pinned by the owner: it asks until the owner frees it
        return []
    s.series = min(s.series + 1, n)
    if _middle(s):
        a, step, ln_b = params.wald_steps(s.stakes)
        s.wald = max(s.wald + step, ln_b - a)
    old = s.tier
    if s.series >= n:
        s.tier = T3
    elif s.tier == T1 and _middle(s) and s.wald <= params.wald_steps(s.stakes)[2] + TOL:
        s.tier = T2
    if s.tier == old:
        return []
    return [_move(s, "tier", old, s.tier, "series" if s.tier == T3 else "wald", required=n)]


def _simple_fault(s: TypeState, n: int | None, *, source: str, free: bool) -> list[dict]:
    """Simple mode, a verified fault. The series restarts. A free type (``free``: never faulted, or back at T3)
    goes to T2 with its score at the bar when it is reversible at low or medium stakes, else to T1. A type already
    held back goes to T1, whatever its score, which still takes the study's Wald step and is then at least ln B + a:
    the score only leads back up to T2, after the study's count of approvals. No trial, wait or lengthening."""
    s.faults += 1
    s.distrusted = True
    s.owner_freed = False          # a person's word holds until the next mistake: a kind tenure cannot undo asks again
    if source == "spot":
        s.spot_checks += 1
    old, borrowed = s.tier, s.provisional > 0
    s.series, s.sessions, s.provisional, s.session_runs = 0, [], 0, []
    if free:
        if _middle(s):
            s.tier, s.wald = T2, params.wald_steps(s.stakes)[2]
        else:
            s.tier = T1
        return [_move(s, "tier", "trusted" if old != T3 else T3, s.tier, "fault")]
    if _middle(s):
        a, _, ln_b = params.wald_steps(s.stakes)
        s.wald = (max(s.wald, 0.0) if s.stakes in GRAVE or borrowed else s.wald) + a
        s.wald = max(s.wald, ln_b + a)  # the climb back to T2 takes the study's count from there, never one approval
    s.tier = T1                    # a second fault asks first, whatever the score: the score only leads back up
    return [_move(s, "tier", old, s.tier, "fault")] if s.tier != old else []


def outcome(s: TypeState, n: int | None, result: str, source: str, *, session: str, start: str | None,
            mode: str = STUDY) -> list[dict]:
    """One outcome on the type under the mode, the one dispatch of the hooks and of the replay: a success of a type
    the trusted start (or simple mode) leaves free counts in the statistics only. In simple mode, an act-then-tell
    action left undone through its undo window (``unseen``) is a success, and an excused fault is only neutral."""
    if mode == SIMPLE:
        if (result, source) == ("neutral", "unseen"):
            result = "success"
        free = trusted(s, n, start, mode)
        if result == "success":
            return on_trusted_success(s, source=source) if free else _simple_success(s, n, source=source)
        if result == "fault":
            return _simple_fault(s, n, source=source, free=free)
        s.neutrals += 1
        return []
    if result == "success":
        if trusted(s, n, start):
            return on_trusted_success(s, source=source)
        return on_success(s, n, session=session, source=source)
    if result == "fault":
        return on_fault(s, n, session=session, source=source)
    return on_neutral(s, source)


def carry_over_simple(old: TypeState, *, strict: bool) -> TypeState:
    """Simple mode, a model change: the new agent keeps the type as it stands (tier, score, series, the lost trusted
    start, its faults), with other counters of its own and no trial; in strict mode it starts over, still distrusted
    and with its faults if it had them."""
    new = TypeState(key=old.key, stakes=old.stakes, reversible=old.reversible, changed_at=time.time(),
                    distrusted=old.distrusted, pinned=old.pinned,     # the owner's word holds for the new model
                    owner_freed=old.owner_freed)
    new.faults = old.faults            # the faults on the type stay on its record: they hold its categories (_marked)
    if not strict:
        new.tier, new.wald, new.series = old.tier, old.wald, old.series
    return new


# ------------------------------------------------------------------------------------------ the owner's word
FREE, PIN = "free", "ask"     # the ``to`` of a ``trust`` ledger event (simple mode only)


def owner_free(s: TypeState, n: int | None, *, undo: bool = True) -> list[dict]:
    """Simple mode, a ``trust`` event with ``to: free``: a person gives the kind its freedom back now, as a full
    series would (T3 with its series full, no longer pinned). ``undo`` False (the event's ``undo: false``, written
    when the kind asked only because tenure cannot undo it) marks it freed without an undo (``owner_freed``): it then
    runs even when no undo can be prepared (the hooks read it), until its next fault; any other kind runs with its
    undo when its files can be saved, and asks when they cannot, as a free kind does. The pin goes in every case. A
    kind simple mode does not free (an outbound verb, high stakes, capped) keeps its tier. The faults stay on the
    record and ``distrusted`` stays set, so its next fault makes it watched again (``_simple_fault`` from T3), or asks
    first for a kind with no middle tier."""
    s.pinned = False
    if not simple_eligible(s, n):
        return []
    old = s.tier
    s.tier, s.series, s.provisional, s.owner_freed = T3, n, 0, not undo
    return [_move(s, "tier", old, T3, "owner")] if old != T3 else []


def owner_pin(s: TypeState) -> list[dict]:
    """Simple mode, a ``trust`` event with ``to: ask``: the kind asks first, every time, until a person frees it
    (``owner_free``). Its approvals still count in its statistics, never toward freedom; its series starts over."""
    old = s.tier
    s.tier, s.series, s.sessions, s.session_runs, s.provisional, s.pinned = T1, 0, [], [], 0, True
    s.owner_freed = False
    return [_move(s, "tier", old, T1, "owner")] if old != T1 else []
