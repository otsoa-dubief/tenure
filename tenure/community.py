# Copyright 2026 Otsoa Dubief
# SPDX-License-Identifier: Apache-2.0
"""The community benchmark, opt-in: a signed record of counts the owner writes and publishes himself, and the board
an aggregator builds from many records (``docs/community.md``).

Nothing here touches the network. ``share_record`` reads the store and returns a dict; the CLI writes it to a file
in the current folder, and the owner decides whether to publish it. ``aggregate`` runs on the community side
(``scripts/aggregate_community.py``): it checks every signature, keeps one record per public key (the latest), and
sums the counts. ``load_board`` reads a board the owner downloaded into the plugin's data folder; with none, the
dashboard says so.

What a record carries, and nothing else: per model (model id and provider, as Hermes reports them) and per action
FAMILY (``family``: a coarse name from tenure's fixed vocabulary, never a segment taken from a command), the
verified successes and faults; the date (no time); the tenure version, the rule version, the preset and its risks;
the profile's passport public key and an Ed25519 signature over the rest.
"""
from __future__ import annotations

import json
import math
import os
import re
import time

from . import classify, passport, personal, rule

FORMAT = "tenure-community/1"
BOARD_FORMAT = "tenure-community-board/1"
BOARD_FILE = "community-board.json"
REPO = "otsoa-dubief/tenure-community"
RECORD_KEYS = ("format", "date", "tenure", "rule", "preset", "risks", "rows", "public_key", "signature")
ROW_KEYS = ("model", "provider", "family", "successes", "faults")
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
NAME = re.compile(r"[^\x00-\x1f\x7f]{1,120}")
HEX64, HEX128 = re.compile(r"[0-9a-f]{64}"), re.compile(r"[0-9a-f]{128}")

# Non-shell types classify writes from its own fixed words (tenure/classify.py); any other type keeps its namespace
# when that namespace is known, else becomes "other".
FIXED_TYPES = frozenset({
    "bot:message", "browser:cdp", "browser:dialog", "browser:exec", "code:execute", "computer:use", "cron:manage",
    "delegate:task", "discord:admin", "feishu:comment", "file:sensitive", "file:unknown", "file:unreadable",
    "file:write-outside", "file:write", "media:generate", "memory:write", "message:react", "message:send",
    "process:manage", "schedule:at", "schedule:crontab", "schedule:launchctl", "secrets:vault", "self:connections",
    "self:env", "self:hermes", "self:plugins", "self:skills", "self:tenure", "tool:unreadable-args",
} | {t for t, _, _ in classify.TOOLS.values()})
# Namespaces whose later segments are a server, a tool or a board name: only the namespace is shared.
NAMESPACES = frozenset({t.split(":")[0] for t in FIXED_TYPES} | {"mcp", "tool", "kanban", "read"})


def _set(name: str) -> set:
    v = getattr(classify, name, ())
    return set(v.keys() if isinstance(v, dict) else v)


# Programs whose name tenure knows (classify's own lists, and the tools whose subcommands it reads); a program not in
# it may be a script of the owner's run directly (``shell:deploy.sh``): it is shared as ``shell:other``.
PROGRAMS = frozenset(set().union(*(_set(n) for n in (
    "READ_ONLY", "SHELLS", "INTERPRETERS", "MAKES", "FILE_PROGS", "PATH_PROGS", "ELSEWHERE_PROGS", "SEPARATOR_PROGS",
    "EXTERNAL_PROGRAMS", "HERMES_PROGS", "PROGRAM_RUNNERS", "CLOUD", "OUTSIDE", "WRAPPERS"))) | {
    p for p, _ in classify.PUBLISH} | {
    # fixed words classify puts in the program's place
    "complex", "dynamic", "env", "eval", "find", "ftp", "mail", "nc", "nested", "parallel", "rsync", "scp", "sftp",
    "ssh", "stdin-code", "unknown", "watch", "wget", "xargs", "run",
    # tools whose subcommand tenure reads
    "git", "gh", "npm", "pnpm", "yarn", "bun", "cargo", "pip", "pip3", "uv", "docker", "podman", "kubectl",
    "terraform", "aws", "gcloud", "az", "twine", "gem", "go", "brew", "curl", "tar", "zip", "mkdir", "hermes"})
# Programs that run a script or a target: what follows them is a name of the owner's, never shared.
RUNNERS = frozenset(_set("SHELLS") | _set("INTERPRETERS") | _set("MAKES") | {"npx", "exec", "run"})


def family(key: str) -> str:
    """The coarse family of an action type, from fixed words only.

    ``shell:git:commit`` stays; ``shell:npm:run:build`` -> ``shell:npm:run``; ``shell:python3:deploy.py`` ->
    ``shell:python3``; ``shell:deploy.sh`` -> ``shell:other``; ``mcp:notion:create_page`` -> ``mcp``;
    ``file:write`` stays. Applying it twice changes nothing."""
    parts = str(key).split(":")
    ns = parts[0]
    if ns == "shell":
        if len(parts) < 2:
            return "shell:other"
        prog = parts[1]
        base = re.sub(r"\d+(\.\d+)*$", "", prog)
        if prog not in PROGRAMS:
            if base in _set("INTERPRETERS"):
                prog = base
            else:
                return "shell:other"
        if prog in RUNNERS or base in RUNNERS or len(parts) < 3 or parts[2] not in passport.SUBCOMMANDS:
            return f"shell:{prog}"
        return f"shell:{prog}:{parts[2]}"
    if key in FIXED_TYPES:
        return key
    return ns if ns in NAMESPACES else "other"


def _version() -> str:
    """tenure's version, from the plugin manifest beside this file."""
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "plugin.yaml"), encoding="utf-8") as f:
            m = re.search(r"^version:\s*([^\s#]+)", f.read(), re.M)
        return m.group(1) if m else "unknown"
    except OSError:
        return "unknown"


def _risks(settings: dict) -> dict:
    out = {}
    for level in ("low", "medium", "high"):
        v = (settings.get("risks") or {}).get(level)
        out[level] = None if v is None else float(v)
    return out


PATHLIKE = re.compile(r"^[/~.]|\\|^[A-Za-z]:|://")


def model_name(model: str) -> str:
    """The model id as shared: a local file path (a model loaded from disk) becomes ``local-model``."""
    return "local-model" if PATHLIKE.search(model) else model


def counts(st) -> list[dict]:
    """Verified successes and faults per (model, provider, family), from the store's states; rows without any check
    are left out."""
    sums: dict[tuple[str, str, str], list[int]] = {}
    for agent, s in st.states():
        if s.successes + s.faults <= 0:
            continue
        model, provider = personal.split_agent(agent)
        c = sums.setdefault((model_name(model), model_name(provider), family(s.key)), [0, 0])
        c[0] += s.successes
        c[1] += s.faults
    return [{"model": m, "provider": p, "family": f, "successes": c[0], "faults": c[1]}
            for (m, p, f), c in sorted(sums.items())]


def _payload(d: dict) -> bytes:
    return passport._canon({k: v for k, v in d.items() if k != "signature"}).encode("utf-8")


def share_record(st, settings: dict, data_dir: str, today: str | None = None) -> dict:
    """The signed record of this profile. Raises RuntimeError when no signing key is available (an unsigned record
    would be dropped by every aggregator)."""
    rec = {"format": FORMAT, "date": today or time.strftime("%Y-%m-%d", time.gmtime()), "tenure": _version(),
           "rule": rule.VERSION, "preset": str((settings or {}).get("preset") or "custom"),
           "risks": _risks(settings or {}), "rows": counts(st)}
    key, public = passport.keypair(data_dir)
    if key is None:
        raise RuntimeError("the cryptography package is missing: the record cannot be signed")
    rec["public_key"] = public
    rec["signature"] = key.sign(_payload(rec)).hex()
    return rec


def verify_record(d) -> list[str]:
    """Problems with a record: its shape, its vocabulary (every family must be a coarse one), its signature."""
    if not isinstance(d, dict):
        return ["not a JSON object"]
    problems = []
    if tuple(sorted(d)) != tuple(sorted(RECORD_KEYS)):
        problems.append(f"keys must be exactly {', '.join(RECORD_KEYS)}")
    if d.get("format") != FORMAT:
        problems.append(f"format must be {FORMAT}")
    if not (isinstance(d.get("date"), str) and DATE.fullmatch(d["date"])):
        problems.append("date must be YYYY-MM-DD")
    for k in ("tenure", "rule", "preset"):
        if not (isinstance(d.get(k), str) and NAME.fullmatch(d[k])):
            problems.append(f"{k} must be a short text")
    risks = d.get("risks")
    if not (isinstance(risks, dict) and set(risks) == {"low", "medium", "high"}
            and all(v is None or (isinstance(v, (int, float)) and not isinstance(v, bool) and 0 < v < 1)
                    for v in risks.values())):
        problems.append("risks must give low, medium and high, each a rate or null")
    rows = d.get("rows")
    if not isinstance(rows, list):
        problems.append("rows must be a list")
        rows = []
    seen = set()
    for i, r in enumerate(rows, 1):
        if not (isinstance(r, dict) and tuple(sorted(r)) == tuple(sorted(ROW_KEYS))):
            problems.append(f"row {i}: keys must be exactly {', '.join(ROW_KEYS)}")
            continue
        if not all(isinstance(r[k], str) and NAME.fullmatch(r[k]) for k in ("model", "provider", "family")):
            problems.append(f"row {i}: model, provider and family must be short texts")
            continue
        if model_name(r["model"]) != r["model"] or model_name(r["provider"]) != r["provider"]:
            problems.append(f"row {i}: a model or provider that looks like a file path")
        if family(r["family"]) != r["family"]:
            problems.append(f"row {i}: {r['family']!r} is not a coarse action family")
        if not all(isinstance(r[k], int) and not isinstance(r[k], bool) and r[k] >= 0 for k in ("successes", "faults")):
            problems.append(f"row {i}: successes and faults must be whole numbers")
        ident = (r["model"], r["provider"], r["family"])
        if ident in seen:
            problems.append(f"row {i}: duplicate of an earlier row")
        seen.add(ident)
    pub, sig = d.get("public_key"), d.get("signature")
    if not (isinstance(pub, str) and HEX64.fullmatch(pub) and isinstance(sig, str) and HEX128.fullmatch(sig)):
        problems.append("unsigned, or the key or signature is not hex of the right length")
        return problems
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except Exception:
        return problems + ["signature not checked: the cryptography library is not installed"]
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(pub)).verify(bytes.fromhex(sig), _payload(d))
    except (InvalidSignature, ValueError, TypeError):
        problems.append("signature does not match the record's content")
    return problems


def latest_per_key(records: list) -> tuple[list[dict], int]:
    """Valid records, one per public key (the latest date; on a tie, the last one given), and how many were
    dropped as invalid."""
    best: dict[str, dict] = {}
    dropped = 0
    for d in records:
        if verify_record(d):
            dropped += 1
            continue
        old = best.get(d["public_key"])
        if old is None or d["date"] >= old["date"]:
            best[d["public_key"]] = d
    return [best[k] for k in sorted(best)], dropped


def aggregate(records: list, today: str | None = None) -> dict:
    """The board: per family, per model, the contributors (distinct keys), verified successes and faults, and the
    Wilson 95% interval of the fault rate. Models are ranked by the top of that interval (most reliable first)."""
    kept, dropped = latest_per_key(records)
    cells: dict[tuple[str, str, str], dict] = {}
    for d in kept:
        for r in d["rows"]:
            c = cells.setdefault((r["family"], r["model"], r["provider"]), {"keys": set(), "successes": 0, "faults": 0})
            c["keys"].add(d["public_key"])
            c["successes"] += r["successes"]
            c["faults"] += r["faults"]
    fams: dict[str, list[dict]] = {}
    for (fam, model, provider), c in cells.items():
        n = c["successes"] + c["faults"]
        if n <= 0:
            continue
        low, high = personal.wilson(c["faults"], n)
        fams.setdefault(fam, []).append({
            "model": model, "provider": provider, "contributors": len(c["keys"]), "successes": c["successes"],
            "faults": c["faults"], "checks": n, "rate": c["faults"] / n, "low": low, "high": high})
    families = []
    for fam in sorted(fams):
        rows = sorted(fams[fam], key=lambda r: (r["high"], -r["checks"], r["model"], r["provider"]))
        families.append({"family": fam, "models": rows})
    return {"format": BOARD_FORMAT, "generated": today or time.strftime("%Y-%m-%d", time.gmtime()),
            "records": len(kept), "dropped": dropped, "families": families}


def load_board(path: str) -> dict | None:
    """A board the owner downloaded, or None when there is none or it is not a board."""
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return None
    if not (isinstance(d, dict) and d.get("format") == BOARD_FORMAT and isinstance(d.get("families"), list)):
        return None
    for fam in d["families"]:
        if not (isinstance(fam, dict) and isinstance(fam.get("family"), str) and isinstance(fam.get("models"), list)):
            return None
        for m in fam["models"]:
            if not isinstance(m, dict):
                return None
            for k in ("contributors", "successes", "faults", "checks", "low", "high"):
                v = m.get(k)
                if not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v):
                    return None
    return d


def board_path(data_dir: str) -> str:
    return os.path.join(data_dir, BOARD_FILE)
