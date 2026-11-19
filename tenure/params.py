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
(AOQ) of Dodge's continuous sampling plan CSP-1 (1943). For an agent whose error rate ``p`` is stable,

    AOQ(p) = p [(1 - c) + (1 - d) c],  c = f / (f + (1 - f) u),  u = (1 - d p)^N,

where ``c`` is the long-run share of checked actions and ``d`` = DETECTION the chance that a check catches an error
(an error a check misses passes as a success): the same assumption as the series length, so the guarantee shown is
the one the study's N gives under it, not Dodge's perfect inspection (d = 1). Its peak (``aoql``: its first maximum in ``p``; above, very wrong agents are checked almost always and only what a
person misses leaves) is the AOQL,
the guarantee shown to users for that N (``aoql``). For an agent that changes once it acts alone and errs only where
it is not checked, the share is at most ``(1 - f d) / (f d N + 1)`` until the first caught error (``worst_case``).
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
    """Average outgoing quality of CSP-1 when a check catches an error with probability ``d`` (the study's 0.95): an
    error missed by a check passes as a success and leaves too. ``d`` = 1 is Dodge's perfect inspection."""
    u = (1 - d * p) ** i
    checked = spot / (spot + (1 - spot) * u)          # the share of actions that are checked, in the long run
    return p * ((1 - checked) + (1 - d) * checked)


@lru_cache(maxsize=4096)
def aoql(i: int, spot: float) -> tuple[float, float]:
    """(AOQL, the stable error rate that reaches it): the peak of AOQ where the agent passes as good often enough to
    act alone, its first local maximum. With d < 1, AOQ rises again for very wrong agents, towards (1 - d) p: nearly
    every action is checked and what leaves is the share a person misses, the limit of their attention and not of the
    autonomy (an agent that wrong is refused too often to keep any tier). A geometric scan finds the first descent,
    then a golden-section search the peak."""
    if spot >= 1:
        return 0.0, 0.0
    prev2, prev, p = 0.0, 1e-6, 1e-6 * 1.02
    while p < 1 and aoq(p, i, spot) >= aoq(prev, i, spot):
        prev2, prev, p = prev, p, p * 1.02
    lo, hi = prev2, min(p, 1.0)
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


def worst_case(i: int, spot: float, d: float = float(DETECTION)) -> float:
    """Share of errors that run unchecked for an agent that turns bad once cleared, until its first caught error: a
    check catches it with probability ``d``, and an error a check misses runs too."""
    return (1 - spot * d) / (spot * d * i + 1)


def describe(preset_or_risks, spot: float = DEFAULT_SPOT) -> dict:
    """Per stakes level: accepted risk, series length N, guarantee (aoql) and worst case for that N, or capped."""
    risks = PRESETS[preset_or_risks] if isinstance(preset_or_risks, str) else dict(preset_or_risks)
    out = {}
    for level in LEVELS:
        n = required_n(risks, level)
        if n is None:
            out[level] = dict(risk=None, capped=True, n=None, aoql=None, worst_case=None)
            continue
        g = aoql(n, spot)[0]
        out[level] = dict(risk=risks[level], capped=False, n=n, aoql=g, worst_case=worst_case(n, spot))
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
