# Copyright 2026 Otsoa Dubief
# SPDX-License-Identifier: Apache-2.0
"""The numbers of the rule, for the risk a user accepts: series lengths, the middle tier's steps, the guarantee.

The series length for an accepted risk ``bar`` (the share of errors that may run without a human check) is the
formula of the preregistered earned-autonomy study, in exact fractions: N = ceil(1 / (DETECTION * bar)) - 1 (``study_n``). A type
whose last N verified outcomes are successes acts alone, except for a random fraction ``f`` of its actions that still
asks (spot checks); one caught error takes the autonomy back.

Errors the owner catches never run: an asked action that is refused is blocked. Errors that run unchecked are those
of a type that acts alone, and those of an act-then-tell action the owner did not read before its undo window closed
(rule B/2: the series only counts an act-then-tell action the owner marked as seen; one left unread counts for
nothing, but its errors still ran unchecked). Their long-run share of the type's actions is the average outgoing quality
(AOQ) of Dodge's continuous sampling plan CSP-1 (1943), split in two numbers (audit of 19/11):

- unchecked errors, those no check ever saw. For an agent whose error rate ``p`` is stable,

      U(p) = p (1 - c),  c = f / (f + (1 - f) u),  u = (1 - d p)^N,

  where ``c`` is the long-run share of checked actions and ``d`` = DETECTION the chance that a check catches an
  error (an error a check misses passes as a success, so the series is longer to clear). U rises then falls to 0:
  its maximum over ``p`` is a true AOQL (``aoql``), the guarantee shown for that N; with d = 1 it is Dodge's;
- missed errors, those a check saw and a person let through: at most ``1 - d`` of the errors checked (``missed``),
  the study's assumption, not a measure. It grows with ``p`` (a very wrong agent is checked almost always), so it is
  shown apart, as the limit of the owner's attention, never folded into one number.

For an agent that turns bad once it acts alone and errs on every action from then on, the unchecked share is
``(1 - f) / (f d N + 1)`` of its actions until the first caught error, as a ratio of expectations (``worst_case``).
Neither covers the act-then-tell actions nobody marked as seen: they run unchecked and count for nothing.
"""
from __future__ import annotations

import math
from fractions import Fraction
from functools import lru_cache

# Recommendations shown by `/tenure setup`: accepted share of errors that run without approval, per stakes level.
# None = capped: the type always asks, whatever its record.
PRESETS = {
    "careful": {"low": 1 / 100, "medium": 1 / 200, "high": 1 / 1000},
    "balanced": {"low": 1 / 50, "medium": 1 / 100, "high": None},
    "fast": {"low": 1 / 20, "medium": 1 / 50, "high": None},
}
DEFAULT_PRESET = "balanced"
STARTS = ("trusted", "probation")   # trusted: no ask before a type's first fault; probation: the study's T1 start
DEFAULT_START = "trusted"
# Asks that the owner may silence for the rest of a session ("Allow for this session") under the trusted start: code
# run inline and shell constructs read as complex. Each answer is the owner's, never evidence; a new session asks again.
SESSION_TYPES = frozenset({"shell:python:inline", "shell:python3:inline", "shell:node:inline", "shell:stdin-code",
                           "shell:complex"})
# What the trusted start covers: files and memory (with an undo where files are written), handing work to a subagent,
# and the usual local development tools. Any other program (a deploy, payment or database CLI, an unknown tool,
# deleting files) asks under the study rule from the start, whatever the start mode.
TRUSTED_TYPES = ("file:write", "file:write-outside", "file:shell", "memory:write", "delegate:task")
# Subcommands that leave the machine are never covered, whatever classify made of them (e.g. `bun publish`).
UNTRUSTED_VERBS = frozenset({"publish", "deploy", "unpublish", "yank", "login", "logout", "adduser", "token", "owner",
                             "dist-tag", "deprecate", "send-email", "upload", "release", "push", "discard",
                             "remote", "dcommit", "imap-send", "uploadarchives", "perform", "x", "dlx",
                             "new-dependency"})
TRUSTED_PROGRAMS = frozenset({
    "npm", "pnpm", "yarn", "bun", "node", "deno", "tsc", "eslint", "prettier", "jest", "vitest",
    "python", "python3", "pytest", "uv", "poetry", "pip", "pip3", "ruff", "black", "mypy", "isort",
    "cargo", "rustc", "go", "make", "cmake", "gradle", "mvn", "swift", "dotnet",
    "git", "mkdir", "touch", "cd", "pushd", "popd", "export", "sleep", "set", "lsof", "chmod",
})
DEFAULT_SPOT = 0.1          # one cleared action in ten still asks
LEVELS = ("low", "medium", "high")


# Detection rate of the preregistered earned-autonomy study; series length N = ceil(1 / (DETECTION * bar)) - 1.
DETECTION = Fraction(95, 100)
# Wald sequential test for the middle tier: (pb, pm) = (acceptable, unacceptable) error rate per stakes.
WALD = {"low": (0.10, 0.30), "medium": (0.05, 0.20)}
ALPHA = BETA = 0.05


@lru_cache(maxsize=512)
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


def aoq(p: float, i: int, spot: float, d: float = float(DETECTION)) -> float:
    """Unchecked errors of CSP-1 in the long run, for a stable error rate ``p``, a check catching an error with
    probability ``d``: ``p (1 - c)``, ``c`` the share of checked actions. ``d`` = 1 is Dodge's AOQ."""
    u = (1 - d * p) ** i
    return p * (1 - spot) * u / (spot + (1 - spot) * u)


def missed(d: float = float(DETECTION)) -> float:
    """The share of the errors a check sees that a person lets through: the study's assumption, not a measure."""
    return 1 - d


@lru_cache(maxsize=4096)
def aoql(i: int, spot: float, d: float = float(DETECTION)) -> tuple[float, float]:
    """(AOQL, the stable error rate that reaches it): the maximum of the unchecked errors ``aoq`` over ``p``. It is
    unimodal on (0, 1): golden-section search."""
    if spot >= 1:
        return 0.0, 0.0
    lo, hi = 0.0, 1.0
    g = (math.sqrt(5) - 1) / 2
    a, b = hi - g * (hi - lo), lo + g * (hi - lo)
    fa, fb = aoq(a, i, spot, d), aoq(b, i, spot, d)
    for _ in range(200):
        if fa < fb:
            lo, a, fa = a, b, fb
            b = lo + g * (hi - lo)
            fb = aoq(b, i, spot, d)
        else:
            hi, b, fb = b, a, fa
            a = hi - g * (hi - lo)
            fa = aoq(a, i, spot, d)
    p = (lo + hi) / 2
    return aoq(p, i, spot, d), p


def worst_case(i: int, spot: float, d: float = float(DETECTION)) -> float:
    """Share of the actions that are errors no check saw, for an agent that turns bad once cleared and errs on every
    action from then on, until its first caught error (a ratio of expectations): T3 then lasts 1 / (f d) actions."""
    return (1 - spot) / (spot * d * i + 1)


def describe(preset_or_risks, spot: float = DEFAULT_SPOT) -> dict:
    """Per stakes level: accepted risk, series length N, guarantee (aoql) and worst case for that N, or capped."""
    risks = PRESETS[preset_or_risks] if isinstance(preset_or_risks, str) else dict(preset_or_risks)
    out = {}
    for level in LEVELS:
        n = required_n(risks, level)
        if n is None:
            out[level] = dict(risk=None, capped=True, n=None, aoql=None, worst_case=None, missed=None)
            continue
        g = aoql(n, spot)[0]
        out[level] = dict(risk=risks[level], capped=False, n=n, aoql=g, worst_case=worst_case(n, spot), missed=missed())
    return out


def trust_covers(key: str) -> bool:
    """The kinds of action the trusted start may cover: ``TRUSTED_TYPES``, a shell program of ``TRUSTED_PROGRAMS``
    (a package runner only for a covered program), never a key carrying one of ``UNTRUSTED_VERBS``."""
    if key in TRUSTED_TYPES:
        return True
    parts = key.split(":")
    if any(p in UNTRUSTED_VERBS for p in parts[2:]):
        return False
    if len(parts) >= 4 and parts[0] == "shell" and parts[2] == "exec":
        return parts[3] in TRUSTED_PROGRAMS
    if len(parts) >= 3 and parts[:2] == ["shell", "npx"]:
        return parts[2] in TRUSTED_PROGRAMS                  # npx runs a package: covered only for a covered tool
    return len(parts) >= 2 and parts[0] == "shell" and parts[1] in TRUSTED_PROGRAMS
