"""``hermes tenure`` and ``/tenure``: one test per subcommand, and the commands that must target the right agent.
The fixtures are those of test_plugin (a fake Hermes plugin context)."""
import json
import os
import re
import sys
import types

import pytest

from test_plugin import (A, B, FAST, NPM, FakeCtx, Picks, age, anon, climb, ledger, outcomes, plugin, pre, post,  # noqa: F401
                         state, to_t3, write)


def fake_hermes_config(monkeypatch, config):
    pkg, mod = types.ModuleType("hermes_cli"), types.ModuleType("hermes_cli.config")
    mod.load_config = lambda: config
    pkg.config = mod
    monkeypatch.setitem(sys.modules, "hermes_cli", pkg)
    monkeypatch.setitem(sys.modules, "hermes_cli.config", mod)


def two_models(plugin):
    """model-a earns file:write, then model-b (the last active agent) inherits half of it."""
    mod, ctx = plugin(FAST)
    climb(ctx, 3)
    mod.pre_api_request(model="model-b", provider="nous", session_id="s1")
    return mod, ctx


# ---------------------------------------------------------------------------------------------------- status
def test_status_shows_the_effective_tier_series_sessions_and_guarantee(plugin):
    mod, ctx = plugin(FAST)
    climb(ctx, 3)
    to_t3(ctx, tool="memory")
    text = mod.cli.slash("status")
    assert re.search(r"file:write\s+low\s+T1 asks first\s+3/4\s+1/2\s+0 faults / 3 checks", text)
    assert re.search(r"memory:write\s+low\s+T3 acts on its own\s+4/4\s+2/2\s+0 faults / 4 checks\s+unchecked errors under "
                     r"\d+\.\d\d% of its actions", text)
    assert "Evidence:" in text and "chain intact" in text


def test_status_says_held_when_settings_hold_a_tier_back(plugin):
    mod, ctx = plugin(FAST)
    to_t3(ctx)
    assert re.search(r"file:write\s+low\s+T3 acts on its own\s", mod.cli.slash("status"))
    ctx.settings["risks"] = {"low": 0.01, "medium": 0.01}               # stricter: nothing synced yet, stored tier T3
    assert state(mod, "file:write").tier == mod.rule.T3
    line = next(ln for ln in mod.cli.slash("status").splitlines() if ln.strip().startswith("file:write"))
    assert "(held: settings)" in line and "T3 acts on its own" not in line
    ctx.settings["risks"] = {"low": None, "medium": 0.2}                 # capped: always asked
    assert "capped: always asked" in mod.cli.slash("status")


def test_status_model_and_all(plugin):
    mod, ctx = two_models(plugin)
    assert state(mod, "file:write", B) is not None
    only_b = mod.cli.slash("status")
    assert "model-b@nous" in only_b and "model-a@nous" not in only_b
    assert "model-a@nous" in mod.cli.slash("status --model model-a") and "model-b@nous" not in \
        mod.cli.slash("status --model model-a")
    both = mod.cli.slash("status --all")
    assert "model-a@nous" in both and "model-b@nous" in both
    assert mod.cli.slash("status --model nothing").startswith("No agent starts with 'nothing'")


def test_status_profile_reads_another_profile_read_only(plugin, tmp_path):
    mod, ctx = plugin(FAST)
    other = tmp_path / "hermes" / "profiles" / "work" / "plugin-data" / "tenure" / "tenure.db"
    st = mod.store.Store(str(other))
    with st.transaction():
        st.put_state("model-z@nous", mod.rule.TypeState(key="shell:make", stakes="medium", reversible=False))
        st.set_meta("agent:last", "model-z@nous")
    out = mod.cli.slash("status --profile work")
    assert "profile work" in out and "model-z@nous" in out and "shell:make" in out
    assert mod.cli.slash("status --profile nope").startswith("No tenure record for profile 'nope'")


# ----------------------------------------------------------------------------------------------- setup, strict
def test_setup_warns_when_approvals_not_manual(plugin, monkeypatch):
    mod, ctx = plugin()
    # smart is the Hermes 0.23 default: plugin approval rules skip the guardian and always reach a person
    fake_hermes_config(monkeypatch, {"approvals": {"mode": "smart"}})
    assert "learning is paused" not in mod.cli.slash("setup")
    fake_hermes_config(monkeypatch, {"approvals": {"mode": False}})           # YAML reads an unquoted off as False
    assert "learning is paused: approvals.mode is off" in mod.cli.slash("setup fast")
    fake_hermes_config(monkeypatch, {"approvals": {"mode": "manual"}})
    assert "learning is paused" not in mod.cli.slash("setup")
    fake_hermes_config(monkeypatch, {})
    assert "learning is paused" not in mod.cli.slash("setup")


def test_setup_with_a_name_saves_the_preset_and_logs_the_settings(plugin):
    mod, ctx = plugin()
    out = mod.cli.slash("setup fast")
    assert "Preset fast in force" in out and "52 approvals" in out and ctx.settings["preset"] == "fast"
    assert ledger(mod, "settings")[-1]["risks"]["low"] == 1 / 20
    assert "Unknown preset 'wild'" in mod.cli.slash("setup wild")
    assert "balanced (default): low: 52 approvals" in mod.cli.slash("setup")


def test_strict_on_and_off(plugin):
    mod, ctx = plugin()
    assert "Strict mode on" in mod.cli.slash("strict on")
    assert ctx.settings["strict"] is True and ledger(mod, "settings")[-1]["strict"] is True
    assert "Strict mode off" in mod.cli.slash("strict off")
    assert ctx.settings["strict"] is False and ledger(mod, "settings")[-1]["strict"] is False
    assert mod.cli.slash("strict maybe").startswith("tenure:")


def test_explain_uses_the_params_numbers(plugin):
    mod, _ = plugin()
    out = mod.cli.slash("explain")
    g = mod.params.describe("balanced")
    assert f"i = {g['low']['n']}" in out and f"{g['low']['aoql']:.2%}" in out and "high: always asked" in out


# ------------------------------------------------------------------------------------------------------ models
def test_models_lists_each_model_with_its_denominator(plugin):
    mod, ctx = two_models(plugin)
    out = mod.cli.slash("models")
    assert re.search(r"file:write\s+model-a\s+nous\s+0 faults / 3 checks\s+0\.0% \(95% interval 0\.0% to", out)
    assert "under 20 checks: too few to compare" in out
    assert "model-b" in out
    assert "No record yet for shell:npm." == mod.cli.slash("models --type shell:npm")


# ------------------------------------------------------------------------------------------- flag and revoke
def test_flag_targets_the_named_model(plugin):
    """Adversarial finding 4: a flag meant for the old model must not land on the model that is active now."""
    mod, ctx = two_models(plugin)
    before_b = state(mod, "file:write", B).faults
    out = mod.cli.slash("flag file:write --model model-a")
    assert "model-a@nous" in out and state(mod, "file:write", A).faults == 1
    assert state(mod, "file:write", B).faults == before_b
    last = outcomes(mod)[-1]
    assert (last["agent"], last["result"], last["source"], last["session"]) == (A, "fault", "flag", "")
    mod.cli.slash("flag file:write private note")                       # no --model: the last active agent
    assert state(mod, "file:write", B).faults == before_b + 1 and outcomes(mod)[-1]["agent"] == B
    assert mod.cli.slash("flag file:write --model zzz").startswith("No agent starts with 'zzz'")
    assert mod.cli.slash("flag nothing:here --model model-a").startswith("No record of nothing:here")
    assert mod.store_().totals(A)["faults"] == 1


def test_flag_with_an_ambiguous_model_asks_to_be_specific(plugin):
    mod, ctx = two_models(plugin)
    mod.pre_api_request(model="model-a", provider="other", session_id="s9")
    assert "matches 2 agents" in mod.cli.slash("flag file:write --model model-a")


def test_revoke_all_and_by_model(plugin):
    mod, ctx = plugin(FAST)
    to_t3(ctx)
    to_t3(ctx, tool="memory")
    mod.pre_api_request(model="model-b", provider="nous", session_id="s1")
    assert state(mod, "file:write", B).series > 0
    out = mod.cli.slash("revoke file:write --model model-a")
    assert "model-a@nous: file:write" in out
    assert state(mod, "file:write", A).tier == mod.rule.T1 and state(mod, "memory:write", A).tier == mod.rule.T3
    assert state(mod, "file:write", B).series > 0
    assert ledger(mod, "revoke")[-1] == {"event": "revoke", "agent": A, "type": "file:write"}
    out = mod.cli.slash("revoke all --all")
    assert state(mod, "memory:write", A).tier == mod.rule.T1 and "memory:write" in out
    assert state(mod, "file:write", B).series == 0
    assert mod.cli.slash("revoke all --all") == "Nothing to revoke."


# ------------------------------------------------------------------------------------------------------- undo
def test_undo_restores_and_records_a_fault(plugin):
    mod, ctx = plugin(FAST)
    climb(ctx, 12)
    target = os.path.join(ctx.cwd, "src", "u.py")
    with open(target, "w") as f:
        f.write("before = 1\n")
    assert ctx.call("write_file", {"path": "src/u.py", "content": "after = 2\n"}) == "ran"
    uid = int(ctx.posted[-1].rsplit(" ", 1)[1])
    faults = state(mod, "file:write").faults
    out = mod.cli.slash(f"undo {uid}")
    assert "files restored" in out and "Counted as a fault of file:write" in out
    with open(target) as f:
        assert f.read() == "before = 1\n"
    s = state(mod, "file:write")
    assert (s.faults, s.series, s.tier) == (faults + 1, 0, mod.rule.T1)
    last = outcomes(mod)[-1]
    assert (last["result"], last["source"], last["session"]) == ("fault", "undo", "")
    assert mod.store_().get_undo(uid)["undone"] is True
    assert "already undone" in mod.cli.slash(f"undo {uid}")
    assert state(mod, "file:write").faults == faults + 1
    live = {(a, s.key): s.to_dict() for a, s in mod.store_().states()}
    replayed = {(a, k): s.to_dict() for a, t in mod.passport.replay(mod.store_().ledger()).items()
                for k, s in t.items()}
    for d in list(live.values()) + list(replayed.values()):
        d.pop("changed_at")
    assert replayed == live                                              # the ledger input keeps replay exact


def test_undo_of_a_failed_check_restores_without_a_second_fault(plugin):
    mod, ctx = plugin(FAST)
    climb(ctx, 12)
    target = os.path.join(ctx.cwd, "src", "w.py")
    with open(target, "w") as f:
        f.write("good = 1\n")
    assert ctx.call("write_file", {"path": "src/w.py", "content": "def broken(:\n"}) == "ran"
    uid = int(re.search(r"/tenure undo (\d+)$", next(p for p in ctx.posted if "check failed" in p))[1])
    faults, n = state(mod, "file:write").faults, len(outcomes(mod))
    out = mod.cli.slash(f"undo {uid}")
    assert "no second fault is recorded" in out
    with open(target) as f:
        assert f.read() == "good = 1\n"
    assert state(mod, "file:write").faults == faults and len(outcomes(mod)) == n
    assert mod.store_().get_undo(uid)["undone"] is True


def test_undo_refuses_old_and_unknown_entries(plugin):
    mod, ctx = plugin(FAST)
    climb(ctx, 12)
    ctx.call("write_file", write("o"))
    uid = int(ctx.posted[-1].rsplit(" ", 1)[1])
    with mod.txn() as st:
        st.db.execute("UPDATE undo SET at = at - 90000 WHERE id = ?", (uid,))
    n = len(ledger(mod))
    assert "older than 24 h" in mod.cli.slash(f"undo {uid}")
    assert "No undo entry 999" in mod.cli.slash("undo 999")
    assert mod.cli.slash("undo x").startswith("tenure:")
    assert len(ledger(mod)) == n and mod.store_().get_undo(uid)["undone"] is False


# --------------------------------------------------------------------------- passport, verify, anchor, export
def earned(plugin):
    mod, ctx = plugin(FAST)
    to_t3(ctx)
    ctx.call("terminal", NPM)
    return mod, ctx


def test_passport_syncs_settings_and_redacts_by_default(plugin, tmp_path):
    mod, ctx = earned(plugin)
    ctx.call("terminal", {"command": "make secret_target_xyz"})
    ctx.settings["risks"] = {"low": 0.2, "medium": 0.2}                  # changed, not yet in the ledger
    n_settings = len(ledger(mod, "settings"))
    out_file = tmp_path / "p.json"
    out = mod.cli.slash(f"passport --out {out_file}")
    assert "Passport written" in out and "redacted" in out and "NOT redacted" not in out
    assert len(ledger(mod, "settings")) == n_settings + 1                # the ledger has the current settings
    p = json.loads(out_file.read_text())
    assert p["redacted"] is True and p["signature"] and p["agent"]["model"] == "model-a"
    assert "secret_target_xyz" not in out_file.read_text()
    assert p["ledger"]["count"] == len(mod.store_().ledger())
    assert mod.passport.verify(p, mod.store_().ledger()) == []


def test_passport_no_redact_warns_and_keeps_names(plugin, tmp_path):
    mod, ctx = earned(plugin)
    ctx.call("terminal", {"command": "make secret_target_xyz"})
    out_file = tmp_path / "raw.json"
    out = mod.cli.slash(f"passport --no-redact --out {out_file}")
    assert "NOT redacted" in out and "Warning" in out
    assert json.loads(out_file.read_text())["redacted"] is False and "secret_target_xyz" in out_file.read_text()
    assert mod.cli.slash("passport --agent nobody").startswith("No agent starts with")


def test_verify_ok_only_with_the_ledger(plugin, tmp_path):
    mod, ctx = earned(plugin)
    pfile, lfile = tmp_path / "p.json", tmp_path / "ledger.jsonl"
    mod.cli.slash(f"passport --out {pfile}")
    mod.cli.slash(f"export {lfile}")
    text, code = mod.cli.verify_cmd(str(pfile), str(lfile))
    assert code == 0 and text.startswith("OK:") and "recomputed by replay" in text
    text, code = mod.cli.verify_cmd(str(pfile))
    assert code == 1 and "OK" not in text
    assert text == "signature and chain not checked against types: pass the ledger"
    assert mod.cli.slash(f"verify {pfile} {lfile}").startswith("OK:")


def test_verify_reports_tampering(plugin, tmp_path):
    mod, ctx = earned(plugin)
    pfile, lfile = tmp_path / "p.json", tmp_path / "ledger.jsonl"
    mod.cli.slash(f"passport --out {pfile}")
    mod.cli.slash(f"export {lfile}")
    p = json.loads(pfile.read_text())
    p["types"][0]["series"] += 1
    pfile.write_text(json.dumps(p))
    text, code = mod.cli.verify_cmd(str(pfile), str(lfile))
    assert code == 1 and "problem(s)" in text and "signature" in text
    assert mod.cli.verify_cmd(str(tmp_path / "missing.json"))[1] == 1
    (tmp_path / "bad.json").write_text("{nope")
    assert "not valid JSON" in mod.cli.verify_cmd(str(tmp_path / "bad.json"))[0]


def test_anchor_prints_the_ledger_head(plugin):
    mod, ctx = earned(plugin)
    line = mod.cli.slash("anchor")
    head = mod.store_().ledger()[-1]["hash"]
    assert line.startswith(f"tenure ledger head {head} at ") and f"({len(mod.store_().ledger())} events)" in line


def test_export_writes_a_verifiable_ledger(plugin, tmp_path):
    mod, ctx = earned(plugin)
    path = tmp_path / "e.jsonl"
    out = mod.cli.slash(f"export {path}")
    rows = [json.loads(ln) for ln in path.read_text().splitlines()]
    assert f"({len(rows)} entries)" in out and mod.store.verify(rows) == []


# ------------------------------------------------------------------------------------------------------ cleanup
def test_cleanup_lists_dead_keys_and_never_edits_config(plugin, monkeypatch):
    mod, ctx = plugin()
    config = {"command_allowlist": ["recursive delete", "plugin_rule:tenure:ask:file:write:" + "a" * 32,
                                    "tenure:spot:shell:npm:" + "b" * 32]}
    fake_hermes_config(monkeypatch, config)
    out = mod.cli.slash("cleanup")
    assert "2 dead tenure key(s)" in out and "tenure:spot:shell:npm:" + "b" * 32 in out
    assert """hermes config set command_allowlist '["recursive delete"]'""" in out
    assert len(config["command_allowlist"]) == 3
    fake_hermes_config(monkeypatch, {"command_allowlist": ["recursive delete"]})
    assert mod.cli.slash("cleanup").startswith("No tenure key")
    fake_hermes_config(monkeypatch, {})
    assert mod.cli.slash("cleanup").startswith("No tenure key")


def test_cleanup_without_hermes_config(plugin, monkeypatch):
    mod, _ = plugin()
    monkeypatch.setitem(sys.modules, "hermes_cli", None)
    assert mod.cli.slash("cleanup").startswith("Cannot read Hermes' config")


# --------------------------------------------------------------------------------------------- entry points
def test_unknown_command_shows_the_usage_and_run_sets_the_exit_code(plugin, capsys):
    mod, ctx = plugin()
    assert "verify PASSPORT [LEDGER]" in mod.cli.slash("frobnicate")
    setup_fn, handler = ctx.cli["tenure"]
    import argparse
    parser = argparse.ArgumentParser()
    setup_fn(parser)
    args = parser.parse_args(["verify", "/nonexistent/passport.json"])
    with pytest.raises(SystemExit) as e:
        handler(args)
    assert e.value.code == 1 and "Cannot read" in capsys.readouterr().out
    handler(parser.parse_args(["status"]))
    assert "Evidence:" in capsys.readouterr().out


# ------------------------------------------------------------------------------- exit codes, partial undo
def run_line(mod, line):
    import shlex
    p = mod.cli._Parser(prog="x", add_help=False)
    mod.cli._add_subcommands(p)
    return mod.cli.execute(p.parse_args(shlex.split(line)))


def test_refusals_exit_non_zero(plugin):
    mod, ctx = plugin(FAST)
    climb(ctx, 12)
    ctx.call("write_file", write("r"))
    uid = int(ctx.posted[-1].rsplit(" ", 1)[1])
    assert run_line(mod, "undo 999")[1] == 1
    assert run_line(mod, "flag nothing:here --model model-a")[1] == 1
    assert run_line(mod, "revoke zzz --model model-a") == ("Nothing to revoke.", 0)
    with mod.txn() as st:
        st.db.execute("UPDATE undo SET at = at - 90000 WHERE id = ?", (uid,))
    assert run_line(mod, f"undo {uid}")[1] == 1
    with mod.txn() as st:
        st.db.execute("UPDATE undo SET at = at + 90000 WHERE id = ?", (uid,))
    text, code = run_line(mod, f"undo {uid}")
    assert code == 0 and "files restored" in text
    assert run_line(mod, f"undo {uid}")[1] == 1                          # already undone


def test_undo_with_a_gone_snapshot_exits_non_zero(plugin):
    mod, ctx = plugin(FAST)
    climb(ctx, 12)
    ctx.call("write_file", write("g"))
    uid = int(ctx.posted[-1].rsplit(" ", 1)[1])
    import shutil
    shutil.rmtree(os.path.join(mod.data_dir(), "undo"))
    assert run_line(mod, f"undo {uid}")[1] == 1


def test_partial_undo_keeps_the_entry_open_and_records_no_fault(plugin, monkeypatch):
    mod, ctx = plugin(FAST)
    climb(ctx, 12)
    ctx.call("write_file", write("p"))
    uid = int(ctx.posted[-1].rsplit(" ", 1)[1])
    faults, n = state(mod, "file:write").faults, len(ledger(mod))
    monkeypatch.setattr(mod.undo, "restore", lambda snap, root, keep=False, key=None: (1, 2))
    text, code = run_line(mod, f"undo {uid}")
    assert code == 1 and "2 file(s) could not be restored" in text and "try again" in text
    assert mod.store_().get_undo(uid)["undone"] is False
    assert state(mod, "file:write").faults == faults and len(ledger(mod)) == n


def test_snapshot_is_discarded_only_after_the_transaction_commits(plugin, monkeypatch):
    mod, ctx = plugin(FAST)
    climb(ctx, 12)
    ctx.call("write_file", write("d"))
    uid = int(ctx.posted[-1].rsplit(" ", 1)[1])
    snap = mod.store_().get_undo(uid)["snap_id"]
    folder = os.path.join(mod.data_dir(), "undo", snap)
    # a failure after the files are back (recording the fault) rolls everything back and keeps the snapshot
    with monkeypatch.context() as m:
        m.setattr(mod, "record_outcome", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
        with pytest.raises(RuntimeError):
            mod.cli.undo_action(uid)
    assert os.path.isdir(folder) and mod.store_().get_undo(uid)["undone"] is False
    with mod.txn() as st:
        msg = mod.undo_entry(st, uid)
        assert msg.ok and os.path.isdir(folder)                          # still there inside the transaction
    msg.cleanup()
    assert not os.path.exists(folder) and mod.store_().get_undo(uid)["undone"] is True


def test_settings_come_from_hermes_config_without_a_plugin_context(plugin, monkeypatch):
    mod, ctx = plugin(FAST)
    mod.ST.ctx = None
    assert mod.settings()["risks"]["low"] == mod.params.PRESETS["balanced"]["low"]      # nothing to read: defaults
    fake = types.ModuleType("hermes_cli.config")
    fake.load_config = lambda: {"plugins": {"entries": {"tenure": {"settings": {
        "preset": "fast", "strict": True, "spot_check": 0.2}}}}}
    pkg = types.ModuleType("hermes_cli")
    pkg.config = fake
    monkeypatch.setitem(sys.modules, "hermes_cli", pkg)
    monkeypatch.setitem(sys.modules, "hermes_cli.config", fake)
    cfg = mod.settings()
    assert (cfg["preset"], cfg["strict"], cfg["spot"]) == ("fast", True, 0.2)
