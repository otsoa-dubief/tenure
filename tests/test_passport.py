"""The autonomy passport: signed and tamper-evident, re-verifiable by replaying the hash-chained ledger."""
import copy
import hashlib
import json
import os
import re
import stat

import pytest

from test_plugin import A, B, C, FAST, NPM, Picks, climb, plugin, to_t3, write   # noqa: F401 (plugin: fixture)

try:
    import cryptography  # noqa: F401
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False
signing = pytest.mark.skipif(not HAS_CRYPTO, reason="cryptography is not installed: passports are unsigned")


def sha8(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


def live_states(mod):
    out = {}
    for agent, s in mod.store_().states():
        d = s.to_dict()
        d.pop("changed_at")
        out.setdefault(agent, {})[s.key] = d
    return out


def replayed_states(mod):
    out = {}
    for agent, types in mod.passport.replay(mod.store_().ledger()).items():
        for key, s in types.items():
            d = s.to_dict()
            d.pop("changed_at")
            out.setdefault(agent, {})[key] = d
    return out


def make_passport(mod, agent=A, **kw):
    return mod.passport.build(mod.store_(), agent, mod.settings(), mod.data_dir(), **kw)


def scripted(plugin, monkeypatch, tmp_path):
    """A session through the hooks: climbs, act then notify, a failed check, spot checks, a failed trial and its
    wait, a settings change, a carry-over with a veto, a revocation, strict mode and a flag."""
    mod, ctx = plugin(FAST)
    monkeypatch.setattr(mod.benchmarks, "veto", lambda old, new, key, margin=5.0: key == "memory:write")
    climb(ctx, 12)                                                        # file:write to T2
    ctx.call("write_file", write("bad", "def x(:\n"))                     # notify, check fails
    to_t3(ctx, tool="memory")
    mod.ST.rng = Picks([0.0, 0.0])
    ctx.call("memory", {"action": "add", "content": "spot ok"})
    ctx.call("memory", {"action": "add", "content": "spot no"}, answer="deny")
    climb(ctx, 2, name="again", tool="memory")                            # a series for the veto to withhold
    for verdict in ("deny", "deny", "timeout", "once"):
        ctx.call("terminal", NPM, answer=verdict)
    ctx.call("terminal", {"command": "npm run build"})
    outside = str(tmp_path / "outside" / "m.py")                         # file:write-outside, medium stakes
    ctx.call("write_file", {"path": outside, "content": "x = 1\n"}, answer="deny")        # a trial opens
    ctx.call("write_file", {"path": outside, "content": "def x(:\n"})    # ran, check failed: not counted (R17)
    ctx.call("write_file", {"path": outside, "content": "x = 2\n"})      # counted by the wait
    ctx.call("terminal", {"command": "python3 scripts/deploy.py"}, answer="deny")
    ctx.settings["risks"] = {"low": 0.25, "medium": 0.1}
    ctx.call("terminal", NPM)
    ctx.settings["types"] = {"file:write": "medium"}                     # a stakes change: the evidence re-based
    climb(ctx, 2, name="m")
    mod.pre_api_request(model="model-b", provider="nous", session_id="s1")   # carry, memory:write vetoed
    climb(ctx, 2, name="b")
    climb(ctx, 2, name="bm", tool="memory")                               # a series strict mode must not carry
    mod.cli.revoke("file:write", B)
    ctx.settings["strict"] = True
    mod.pre_api_request(model="model-c", provider="nous", session_id="s1")   # strict
    ctx.call("write_file", write("c"), answer="deny")
    mod.cli.flag("memory:write", agent=A)
    return mod, ctx


# ------------------------------------------------------------------------------------------------------- replay
def test_replay_reproduces_live_states(plugin, monkeypatch, tmp_path):
    mod, _ = scripted(plugin, monkeypatch, tmp_path)
    live, replayed = live_states(mod), replayed_states(mod)
    assert set(live) == {A, B, C} and sum(len(t) for t in live.values()) >= 10
    assert replayed == live


def test_replay_reads_input_events_only(plugin, monkeypatch, tmp_path):
    mod, _ = scripted(plugin, monkeypatch, tmp_path)
    rows = mod.store_().ledger()
    inputs = [r for r in rows if r["event"]["event"] in mod.store.INPUT_KINDS]
    assert len(inputs) < len(rows)
    assert {a: {k: s.to_dict() | {"changed_at": 0} for k, s in t.items()}
            for a, t in mod.passport.replay(inputs).items()} == \
           {a: {k: s.to_dict() | {"changed_at": 0} for k, s in t.items()}
            for a, t in mod.passport.replay(rows).items()}


def test_replay_refuses_an_outcome_before_any_settings(plugin):
    mod, _ = plugin(FAST)
    event = {"event": "outcome", "agent": A, "type": "file:write", "stakes": "low", "reversible": True,
             "result": "success", "source": "approval", "session": "x"}
    with pytest.raises(ValueError, match="settings"):
        mod.passport.replay([{"seq": 1, "event": event}])


def test_replay_refuses_another_rule(plugin):
    mod, _ = plugin(FAST)
    with pytest.raises(ValueError, match="rule"):
        mod.passport.replay([{"seq": 1, "event": {"event": "settings", "risks": {"low": 0.1}, "spot": 0.1,
                                                  "strict": False, "rule": "study-rule-Z/9"}}])


def test_settings_change_is_replayed_with_old_settings(plugin):
    mod, ctx = plugin(FAST)                                               # n = 4 at low stakes
    to_t3(ctx)
    ctx.call("write_file", write("extra"), session="s2")                  # series stays capped at 4
    ctx.settings["risks"] = {"low": 0.1, "medium": 0.2}                   # n = 10: the T3 drops
    ctx.call("terminal", NPM)
    assert len([r for r in mod.store_().ledger() if r["event"]["event"] == "settings"]) == 2
    s = mod.passport.replay(mod.store_().ledger())[A]["file:write"]
    assert (s.series, s.tier) == (4, mod.rule.T1)                         # with today's settings only: 5
    assert replayed_states(mod) == live_states(mod)
    assert mod.passport.verify(make_passport(mod), mod.store_().ledger()) in ([], ["unsigned"])


# ---------------------------------------------------------------------------------------------------- passport
def test_rule_fingerprint_is_stable_and_follows_the_parameters(plugin, monkeypatch):
    mod, _ = plugin(FAST)
    fp = mod.passport.rule_fingerprint()
    assert re.fullmatch(r"[0-9a-f]{64}", fp) and fp == mod.passport.rule_fingerprint()
    monkeypatch.setattr(mod.rule, "WAIT", 49)
    assert mod.passport.rule_fingerprint() != fp


@signing
def test_build_and_verify_ok(plugin, monkeypatch, tmp_path):
    mod, _ = scripted(plugin, monkeypatch, tmp_path)
    p = make_passport(mod)
    assert p["protocol"] == "earned-autonomy/0.1"
    assert p["agent"] == {"model": "model-a", "provider": "nous", "profile": p["agent"]["profile"]}
    assert re.fullmatch(r"[0-9a-f]{12}", p["agent"]["profile"])
    assert p["rule"] == {"name": "study-rule-B", "fingerprint": mod.passport.rule_fingerprint()}
    rows = mod.store_().ledger()
    assert p["ledger"] == {"count": len(rows), "head": rows[-1]["hash"]}
    t = {e["type"]: e for e in p["types"]}
    assert set(t["file:write"]) == {"type", "stakes", "tier", "series", "required", "sessions", "provisional",
                                    "guarantee"}
    assert t["memory:write"]["required"] == 4 and t["file:write-outside"]["stakes"] == "medium"
    assert re.fullmatch(r"[0-9a-f]{128}", p["signature"]) and re.fullmatch(r"[0-9a-f]{64}", p["public_key"])
    assert mod.passport.verify(p) == []
    assert mod.passport.verify(p, rows) == []
    assert mod.passport.verify(make_passport(mod, B), rows) == []
    assert mod.passport.verify(json.loads(json.dumps(p)), rows) == []     # survives a JSON round trip


@signing
def test_the_key_is_created_once_with_mode_0600(plugin):
    mod, _ = plugin(FAST)
    key, pub = mod.passport.keypair(mod.data_dir())
    assert key is not None and re.fullmatch(r"[0-9a-f]{64}", pub)
    path = os.path.join(mod.data_dir(), mod.passport.KEY_FILE)
    if os.name == "posix":
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert mod.passport.keypair(mod.data_dir())[1] == pub


@signing
def test_tampered_type_is_detected(plugin, monkeypatch, tmp_path):
    mod, _ = scripted(plugin, monkeypatch, tmp_path)
    p = make_passport(mod)
    forged = copy.deepcopy(p)
    next(e for e in forged["types"] if e["type"] == "file:write")["tier"] = "alone"
    problems = mod.passport.verify(forged)
    assert problems and "signature" in problems[0]
    resigned = copy.deepcopy(forged)                                      # the owner re-signs a forged record
    key, _ = mod.passport.keypair(mod.data_dir())
    resigned["signature"] = mod.passport.sign(resigned, key)
    assert mod.passport.verify(resigned) == []                            # alone, the signature cannot tell
    problems = mod.passport.verify(resigned, mod.store_().ledger())
    assert any("file:write" in p and "tier" in p for p in problems)       # the replay can


@signing
def test_tampered_ledger_row_is_detected(plugin, monkeypatch, tmp_path):
    mod, _ = scripted(plugin, monkeypatch, tmp_path)
    p = make_passport(mod)
    rows = copy.deepcopy(mod.store_().ledger())
    first = next(r for r in rows if r["event"]["event"] == "outcome" and r["event"]["result"] == "success")
    first["event"]["result"] = "fault"
    first["event"]["source"] = "refusal"
    problems = mod.passport.verify(p, rows)
    assert any("ledger" in x and "changed" in x for x in problems)
    dropped = [r for r in mod.store_().ledger() if r is not None][:-1]    # the last row removed
    assert any("ledger" in x for x in mod.passport.verify(p, dropped))


@signing
def test_an_older_passport_verifies_against_a_longer_ledger(plugin):
    mod, ctx = plugin(FAST)
    to_t3(ctx)
    p = make_passport(mod)
    ctx.call("write_file", write("later"), answer="deny")
    assert mod.passport.verify(p, mod.store_().ledger()) == []


def test_unsigned_passport_says_so(plugin, monkeypatch):
    mod, ctx = plugin(FAST)
    to_t3(ctx)
    monkeypatch.setattr(mod.passport, "keypair", lambda data_dir: (None, None))
    p = make_passport(mod)
    assert p["signature"] is None and p["public_key"] is None
    assert mod.passport.verify(p) == ["unsigned"]
    assert mod.passport.verify(p, mod.store_().ledger()) == ["unsigned"]


@pytest.mark.skipif(HAS_CRYPTO, reason="checks the passport made without cryptography")
def test_without_cryptography_the_passport_is_unsigned_and_still_verifies_by_replay(plugin):
    mod, ctx = plugin(FAST)
    to_t3(ctx)
    assert mod.passport.keypair(mod.data_dir()) == (None, None)
    assert mod.passport.verify(make_passport(mod), mod.store_().ledger()) == ["unsigned"]


def test_unsigned_tampered_passport_still_fails_the_replay(plugin, monkeypatch):
    mod, ctx = plugin(FAST)
    to_t3(ctx)
    monkeypatch.setattr(mod.passport, "keypair", lambda data_dir: (None, None))
    p = make_passport(mod)
    p["types"][0]["series"] += 1
    problems = mod.passport.verify(p, mod.store_().ledger())
    assert problems[0] == "unsigned" and any("series" in x for x in problems[1:])


# --------------------------------------------------------------------------------------------------- redaction
@pytest.mark.parametrize("raw, redacted", [
    ("file:write", "file:write"),
    ("mcp:github:create_issue", "mcp:github:create_issue"),
    ("shell:git:commit", "shell:git:commit"),
    ("shell:npm", "shell:npm"),
    ("shell:npm:run:build", "shell:npm:run:" + sha8("build")),
    ("shell:python3:deploy.py", "shell:python3:" + sha8("deploy.py")),
    ("shell:python3:-m:pytest", "shell:python3:-m:" + sha8("pytest")),
    ("shell:python3:inline", "shell:python3:inline"),
    ("shell:bash:setup.sh", "shell:bash:" + sha8("setup.sh")),
    ("shell:make:release", "shell:make:" + sha8("release")),
    ("shell:make:default", "shell:make:default"),
    ("shell:npx:prettier", "shell:npx:" + sha8("prettier")),
    ("shell:tool:sub:a:b", "shell:tool:sub:" + sha8("a") + ":" + sha8("b")),
])
def test_redaction_hashes_the_segments_after_the_program_and_its_subcommand(plugin, raw, redacted):
    mod, _ = plugin(FAST)
    assert mod.passport.redact_type(raw) == redacted


def test_redacted_types_still_verify(plugin, monkeypatch, tmp_path):
    mod, _ = scripted(plugin, monkeypatch, tmp_path)
    p = make_passport(mod)
    keys = {e["type"] for e in p["types"]}
    assert "shell:npm:run:" + sha8("build") in keys and "shell:python3:" + sha8("deploy.py") in keys
    assert not any("build" in k or "deploy" in k for k in keys) and p["redacted"] is True
    assert mod.passport.verify(p, mod.store_().ledger()) in ([], ["unsigned"])
    clear = make_passport(mod, redact=False)
    assert "shell:npm:run:build" in {e["type"] for e in clear["types"]} and clear["redacted"] is False
    assert mod.passport.verify(clear, mod.store_().ledger()) in ([], ["unsigned"])


# ------------------------------------------------------------------------------------------------------ anchor
def test_anchor_line(plugin):
    mod, ctx = plugin(FAST)
    to_t3(ctx)
    rows = mod.store_().ledger()
    line = mod.passport.anchor_line(mod.store_())
    m = re.fullmatch(r"clearance ledger head ([0-9a-f]{64}) at (\S+) \((\d+) events\)", line)
    assert m and m.group(1) == rows[-1]["hash"] and int(m.group(3)) == len(rows)
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", m.group(2))
