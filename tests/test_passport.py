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


NO_LEDGER = "ledger not provided: types not checked"
HIGH_OK = {"risks": {"low": 0.25, "medium": 0.2, "high": 0.1}}          # high stakes recorded, not capped


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
    assert set(t["file:write"]) == {"type", "stakes", "tier", "effective_tier", "series", "required", "sessions",
                                    "provisional", "guarantee", "trusted"}
    assert t["memory:write"]["required"] == 4 and t["file:write-outside"]["stakes"] == "medium"
    assert re.fullmatch(r"[0-9a-f]{128}", p["signature"]) and re.fullmatch(r"[0-9a-f]{64}", p["public_key"])
    assert mod.passport.verify(p) == [NO_LEDGER]
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
    assert mod.passport.verify(resigned) == [NO_LEDGER]                   # alone, the signature cannot tell
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
    assert mod.passport.verify(p) == ["unsigned", NO_LEDGER]
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
    ("shell:tool:sub:a:b", "shell:tool:" + sha8("sub") + ":" + sha8("a") + ":" + sha8("b")),
    ("shell:docker:build:x", "shell:docker:build:" + sha8("x")),
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
    m = re.fullmatch(r"tenure ledger head ([0-9a-f]{64}) at (\S+) \((\d+) events\)", line)
    assert m and m.group(1) == rows[-1]["hash"] and int(m.group(3)) == len(rows)
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", m.group(2))


# ------------------------------------------------------------------------------------------- review, round 1
def resign(mod, p):
    if HAS_CRYPTO:
        key, _ = mod.passport.keypair(mod.data_dir())
        p["signature"] = mod.passport.sign(p, key)
    return p


def small(plugin, monkeypatch=None):
    mod, ctx = plugin(FAST)
    to_t3(ctx)
    return mod, mod.store_(), make_passport(mod)


def test_a_type_listed_twice_is_reported(plugin):
    mod, st, p = small(plugin)
    real = p["types"][0]
    p["types"] = [dict(real, tier="alone", series=999, required=0)] + p["types"]
    problems = mod.passport.verify(resign(mod, p), st.ledger())
    assert f"type {real['type']}: listed twice" in problems


def test_extra_and_missing_fields_are_reported(plugin):
    mod, st, p = small(plugin)
    p["certified_by"] = "ACME audit"
    p["types"][0]["note"] = "never failed"
    del p["types"][0]["sessions"]
    del p["generated_at"]
    problems = mod.passport.verify(resign(mod, p), st.ledger())
    key = p["types"][0]["type"]
    for want in ("malformed passport: extra field certified_by", "malformed passport: missing field generated_at",
                 f"type {key}: extra field note", f"type {key}: missing field sessions"):
        assert want in problems, (want, problems)


@pytest.mark.parametrize("change", [
    lambda p: p["types"].append("x"),
    lambda p: p.__setitem__("agent", "x"),
    lambda p: p.__setitem__("ledger", []),
    lambda p: p.__setitem__("types", {"a": 1}),
    lambda p: p.__setitem__("rule", None),
    lambda p: p.__setitem__("ledger", {"count": True, "head": "0" * 64}),
    lambda p: p.__setitem__("ledger", {"count": "3", "head": "0" * 64}),
])
def test_a_malformed_passport_gives_problems_not_exceptions(plugin, change):
    mod, st, p = small(plugin)
    change(p)
    problems = mod.passport.verify(resign(mod, p), st.ledger())
    assert any(x.startswith("malformed passport: ") for x in problems), problems


@pytest.mark.parametrize("field, value", [
    ("signature", 5), ("signature", "zz"), ("public_key", "ab"), ("public_key", 7),
])
def test_signature_and_key_must_be_lowercase_hex_of_the_right_length(plugin, field, value):
    mod, st, p = small(plugin)
    p[field] = value
    problems = mod.passport.verify(p, st.ledger())
    assert any(x.startswith("malformed passport: ") and field.replace("_", " ") in x for x in problems), problems


@signing
def test_signature_encodings_other_than_lowercase_hex_are_refused(plugin):
    mod, st, p = small(plugin)
    s = p["signature"]
    for v in (s.upper(), " ".join(s[i:i + 2] for i in range(0, len(s), 2)), s + " "):
        problems = mod.passport.verify(dict(p, signature=v), st.ledger())
        assert any(x.startswith("malformed passport: signature") for x in problems), (v, problems)


def test_not_a_passport_at_all(plugin):
    mod, st, _ = small(plugin)
    assert mod.passport.verify("x", st.ledger())[0].startswith("malformed passport: ")
    assert mod.passport.verify(None)[0].startswith("malformed passport: ")


def test_malformed_ledger_rows_give_problems(plugin):
    mod, st, p = small(plugin)
    rows = st.ledger()
    for bad in (["x"] + rows, rows[:1] + [{"seq": 2}], None):
        problems = mod.passport.verify(p, bad) if bad is not None else mod.passport.verify(p, "rows")
        assert problems and all(isinstance(x, str) for x in problems)


def test_an_agent_event_with_an_unknown_mode_is_refused(plugin):
    mod, ctx = plugin(FAST)
    to_t3(ctx)
    mod.pre_api_request(model="model-b", provider="nous", session_id="s1")
    rows = [dict(r, event=dict(r["event"])) for r in mod.store_().ledger()]
    next(r for r in rows if r["event"]["event"] == "agent")["event"]["mode"] = "lenient"
    with pytest.raises(ValueError, match="mode"):
        mod.passport.replay(rows)


def test_count_zero_on_an_empty_ledger(plugin):
    mod, st, p = small(plugin)
    q = resign(mod, dict(p, ledger={"count": 0, "head": "0" * 64}, types=[], settings_fingerprint=None))
    expected = [] if HAS_CRYPTO else ["unsigned"]
    assert mod.passport.verify(q, []) == expected
    assert mod.passport.verify(q, st.ledger()) == expected


@pytest.mark.parametrize("command, kind", [
    ("kubectl -n acme-prod get pods", "shell:kubectl:get"),
    ("kubectl --namespace acme-prod --context acme-ctx apply -f x.yaml", "shell:kubectl:apply"),
    ("kubectl --kubeconfig /k/acme.yaml delete pod x", "shell:kubectl:delete"),
    ("aws --profile client-acme s3 ls", "shell:aws:s3"),
    ("aws --region eu-west-3 --profile client-acme s3 cp a s3://b", "shell:aws:s3"),
    ("gcloud --project acme-secret compute list", "shell:gcloud:compute"),
])
def test_value_options_never_become_the_subcommand(plugin, command, kind):
    mod, _ = plugin(FAST)
    assert mod.classify.classify("terminal", {"command": command}, cwd="/tmp").type == kind


def test_kubectl_writes_behind_a_namespace_stay_high(plugin):
    mod, _ = plugin(FAST)
    act = mod.classify.classify("terminal", {"command": "kubectl -n acme-prod apply -f x.yaml"}, cwd="/tmp")
    assert (act.type, act.stakes) == ("shell:kubectl:apply", "high")


@pytest.mark.parametrize("raw, redacted", [
    ("shell:kubectl:acme-prod", "shell:kubectl:" + sha8("acme-prod")),
    ("shell:aws:client-acme", "shell:aws:" + sha8("client-acme")),
    ("shell:git:my-secret-alias", "shell:git:" + sha8("my-secret-alias")),
    ("shell:kubectl:apply", "shell:kubectl:apply"),
    ("shell:aws:s3", "shell:aws:s3"),
    ("shell:docker:push", "shell:docker:push"),
    ("shell:gh:pr", "shell:gh:pr"),
    ("shell:terraform:apply", "shell:terraform:apply"),
])
def test_only_known_subcommands_stay_readable(plugin, raw, redacted):
    mod, _ = plugin(FAST)
    assert mod.passport.redact_type(raw) == redacted


def test_no_client_name_in_a_redacted_passport(plugin):
    mod, ctx = plugin(HIGH_OK)
    for cmd in ("kubectl -n acme-prod apply -f x.yaml", "aws --profile client-acme s3 cp a s3://b",
                "gcloud --project acme-secret compute instances create x", "npm run deploy-acme",
                "make acme-release", "python3 /x/acme/deploy.py"):
        ctx.call("terminal", {"command": cmd})
    p = make_passport(mod)
    assert len(p["types"]) == 6 and "acme" not in json.dumps(p)
    assert mod.passport.verify(p, mod.store_().ledger()) in ([], ["unsigned"])


@signing
def test_a_corrupt_or_empty_key_file_names_the_path(plugin):
    mod, _ = plugin(FAST)
    d = mod.data_dir()
    mod.passport.keypair(d)
    path = os.path.join(d, mod.passport.KEY_FILE)
    for content in (b"", b"not a key"):
        with open(path, "wb") as f:
            f.write(content)
        with pytest.raises(RuntimeError) as err:
            mod.passport.keypair(d)
        assert path in str(err.value) and "move that file away" in str(err.value).lower()


@signing
def test_the_key_is_written_whole_then_put_in_place(plugin, monkeypatch):
    mod, _ = plugin(FAST)
    d = mod.data_dir()
    real = os.fdopen

    def failing(fd, *a, **k):
        f = real(fd, *a, **k)
        f.write = lambda data: (_ for _ in ()).throw(OSError("disk full"))
        return f
    monkeypatch.setattr(mod.passport.os, "fdopen", failing)
    with pytest.raises(OSError):
        mod.passport.keypair(d)
    assert not os.path.exists(os.path.join(d, mod.passport.KEY_FILE))      # no half-written key left in place
    assert [n for n in os.listdir(d) if n.startswith(mod.passport.KEY_FILE)] == []
    monkeypatch.setattr(mod.passport.os, "fdopen", real)
    assert mod.passport.keypair(d)[0] is not None


def test_verify_can_skip_a_chain_the_caller_already_checked(plugin):
    mod, ctx = plugin(FAST)
    ctx.call("write_file", write("v"))
    st = mod.store_()
    rows = st.ledger()
    doc = mod.passport.build(st, A, {}, mod.data_dir(), create_key=False, rows=rows)
    assert mod.passport.verify(doc, rows) == mod.passport.verify(doc, rows, chain_ok=True)
    rows[0]["hash"] = "0" * 64
    assert any("ledger:" in p for p in mod.passport.verify(doc, rows))
    assert not any("content changed" in p for p in mod.passport.verify(doc, rows, chain_ok=True))


# --------------------------------------------------------------------- counter-audit (10/11): stale and foreign passports
def test_an_older_passport_reports_what_changed_since(plugin):
    mod, ctx = plugin(FAST)
    to_t3(ctx)
    p = make_passport(mod)
    mod.cli.flag("file:write", agent=A)                  # an error reported after the passport: a fault
    rows = mod.store_().ledger()
    changed = mod.passport.changes_since(p, rows)
    assert changed and any("file:write" in c or "type" in c for c in changed)
    assert mod.passport.changes_since(make_passport(mod), rows) == []


def test_verify_command_notes_a_stale_passport_and_pins_a_key(plugin, tmp_path):
    from tenure import cli
    mod, ctx = plugin(FAST)
    to_t3(ctx)
    p = make_passport(mod)
    mod.cli.flag("file:write", agent=A)
    pp, lp = tmp_path / "p.json", tmp_path / "l.jsonl"
    pp.write_text(json.dumps(p))
    lp.write_text("".join(json.dumps(r) + "\n" for r in mod.store_().ledger()))
    out, code = cli.verify_cmd(str(pp), str(lp))
    assert code == 0 and "after this passport" in out
    if p.get("public_key"):
        out, code = cli.verify_cmd(str(pp), str(lp), key="0" * 64)
        assert code == 1 and "public key" in out
        out, code = cli.verify_cmd(str(pp), str(lp), key=p["public_key"])
        assert code == 0
