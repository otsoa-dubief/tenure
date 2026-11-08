# Copyright 2026 Otsoa Dubief
# SPDX-License-Identifier: Apache-2.0
"""The rule for one action type: Dodge's CSP-1 with the refinements of the earned-autonomy study.

- ASK: every action of the type asks the owner. ``i`` approvals in a row clear the type.
- CLEARED: the agent acts alone, except a random fraction ``f`` of actions that still ask (spot checks).
- A refusal resets the streak. A refused spot check, or an error the owner flags after the fact, revokes the
  clearance: back to ASK, and a new generation, so that Hermes' own "session"/"always" choices for the old
  generation stop applying.
- At medium or high stakes, an error lengthens the next climb to ceil(1.25 i) approvals (the error stays on the
  record); the lengthening does not pile up and is dropped once the type is cleared again.
- A model change starts every type over: the record was about another agent.
- Timeouts, cancellations and answers given by a model rather than a person count for nothing.

The functions mutate the state and return the events to write to the ledger.
"""
from __future__ import annotations

import math
import random
import time
from dataclasses import asdict, dataclass

ASK, CLEARED = "ask", "cleared"           # levels
ALLOW, SPOT = "allow", "spot"             # decisions besides ASK
LENGTHEN = 1.25


@dataclass
class TypeState:
    key: str
    stakes: str                            # "low" | "medium" | "high"
    level: str = ASK
    streak: int = 0
    lengthened: bool = False
    generation: int = 0
    manual: bool = False                   # cleared by the owner's own "always", not by the record
    approvals: int = 0
    refusals: int = 0
    spot_checks: int = 0
    revocations: int = 0
    changed_at: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "TypeState":
        fields = cls.__dataclass_fields__
        return cls(**{k: v for k, v in d.items() if k in fields})


def required(s: TypeState, i: int) -> int:
    return math.ceil(LENGTHEN * i) if s.lengthened else i


def decide(s: TypeState, i: int, spot: float, rng: random.Random | None = None) -> str:
    """ASK, SPOT (a cleared type's random check) or ALLOW."""
    if s.level != CLEARED:
        return ASK
    r = (rng or random).random()
    return SPOT if r < spot else ALLOW


def _event(s: TypeState, name: str, **extra) -> dict:
    s.changed_at = time.time()
    return dict(event=name, type=s.key, stakes=s.stakes, generation=s.generation, at=s.changed_at, **extra)


def on_approval(s: TypeState, i: int, *, manual: bool = False, spot: bool = False) -> list[dict]:
    s.approvals += 1
    if spot:
        s.spot_checks += 1
    if s.level == CLEARED:
        return []
    need = required(s, i)
    s.streak = min(s.streak + 1, need)
    if manual or s.streak >= need:
        s.level, s.manual = CLEARED, manual
        ev = _event(s, "cleared", approvals_in_a_row=s.streak, required=need, manual=manual)
        s.lengthened = False
        return [ev]
    return []


def _revoke(s: TypeState, i: int, reason: str, **extra) -> list[dict]:
    was = s.level
    s.streak = 0
    if s.stakes in ("medium", "high"):
        s.lengthened = True
    if was != CLEARED:
        return []
    s.level, s.manual = ASK, False
    s.generation += 1
    s.revocations += 1
    return [_event(s, "revoked", reason=reason, next_required=required(s, i), **extra)]


def on_refusal(s: TypeState, i: int, *, spot: bool = False) -> list[dict]:
    s.refusals += 1
    if spot:
        s.spot_checks += 1
    return _revoke(s, i, "refused")


def on_flag(s: TypeState, i: int, note: str = "") -> list[dict]:
    """The owner reports an error the agent made on its own."""
    s.refusals += 1
    events = _revoke(s, i, "flagged", note=note)
    return events or [_event(s, "flagged", note=note)]


def on_neutral(s: TypeState, reason: str) -> list[dict]:
    return []


def on_model_change(s: TypeState, old: str, new: str) -> list[dict]:
    s.level, s.streak, s.lengthened, s.manual = ASK, 0, False, False
    s.generation += 1
    return [_event(s, "reset", reason="model change", old_model=old, new_model=new)]
