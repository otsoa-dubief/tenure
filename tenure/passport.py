# Copyright 2026 Otsoa Dubief
# SPDX-License-Identifier: Apache-2.0
"""The autonomy passport: what an agent has earned, per action type, in a signed and tamper-evident JSON that anyone
can check again by replaying the ledger (Earned Autonomy Protocol v0.1, ``docs/protocol.md``).

``replay`` is the single reading of the ledger contract of ``store``: it applies the input events (settings,
outcome, agent, revoke) in ledger order with the functions of ``rule``, exactly as the hooks do, and must find the
states the hooks recorded. ``build`` writes the passport of one agent from the recorded states, ``verify`` checks
its structure and signature, then the ledger's hash chain, then recomputes every type by replay; without the
ledger it says the types were not checked.

What it proves, and what it does not: the owner holds the signing key and could build a whole new history and sign
it. A third party detects a change to a passport or a ledger once published (the signature, the chain, the head
anchored with ``anchor_line``), not a complete rewrite by its author.

Type names can carry names taken from the arguments (a script, a make target, an npm script, a git alias). By default,
``build`` replaces every type segment after the program and a known subcommand, and a third segment that is not a
known subcommand, by the first 8 hex digits of its sha256 (``redact_type``). ``verify`` applies the same function to the replayed states, so a redacted passport verifies with
the plain ledger. The hash is not salted: it hides a name from a casual reader, not from someone who guesses it.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
from fractions import Fraction

from . import benchmarks, classify, params, personal, rule, store

PROTOCOL = "earned-autonomy/0.1"
RULE_NAME = "study-rule-B"
KEY_FILE = "passport-ed25519.pem"
TYPE_FIELDS = ("type", "stakes", "tier", "effective_tier", "series", "required", "sessions", "provisional",
               "guarantee")
ROOT_KEYS = ("protocol", "generated_at", "agent", "rule", "settings_fingerprint", "redacted", "types", "ledger",
             "public_key", "signature")
PART_KEYS = {"agent": ("model", "provider", "profile"), "rule": ("name", "fingerprint"), "ledger": ("count", "head")}
NO_LEDGER = "ledger not provided: types not checked"
HEX64, HEX128 = re.compile(r"[0-9a-f]{64}"), re.compile(r"[0-9a-f]{128}")
RUNNER_WORDS = frozenset({"inline", "default", "-m"})   # fixed words classify puts after a script runner
# Subcommands that stay readable in a redacted type (``shell:<program>:<subcommand>``). Any other third segment, and
# every segment after it, is hashed: it may be a name of the user's (a git alias, a namespace, a script).
SUBCOMMANDS = frozenset(
    classify.GIT_READ | classify.KUBE_WRITE | {sub for _, sub in classify.PUBLISH} | {
        # fixed words of classify
        "run", "send", "api", "unknown", "default", "inline", "tenure", "version",
        # git
        "add", "commit", "pull", "merge", "rebase", "checkout", "switch", "branch", "tag", "remote", "reset",
        "restore", "stash", "clone", "init", "cherry-pick", "revert", "clean", "rm", "mv", "config", "worktree",
        "submodule", "bisect", "am", "apply", "push",
        # npm, pnpm, yarn, bun, cargo, pip
        "install", "i", "ci", "test", "remove", "uninstall", "update", "exec", "start", "build", "link", "pack",
        "audit", "version", "dlx", "check", "clippy", "fmt",
        # docker, podman
        "compose", "ps", "images", "rmi", "stop", "logs", "inspect", "network", "volume", "system", "login",
        # kubectl
        "get", "describe", "top", "explain", "port-forward", "label", "annotate", "api-resources", "cp", "auth",
        "wait", "diff", "kustomize", "set",
        # gh
        "pr", "issue", "repo", "release", "workflow", "gist", "secret", "variable", "search", "browse", "codespace",
        # terraform
        "plan", "validate", "output", "show", "state", "workspace", "refresh", "taint", "untaint", "providers",
        "graph", "console", "destroy", "import",
        # aws services
        "s3", "s3api", "ec2", "iam", "lambda", "sts", "cloudformation", "ecs", "ecr", "eks", "rds", "dynamodb", "sqs",
        "sns", "cloudwatch", "route53", "ssm", "secretsmanager", "kms", "cloudfront", "apigateway", "elbv2",
        "autoscaling", "configure", "sso",
        # gcloud groups
        "compute", "functions", "storage", "container", "projects", "sql", "app", "pubsub", "secrets", "artifacts",
        "builds", "dns", "logging", "services",
        # az groups
        "group", "vm", "webapp", "functionapp", "aks", "acr", "account", "keyvault", "resource", "ad", "role",
        "monitor",
    })


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


def settings_event_fingerprint(event: dict | None) -> str | None:
    """sha256 of a ``settings`` ledger event's canonical JSON (the settings a replay uses), or None."""
    if event is None:
        return None
    return _sha(_canon({k: event.get(k) for k in ("event", "risks", "spot", "strict", "rule")}))


# ------------------------------------------------------------------------------------------------------ replay
def _replay(rows: list[dict]) -> tuple[dict[tuple[str, str], rule.TypeState], dict | None]:
    """States by (agent, type), and the last settings event. Mirrors the hooks of ``tenure/__init__.py``:

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
            if e.get("mode") not in ("carry", "strict"):
                raise ValueError(f"row {i}: agent event with mode {e.get('mode')!r}, expected carry or strict")
            have = {k for (a, k) in states if a == e["new"]}
            vetoed = set(e.get("vetoed") or ())
            for (a, k), s in sorted(states.items()):
                if a == e["old"] and k not in have:
                    states[(e["new"], k)] = rule.carry_over(s, n_new=params.required_n(cfg["risks"], s.stakes),
                                                            veto=k in vetoed, strict=e["mode"] == "strict")
        elif kind == "copy":                                     # the record was copied into another profile
            if e.get("mode") not in ("carry", "strict"):
                raise ValueError(f"row {i}: copy event with mode {e.get('mode')!r}, expected carry or strict")
            for k, s in sorted(states.items()):
                states[k] = rule.carry_over(s, n_new=params.required_n(cfg["risks"], s.stakes), veto=False,
                                            strict=e["mode"] == "strict")
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
    """Hash the segments of a type that may be a name of the user's: everything after the program and a known
    subcommand.

    ``shell:npm:run:build`` -> ``shell:npm:run:<sha8>``, ``shell:python3:deploy.py`` -> ``shell:python3:<sha8>``,
    ``shell:kubectl:apply`` stays, ``shell:git:my-alias`` -> ``shell:git:<sha8>``. The third segment stays readable
    only when it is in ``SUBCOMMANDS`` (after a script runner, only one of classify's fixed words: ``inline``,
    ``default``, ``-m``); every later segment is hashed. Other namespaces (file, memory, mcp...) carry no argument
    and stay as they are; so does the program, even when it is a script run directly (``shell:deploy.sh``)."""
    parts = key.split(":")
    if len(parts) < 3 or parts[0] != "shell":
        return key
    prog = parts[1]
    base = re.sub(r"\d+(\.\d+)*$", "", prog)
    runs_scripts = (prog in classify.SHELLS or prog in classify.INTERPRETERS or base in classify.INTERPRETERS
                    or prog == "npx" or prog in classify.MAKES)
    known = parts[2] in (RUNNER_WORDS if runs_scripts else SUBCOMMANDS)
    if runs_scripts and parts[2] == "-m" and len(parts) == 3:
        known = False
    out = parts[:2] + [parts[2] if known else _sha(parts[2])[:8]] + [_sha(p)[:8] for p in parts[3:]]
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
        out[name] = {"type": name, "stakes": s.stakes, "tier": s.tier,
                     "effective_tier": rule.effective_tier(s, n, s.stakes), "series": s.series,
                     "required": None if n is None else rule.required(s, n), "sessions": len(s.sessions),
                     "provisional": s.provisional, "guarantee": rule.guarantee(s, n, spot)}
    return [out[k] for k in sorted(out)]


def keypair(data_dir: str) -> tuple[object | None, str | None]:
    """(Ed25519 private key, public key in hex), created at first use in ``data_dir`` with mode 0600; (None, None)
    when ``cryptography`` cannot be imported. A new key is written whole to a temporary file, then linked into place
    without replacing a key another process put there first; every caller then reads the one in place. A key file
    that cannot be read raises RuntimeError naming it: move it away and a new key is made."""
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    except Exception:
        return None, None
    os.makedirs(data_dir, exist_ok=True)
    path = os.path.join(data_dir, KEY_FILE)
    if not os.path.exists(path):
        pem = Ed25519PrivateKey.generate().private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                         serialization.NoEncryption())
        fd, tmp = tempfile.mkstemp(prefix=KEY_FILE + ".", dir=data_dir)      # mode 0600
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(pem)
                f.flush()
                os.fsync(f.fileno())
            try:
                os.link(tmp, path)                   # fails if a key is already there: never replaced
            except FileExistsError:
                pass
            except OSError:                          # no hard links on this file system
                if not os.path.exists(path):
                    os.rename(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
    try:
        with open(path, "rb") as f:
            key = serialization.load_pem_private_key(f.read(), password=None)
        if not isinstance(key, Ed25519PrivateKey):
            raise ValueError("not an Ed25519 private key")
    except Exception as exc:
        raise RuntimeError(f"tenure: the passport key {path} cannot be read ({exc}). Move that file away and a "
                           f"new key will be created; passports signed with the old key keep its public key.") from exc
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


def build(st, agent: str, settings: dict, data_dir: str, redact: bool = True, create_key: bool = True,
          rows: list[dict] | None = None) -> dict:
    """The passport of ``agent``: its recorded states, under the settings of the ledger's last settings event (the
    ones they were computed with; ``settings`` only stands in before the first one, and names the profile with its
    optional ``profile`` key, else the Hermes home holding ``data_dir``), signed when a key is available (with
    ``create_key`` false, only when one already exists: nothing is written). ``rows``: the ledger, when the caller
    already read it."""
    rows = st.ledger() if rows is None else rows
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
         "settings_fingerprint": settings_event_fingerprint(cfg),
         "redacted": bool(redact),
         "types": _entries({s.key: s for _, s in st.states(agent)}, cfg, redact),
         "ledger": {"count": len(rows), "head": _head(rows)}}
    if create_key or os.path.exists(os.path.join(data_dir, KEY_FILE)):
        key, public = keypair(data_dir)
    else:                                                # read-only caller: unsigned, nothing written
        key, public = None, None
    p["public_key"] = public
    p["signature"] = None if key is None else sign(p, key)
    return p


def _shape(passport) -> tuple[list[str], dict]:
    """Structure problems, and which parts are sound enough to check: exactly the documented keys at the root, in
    ``agent``, ``rule`` and ``ledger``, and ``TYPE_FIELDS`` in each type; each type listed once."""
    bad = "malformed passport: "
    if not isinstance(passport, dict):
        return [bad + "not a JSON object"], {}
    problems, ok = [], {}
    problems += [bad + f"extra field {k}" for k in sorted(set(passport) - set(ROOT_KEYS), key=str)]
    problems += [bad + f"missing field {k}" for k in ROOT_KEYS if k not in passport]
    for name, keys in PART_KEYS.items():
        part = passport.get(name)
        if not isinstance(part, dict):
            problems.append(bad + f"{name} is not an object")
            continue
        extra, missing = sorted(set(part) - set(keys), key=str), [k for k in keys if k not in part]
        problems += [bad + f"extra field {name}.{k}" for k in extra] + [bad + f"missing field {name}.{k}" for k in missing]
        ok[name] = not extra and not missing
    led = passport.get("ledger") if ok.get("ledger") else {}
    if ok.get("ledger"):
        count = led["count"]
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            problems.append(bad + "ledger.count must be a whole number")
            ok["ledger"] = False
        if not isinstance(led["head"], str) or not HEX64.fullmatch(led["head"]):
            problems.append(bad + "ledger.head must be 64 lowercase hex digits")
            ok["ledger"] = False
    if ok.get("agent") and not all(isinstance(passport["agent"][k], str) for k in PART_KEYS["agent"]):
        problems.append(bad + "agent fields must be text")
        ok["agent"] = False
    if "redacted" in passport and not isinstance(passport["redacted"], bool):
        problems.append(bad + "redacted must be true or false")
    for field, pattern, size in (("signature", HEX128, 128), ("public_key", HEX64, 64)):
        v = passport.get(field)
        if v is not None and not (isinstance(v, str) and pattern.fullmatch(v)):
            problems.append(bad + f"{field.replace('_', ' ')} must be {size} lowercase hex digits")
            ok["signature_shape_bad"] = True
    types = passport.get("types")
    ok["types"] = isinstance(types, list)
    if not ok["types"]:
        problems.append(bad + "types is not a list")
        return problems, ok
    seen = set()
    for i, e in enumerate(types):
        if not isinstance(e, dict) or not isinstance(e.get("type"), str):
            problems.append(bad + f"types[{i}] is not an object with a type name")
            ok["types"] = False
            continue
        key = e["type"]
        if key in seen:
            problems.append(f"type {key}: listed twice")
        seen.add(key)
        problems += [f"type {key}: extra field {k}" for k in sorted(set(e) - set(TYPE_FIELDS), key=str)]
        problems += [f"type {key}: missing field {k}" for k in TYPE_FIELDS if k not in e]
    return problems, ok


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
    except (InvalidSignature, ValueError, TypeError):
        return ["signature does not match the passport's content"]
    return []


def verify(passport: dict, rows: list[dict] | None = None, chain_ok: bool = False) -> list[str]:
    """Problems found, never an exception. In order: structure, signature, protocol and rule, then with ``rows``: the
    hash chain, the passport's place in it, and every type recomputed by replay of the first ``ledger.count`` rows.
    An empty list means everything checks. An unsigned passport that is otherwise right gives ``["unsigned"]``;
    without ``rows`` the types are not checked and the list ends with ``NO_LEDGER``, so it is never empty. A ledger
    longer than the passport's count is fine: the passport describes the ledger as it was then. ``chain_ok``: the
    caller already checked the hash chain (the dashboard does, from the stored text); it is not checked again."""
    shape, ok = _shape(passport)
    if not isinstance(passport, dict):
        return shape
    problems = ([] if ok.get("signature_shape_bad") else _check_signature(passport)) + shape
    if passport.get("protocol") != PROTOCOL:
        problems.append(f"protocol {passport.get('protocol')!r}, expected {PROTOCOL!r}")
    if not ok.get("rule") or passport["rule"].get("fingerprint") != rule_fingerprint():
        problems.append("rule fingerprint differs from this plugin's rule: the replay below may not apply")
    if rows is None:
        return problems + [NO_LEDGER]
    if not isinstance(rows, list) or not all(isinstance(r, dict) and isinstance(r.get("event"), dict) for r in rows):
        return problems + ["malformed ledger: every row must be an object with an event object"]
    try:
        if not chain_ok:
            problems += [f"ledger: {p}" for p in store.verify(rows)]
    except (TypeError, ValueError, AttributeError) as exc:
        return problems + [f"malformed ledger: {exc}"]
    if not ok.get("ledger"):
        return problems
    count = passport["ledger"]["count"]
    if count > len(rows):
        return problems + [f"ledger: the passport counts {count} events, the ledger has {len(rows)}"]
    head = _head(rows[:count])
    if passport["ledger"]["head"] != head:
        problems.append(f"ledger: head {passport['ledger']['head']} in the passport, {head} at event {count}")
    try:
        states, cfg = _replay(rows[:count])
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        return problems + [f"replay: {exc}"]
    if passport.get("settings_fingerprint") != settings_event_fingerprint(cfg):
        problems.append("settings fingerprint differs from the ledger's last settings")
    if not ok.get("agent") or not ok.get("types"):
        return problems
    agent = passport["agent"]
    name = f"{agent['model']}@{agent['provider'] or 'unknown'}"
    mine = {k: s for (a, k), s in states.items() if a == name}
    try:
        expected = {e["type"]: e for e in _entries(mine, cfg, passport.get("redacted") is True)}
    except (ValueError, TypeError) as exc:
        return problems + [f"replay: {exc}"]
    claimed = {}
    for e in passport["types"]:
        claimed.setdefault(e["type"], e)
    for key in sorted(set(expected) | set(claimed)):
        if key not in claimed:
            problems.append(f"type {key}: found by replay, missing from the passport")
        elif key not in expected:
            problems.append(f"type {key}: in the passport, not found by replay")
        else:
            for f in TYPE_FIELDS[1:]:
                if f in claimed[key] and claimed[key][f] != expected[key][f]:
                    problems.append(f"type {key}: {f} {claimed[key][f]!r} in the passport, "
                                    f"{expected[key][f]!r} by replay")
    return problems


def changes_since(passport: dict, rows: list[dict]) -> list[str]:
    """What changed for the passport's agent in the ledger after the passport was made (counter-audit C6): an older
    passport still verifies against a longer ledger, so the verifier says how the agent's types stand now."""
    try:
        count = passport["ledger"]["count"]
        agent = passport["agent"]
        name = f"{agent['model']}@{agent['provider'] or 'unknown'}"
        if not isinstance(rows, list) or count >= len(rows):
            return []
        then, cfg_then = _replay(rows[:count])
        now, cfg_now = _replay(rows)
        redact = passport.get("redacted") is True
        a = {e["type"]: e for e in _entries({k: s for (x, k), s in then.items() if x == name}, cfg_then, redact)}
        b = {e["type"]: e for e in _entries({k: s for (x, k), s in now.items() if x == name}, cfg_now, redact)}
    except (KeyError, TypeError, ValueError, AttributeError):
        return []
    out = []
    for key in sorted(set(a) | set(b)):
        ea, eb = a.get(key) or {}, b.get(key) or {}
        if (ea.get("tier"), ea.get("effective_tier")) != (eb.get("tier"), eb.get("effective_tier")):
            out.append(f"type {key}: tier {ea.get('effective_tier', ea.get('tier'))} in the passport, "
                       f"{eb.get('effective_tier', eb.get('tier'))} now")
        elif ea != eb:
            out.append(f"type {key}: same tier, record changed (series {ea.get('series')} then, {eb.get('series')} now)")
    return out


def anchor_line(st) -> str:
    """One line to publish anywhere (a post, a gist): the ledger's head, its date and its length."""
    row = st.db.execute("SELECT at, hash FROM ledger ORDER BY seq DESC LIMIT 1").fetchone()
    count = st.db.execute("SELECT COUNT(*) FROM ledger").fetchone()[0]
    at, head = (row[0], row[1]) if row else (time.time(), store.GENESIS)
    return (f"tenure ledger head {head} at {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(at))} "
            f"({count} events)")
