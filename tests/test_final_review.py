"""The final review's probes, through the hooks: a cleared type never reaches tenure's own switches, a suspended
parent taints its children, a background launch teaches nothing, the passport says which tier runs today, and the
copy promises no more than the code does."""
import json
import os
import pathlib

import pytest

from test_plugin import A, FAST, anon, climb, ledger, outcomes, plugin, post, pre, to_t3, write  # noqa: F401
from test_passport import HAS_CRYPTO, make_passport  # noqa: F401

ROOT = pathlib.Path(__file__).resolve().parent.parent


# ----------------------------------------------------------------------------------------------- C1 (probe p3)
def test_a_cleared_hermes_status_never_lets_config_set_run(plugin):
    mod, ctx = plugin({"preset": "fast"})
    for session in ("sA", "sB"):
        for _ in range(30):
            ctx.call("terminal", {"command": "hermes status"}, session=session,
                     result='{"output": "", "exit_code": 0}')
    runs = 0
    for _ in range(20):
        before = len(ctx.prompts)
        ctx.call("terminal", {"command": "hermes config set plugins.entries.tenure.settings.enabled false"},
                 session="sC", answer="deny", result='{"exit_code": 0}')
        runs += len(ctx.prompts) == before
    assert runs == 0
    assert all(p["rule_key"].startswith("tenure:cap:self:hermes:") for p in ctx.prompts)


def test_self_types_stay_capped_even_with_an_override(plugin):
    mod, ctx = plugin({"types": {"self:*": "free", "*": "free"}})
    for cmd in ("hermes plugins disable tenure", "find ~ -name tenure.db -delete"):
        d = pre(mod, "terminal", {"command": cmd}, "c-" + cmd[:5])
        assert d and d["rule_key"].startswith("tenure:cap:self:"), cmd


# ---------------------------------------------------------------------------------------------------------- I1
def test_registers_subagent_start(plugin):
    mod, ctx = plugin()
    assert "subagent_start" in ctx.hooks


def test_a_suspended_parent_taints_its_child(plugin):
    mod, ctx = plugin(FAST)
    to_t3(ctx)
    ctx.call("web_extract", {"urls": ["https://example.com"]}, session="s1")
    ctx.hooks["subagent_start"](parent_session_id="s1", parent_turn_id="t", parent_subagent_id=None,
                                child_session_id="child-1", child_subagent_id="sa-1", child_role="leaf",
                                child_goal="x")
    ctx.hooks["subagent_start"](parent_session_id="s2", child_session_id="child-2")
    st = mod.store_()
    assert st.is_tainted(anon("child-1")) and not st.is_tainted(anon("child-2"))
    assert ctx.call("write_file", write("c1"), session="child-1") == "approved"
    assert ctx.call("write_file", write("c2"), session="child-2") == "ran"


def test_subagent_start_survives_bad_input(plugin):
    mod, ctx = plugin()
    assert ctx.hooks["subagent_start"]() is None
    assert ctx.hooks["subagent_start"](parent_session_id="p", child_session_id="p") is None
    assert ctx.hooks["subagent_start"](parent_session_id="p", child_session_id=None) is None


# ----------------------------------------------------------------------------------------- minor: background
@pytest.mark.parametrize("extra", [{"background": True}, {"background": "true"}, {"timeout": 3600}])
def test_a_background_launch_is_neutral(plugin, extra):
    mod, ctx = plugin(FAST)
    args = {"command": "npm test", **extra}
    for _ in range(6):
        assert ctx.call("terminal", args, result='{"output": "started", "exit_code": 0, "session_id": "p1"}') \
            == "approved"
    got = outcomes(mod, type="shell:npm")
    assert got and all((e["result"], e["source"]) == ("neutral", "background") for e in got)
    assert not outcomes(mod, result="success")


def test_a_foreground_run_still_counts(plugin):
    mod, ctx = plugin(FAST)
    ctx.call("terminal", {"command": "npm test", "background": False, "timeout": 60},
             result='{"output": "", "exit_code": 0}')
    assert [(e["result"], e["source"]) for e in outcomes(mod, type="shell:npm")] == [("success", "approval")]


def test_background_is_a_known_neutral_source():
    from tenure import store
    assert "background" in store.OUTCOME_SOURCES["neutral"]
    assert ("neutral", "background") not in store.COUNTED
    proto = (ROOT / "docs" / "protocol.md").read_text(encoding="utf-8")
    assert "`background`" in proto


# --------------------------------------------------------------------------------------- minor: effective_tier
def test_passport_types_carry_the_effective_tier(plugin):
    mod, ctx = plugin(FAST)
    to_t3(ctx)
    p = make_passport(mod)
    e = {t["type"]: t for t in p["types"]}["file:write"]
    assert e["tier"] == "alone" and e["effective_tier"] == "alone"
    assert list(e) == list(mod.passport.TYPE_FIELDS)
    assert mod.passport.verify(p, mod.store_().ledger()) in ([], ["unsigned"])


def test_effective_tier_follows_todays_settings(plugin):
    mod, ctx = plugin(FAST)
    to_t3(ctx)
    ctx.settings["risks"] = {"low": 0.01, "medium": 0.2}            # a longer series is required now
    pre(mod, "write_file", write("sync"), "sync")                   # syncs the settings into the ledger
    e = {t["type"]: t for t in make_passport(mod)["types"]}["file:write"]
    assert e["effective_tier"] != "alone"


def test_a_forged_effective_tier_fails_verification(plugin):
    mod, ctx = plugin(FAST)
    climb(ctx, 2)
    p = make_passport(mod)
    p["types"][0]["effective_tier"] = "alone"
    problems = mod.passport.verify(p, mod.store_().ledger())
    assert any("effective_tier" in x for x in problems)
    del p["types"][0]["effective_tier"]
    assert any("missing field effective_tier" in x for x in mod.passport.verify(p, mod.store_().ledger()))


def test_protocol_documents_effective_tier():
    proto = (ROOT / "docs" / "protocol.md").read_text(encoding="utf-8")
    assert '"effective_tier"' in proto and "`effective_tier`" in proto


# ---------------------------------------------------------------------------------------------- I2, I3, I4
def test_privacy_wording_admits_names_in_types():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    proto = (ROOT / "docs" / "protocol.md").read_text(encoding="utf-8")
    for text in (readme, proto):
        low = " ".join(text.lower().split())
        assert "never a command, a path, an argument" not in low
        assert "never hold a command, a path, an argument" not in low
        assert "the ledger keeps them" in low
        assert "redact them by default" in low


def test_readme_suspension_names_the_exact_list():
    readme = " ".join((ROOT / "README.md").read_text(encoding="utf-8").split())
    assert "after using one of these tools or commands" in readme


def test_dashboard_never_promises_any_change_shows():
    js = (ROOT / "tenure" / "dashboard" / "dist" / "index.js").read_text(encoding="utf-8")
    assert "any change" not in js.lower()
    assert "a change after it is signed or anchored shows on verification" in js.lower()


def test_manifest_declares_every_registered_hook(plugin):
    mod, ctx = plugin()
    manifest = (ROOT / "tenure" / "plugin.yaml").read_text(encoding="utf-8")
    block = manifest.split("provides_hooks:\n", 1)[1].split("\n", len(ctx.hooks) + 1)
    declared = {line.strip()[2:] for line in block if line.startswith("  - ")}
    assert declared == set(ctx.hooks)
