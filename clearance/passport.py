# Copyright 2026 Otsoa Dubief
# SPDX-License-Identifier: Apache-2.0
"""The autonomy passport: what an agent has earned, per action type, in a signed and tamper-evident JSON that anyone
can check again by replaying the ledger (Earned Autonomy Protocol v0.1, ``docs/protocol.md``).

``replay`` is the single reading of the ledger contract of ``store``: it applies the input events (settings,
outcome, agent, revoke) in ledger order with the functions of ``rule``, exactly as the hooks do, and must find the
states the hooks recorded. ``build`` writes the passport of one agent from the recorded states, ``verify`` checks
its signature, then the ledger's hash chain, then recomputes every type by replay.

What it proves, and what it does not: the owner holds the signing key and could build a whole new history and sign
it. A third party detects a change to a passport or a ledger once published (the signature, the chain, the head
anchored with ``anchor_line``), not a complete rewrite by its author.

Type names can carry names taken from the arguments (a script, a make target, an npm script). By default, ``build``
replaces every type segment after the program and its subcommand by the first 8 hex digits of its sha256
(``redact_type``). ``verify`` applies the same function to the replayed states, so a redacted passport verifies with
the plain ledger. The hash is not salted: it hides a name from a casual reader, not from someone who guesses it.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from fractions import Fraction

from . import benchmarks, classify, params, personal, rule, store

PROTOCOL = "earned-autonomy/0.1"
RULE_NAME = "study-rule-B"
KEY_FILE = "passport-ed25519.pem"
TYPE_FIELDS = ("type", "stakes", "tier", "series", "required", "sessions", "provisional", "guarantee")
KEPT_WORDS = frozenset({"inline", "default"})       # fixed words of classify, never taken from an argument


def _canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ------------------------------------------------------------------------------------------------------- rule
def rule_spec() -> dict:
    """Every number the rule's decisions depend on, with its version."""
    return {"version": rule.VERSION, "DETECTION": str(Fraction(params.DETECTION)),
            "WALD": {k: list(v) for k, v in sorted(params.WALD.items())}, "ALPHA": params.ALPHA,
            "BETA": params.BETA, "lengthen": rule.LENGTHEN, "trial": rule.TRIAL, "wait": rule.WAIT,
            "sessions": rule.SESSIONS, "carry": rule.CARRY, "veto": benchmarks.VETO_MARGIN}


def rule_fingerprint() -> str:
    """sha256 of the canonical JSON of ``rule_spec()``."""
    return _sha(_canon(rule_spec()))


def settings_fingerprint(event: dict | None) -> str | None:
    """sha256 of a ``settings`` ledger event's canonical JSON (the settings a replay uses), or None."""
    if event is None:
        return None
    return _sha(_canon({k: event.get(k) for k in ("event", "risks", "spot", "strict", "rule")}))


# ------------------------------------------------------------------------------------------------------ replay
def _replay(rows: list[dict]) -> tuple[dict[tuple[str, str], rule.TypeState], dict | None]:
    """States by (agent, type), and the last settings event. Mirrors the hooks of ``clearance/__init__.py``:

    - settings (``sync_settings``): ``rule.reevaluate`` on every type of every agent known so far (R23);
    - outcome (``record_outcome``): ``rule.rebase`` when the recorded stakes differ, then the event's stakes and
      reversibility, ``on_success`` / ``on_fault`` / ``on_neutral``, then ``rule.count_action`` for a COUNTED
      outcome unless that fault failed the trial (R17);
    - agent (``_carry``): ``rule.carry_over`` for every type of ``old`` that ``new`` has no state for (R24);
    - revoke (``cli.revoke``): ``rule.revoke``.

    Derived events are skipped. Raises ValueError on an unknown event, an outcome before any settings, or settings
    of another rule."""
    cfg, states = None, {}
    for i, r in enumerate(rows, 1):
        e = r.get("event") or {}
        kind = e.get("event")
        if kind in store.DERIVED_KINDS:
            continue
        if kind not in store.INPUT_KINDS:
            raise ValueError(f"row {i}: unknown ledger event {kind!r}")
        if kind == "settings":
            if e.get("rule") != rule.VERSION:
                raise ValueError(f"row {i}: settings of rule {e.get('rule')!r}, this replay knows {rule.VERSION!r}")
            cfg = e
            for s in states.values():
                rule.reevaluate(s, params.required_n(cfg["risks"], s.stakes))
            continue
        if cfg is None:
            raise ValueError(f"row {i}: a {kind} event before any settings event")
        if kind == "outcome":
            key = (e["agent"], e["type"])
            s = states.get(key)
            if s is None:
                s = rule.TypeState(key=e["type"], stakes=e["stakes"], reversible=bool(e["reversible"]))
            elif s.stakes != e["stakes"]:
                rule.rebase(s)                                   # evidence counts only at the stakes it was earned at
            s.stakes, s.reversible = e["stakes"], bool(e["reversible"])
            n = params.required_n(cfg["risks"], e["stakes"])
            result, source = e["result"], e["source"]
            if source not in store.OUTCOME_SOURCES.get(result, ()):
                raise ValueError(f"row {i}: unknown outcome {result!r} from {source!r}")
            if result == "success":
                events = rule.on_success(s, n, session=e.get("session", ""), source=source)
            elif result == "fault":
                events = rule.on_fault(s, n, session=e.get("session", ""), source=source)
            else:
                events = rule.on_neutral(s, source)
            failed = any(v["event"] == "trial" and v.get("reason") == "failed" for v in events)
            if (result, source) in store.COUNTED and not failed:
                rule.count_action(s)
            states[key] = s
        elif kind == "agent":
            have = {k for (a, k) in states if a == e["new"]}
            vetoed = set(e.get("vetoed") or ())
            for (a, k), s in sorted(states.items()):
                if a == e["old"] and k not in have:
                    states[(e["new"], k)] = rule.carry_over(s, n_new=params.required_n(cfg["risks"], s.stakes),
                                                            veto=k in vetoed, strict=e["mode"] == "strict")
        elif kind == "revoke":
            s = states.get((e["agent"], e["type"]))
            if s is None:
                raise ValueError(f"row {i}: revoke of {e['type']} for {e['agent']}, which has no record")
            rule.revoke(s)
    return states, cfg


def replay(rows: list[dict]) -> dict[str, dict[str, rule.TypeState]]:
    """The states the ledger's input events lead to, by agent then type. Compare them without ``changed_at``."""
    out: dict[str, dict[str, rule.TypeState]] = {}
    for (agent, key), s in sorted(_replay(rows)[0].items()):
        out.setdefault(agent, {})[key] = s
    return out


# --------------------------------------------------------------------------------------------------- redaction
def redact_type(key: str) -> str:
    """Hash the segments of a type taken from the arguments: everything after the program and its subcommand.

    ``shell:npm:run:build`` -> ``shell:npm:run:<sha8>``, ``shell:python3:deploy.py`` -> ``shell:python3:<sha8>``,
    ``shell:python3:-m:pytest`` -> ``shell:python3:-m:<sha8>``. A segment after a script runner (shells,
    interpreters, npx, make and its kin) is a name from the arguments; any segment beyond the third is too. Other
    namespaces (file, memory, mcp...) carry no argument and stay as they are."""
    parts = key.split(":")
    if len(parts) < 3 or parts[0] != "shell":
        return key
    prog = parts[1]
    base = re.sub(r"\d+(\.\d+)*$", "", prog)
    runs_scripts = (prog in classify.SHELLS or prog in classify.INTERPRETERS or base in classify.INTERPRETERS
                    or prog == "npx" or prog in classify.MAKES)
    keep = 3 if len(parts) > 3 or not runs_scripts else 2
    out = parts[:keep] + [p if p in KEPT_WORDS and i == 2 else _sha(p)[:8] for i, p in enumerate(parts[keep:], keep)]
    return ":".join(out)


# ---------------------------------------------------------------------------------------------------- passport
def _entries(states: dict[str, rule.TypeState], cfg: dict | None, redact: bool) -> list[dict]:
    risks = (cfg or {}).get("risks") or {}
    spot = (cfg or {}).get("spot", params.DEFAULT_SPOT)
    out = {}
    for key, s in states.items():
        n = params.required_n(risks, s.stakes) if cfg else None
        name = redact_type(key) if redact else key
        if name in out:
            raise ValueError(f"two types redact to {name}")
        out[name] = {"type": name, "stakes": s.stakes, "tier": s.tier, "series": s.series,
                     "required": None if n is None else rule.required(s, n), "sessions": len(s.sessions),
                     "provisional": s.provisional, "guarantee": rule.guarantee(s, n, spot)}
    return [out[k] for k in sorted(out)]


def keypair(data_dir: str) -> tuple[object | None, str | None]:
    """(Ed25519 private key, public key in hex), created at first use in ``data_dir`` with mode 0600; (None, None)
    when ``cryptography`` cannot be imported."""
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    except Exception:
        return None, None
    os.makedirs(data_dir, exist_ok=True)
    path = os.path.join(data_dir, KEY_FILE)
    try:
        key = Ed25519PrivateKey.generate()
        pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption())
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(pem)
    except FileExistsError:
        with open(path, "rb") as f:
            key = serialization.load_pem_private_key(f.read(), password=None)
    if os.name == "posix":
        os.chmod(path, 0o600)
    raw = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return key, raw.hex()


def _payload(passport: dict) -> bytes:
    return _canon({k: v for k, v in passport.items() if k != "signature"}).encode("utf-8")


def sign(passport: dict, key) -> str:
    """Hex Ed25519 signature over the canonical JSON of the passport without its ``signature`` field."""
    return key.sign(_payload(passport)).hex()


def _head(rows: list[dict]) -> str:
    return rows[-1]["hash"] if rows else store.GENESIS


def _last_settings(rows: list[dict]) -> dict | None:
    return next((r["event"] for r in reversed(rows) if r["event"].get("event") == "settings"), None)


def build(st, agent: str, settings: dict, data_dir: str, redact: bool = True) -> dict:
    """The passport of ``agent``: its recorded states, under the settings of the ledger's last settings event (the
    ones they were computed with; ``settings`` only stands in before the first one, and names the profile with its
    optional ``profile`` key, else the Hermes home holding ``data_dir``), signed when a key is available."""
    rows = st.ledger()
    cfg = _last_settings(rows)
    if cfg is None and settings:
        cfg = {"event": "settings", "risks": dict(settings.get("risks") or {}),
               "spot": settings.get("spot", params.DEFAULT_SPOT), "strict": bool(settings.get("strict")),
               "rule": rule.VERSION}
    model, provider = personal.split_agent(agent)
    profile = str((settings or {}).get("profile")
                  or os.path.basename(os.path.dirname(os.path.dirname(os.path.abspath(data_dir)))) or "default")
    p = {"protocol": PROTOCOL,
         "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
         "agent": {"model": model, "provider": provider, "profile": _sha(profile)[:12]},
         "rule": {"name": RULE_NAME, "fingerprint": rule_fingerprint()},
         "settings_fingerprint": settings_fingerprint(cfg),
         "redacted": bool(redact),
         "types": _entries({s.key: s for _, s in st.states(agent)}, cfg, redact),
         "ledger": {"count": len(rows), "head": _head(rows)}}
    key, public = keypair(data_dir)
    p["public_key"] = public
    p["signature"] = None if key is None else sign(p, key)
    return p


def _check_signature(passport: dict) -> list[str]:
    sig, pub = passport.get("signature"), passport.get("public_key")
    if not sig or not pub:
        return ["unsigned"]
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except Exception:
        return ["signature not checked: the cryptography library is not installed"]
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(pub)).verify(bytes.fromhex(sig), _payload(passport))
    except (InvalidSignature, ValueError):
        return ["signature does not match the passport's content"]
    return []


def verify(passport: dict, rows: list[dict] | None = None) -> list[str]:
    """Problems found, in order: signature, rule, then with ``rows``: the hash chain, the passport's place in it, and
    every type recomputed by replay of the first ``ledger.count`` rows. An empty list means everything checks; an
    unsigned passport that is otherwise right gives ``["unsigned"]``. A ledger longer than the passport's count is
    fine: the passport describes the ledger as it was then."""
    problems = _check_signature(passport)
    if passport.get("protocol") != PROTOCOL:
        problems.append(f"protocol {passport.get('protocol')!r}, expected {PROTOCOL!r}")
    if (passport.get("rule") or {}).get("fingerprint") != rule_fingerprint():
        problems.append("rule fingerprint differs from this plugin's rule: the replay below may not apply")
    if rows is None:
        return problems
    problems += [f"ledger: {p}" for p in store.verify(rows)]
    led = passport.get("ledger") or {}
    count = led.get("count")
    if not isinstance(count, int) or count < 0 or count > len(rows):
        return problems + [f"ledger: the passport counts {count} events, the ledger has {len(rows)}"]
    head = _head(rows[:count])
    if led.get("head") != head:
        problems.append(f"ledger: head {led.get('head')} in the passport, {head} at event {count}")
    try:
        states, cfg = _replay(rows[:count])
    except (KeyError, TypeError, ValueError) as exc:
        return problems + [f"replay: {exc}"]
    if passport.get("settings_fingerprint") != settings_fingerprint(cfg):
        problems.append("settings fingerprint differs from the ledger's last settings")
    agent = passport.get("agent") or {}
    name = f"{agent.get('model')}@{agent.get('provider') or 'unknown'}"
    mine = {k: s for (a, k), s in states.items() if a == name}
    try:
        expected = {e["type"]: e for e in _entries(mine, cfg, bool(passport.get("redacted")))}
    except ValueError as exc:
        return problems + [f"replay: {exc}"]
    claimed = {e.get("type"): e for e in passport.get("types") or []}
    for key in sorted(set(expected) | set(claimed), key=str):
        if key not in claimed:
            problems.append(f"type {key}: found by replay, missing from the passport")
        elif key not in expected:
            problems.append(f"type {key}: in the passport, not found by replay")
        else:
            for f in TYPE_FIELDS[1:]:
                if claimed[key].get(f) != expected[key][f]:
                    problems.append(f"type {key}: {f} {claimed[key].get(f)!r} in the passport, "
                                    f"{expected[key][f]!r} by replay")
    return problems


def anchor_line(st) -> str:
    """One line to publish anywhere (a post, a gist): the ledger's head, its date and its length."""
    row = st.db.execute("SELECT at, hash FROM ledger ORDER BY seq DESC LIMIT 1").fetchone()
    count = st.db.execute("SELECT COUNT(*) FROM ledger").fetchone()[0]
    at, head = (row[0], row[1]) if row else (time.time(), store.GENESIS)
    return (f"clearance ledger head {head} at {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(at))} "
            f"({count} events)")
