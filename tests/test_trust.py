"""The trusted start: no question Hermes would not ask, until a type makes its first fault. Then the study rule
applies to that type, from T1. Actions that leave the machine, self-protection and suspended sessions still ask."""
import os

from test_plugin import A, FAST, NPM, climb, ledger, outcomes, plugin, post, pre, state, write  # noqa: F401

TRUST = {**FAST, "start": "trusted"}


def test_a_reversible_type_acts_then_tells_from_the_first_action(plugin):
    mod, ctx = plugin(TRUST)
    assert ctx.call("write_file", write("t1")) == "ran" and ctx.prompts == []
    assert "/tenure undo" in ctx.posted[-1]
    assert outcomes(mod)[-1]["source"] == "notify"


def test_a_command_runs_like_hermes_without_tenure(plugin):
    mod, ctx = plugin(TRUST)
    assert ctx.call("terminal", NPM) == "ran" and ctx.prompts == []
    last = outcomes(mod, type="shell:npm")[-1]
    assert (last["result"], last["source"]) == ("neutral", "alone")


def test_what_leaves_the_machine_and_self_protection_still_ask(plugin):
    mod, ctx = plugin({"start": "trusted", "preset": "careful"})   # careful does not cap high stakes
    assert ctx.call("terminal", {"command": "git push origin main"}) == "approved"
    assert ctx.call("skill_manage", {"action": "create", "name": "x"}) == "approved"
    assert len(ctx.prompts) == 2


def test_the_first_fault_puts_the_type_on_probation_and_the_study_rule_applies(plugin):
    mod, ctx = plugin(TRUST)
    ctx.call("write_file", write("t1"))
    uid = int(ctx.posted[-1].rsplit(" ", 1)[1])
    mod.cli.slash(f"undo {uid}")
    s = state(mod, "file:write")
    assert s.distrusted and s.tier == mod.rule.T1
    assert ctx.call("write_file", write("t2")) == "approved"            # asks now, only for this type
    assert ctx.call("terminal", NPM) == "ran"                            # other types keep their trust
    k = 1
    while state(mod, "file:write").tier == mod.rule.T1:                 # the study's Wald climb, after a fault
        climb(ctx, 1, name=f"back{k}")
        k += 1
    assert state(mod, "file:write").tier == mod.rule.T2
    assert len(ctx.prompts) == k == 17                                   # 17 approvals after a first fault, all asked


def test_a_flag_on_a_command_takes_its_trust_back(plugin):
    mod, ctx = plugin(TRUST)
    ctx.call("terminal", NPM)
    mod.cli.flag("shell:npm", agent=A)
    assert ctx.call("terminal", NPM) == "approved"


def test_a_revoke_takes_the_trust_back(plugin):
    mod, ctx = plugin(TRUST)
    ctx.call("terminal", NPM)
    mod.cli.revoke("shell:npm", agent=A)
    assert ctx.call("terminal", NPM) == "approved"


def test_a_suspended_session_still_asks(plugin):
    mod, ctx = plugin(TRUST)
    ctx.call("web_search", {"query": "x"})
    assert ctx.call("write_file", write("s1")) == "approved"


def test_trust_earns_no_tier_keeps_its_undo_and_claims_no_guarantee(plugin):
    mod, ctx = plugin(TRUST)
    mod.ST.rng.values = [0.0] * 40                                       # every draw would be a spot check
    for i in range(12):                                                  # FAST: 4 in a row over 2 sessions = T3
        assert ctx.call("write_file", write(f"sp{i}"), session=f"s{i % 2}") == "ran"
        assert "/tenure undo" in ctx.posted[-1]                          # every action keeps its undo
    s = state(mod, "file:write")
    assert ctx.prompts == [] and s.tier == mod.rule.T1 and s.series == 0 and s.successes == 12
    assert not [e for e in ledger(mod, "tier")]                          # no "Tenure granted" for unearned trust
    text = mod.cli.slash("status")
    assert "Trusted (until a mistake)" in text and "unchecked errors under" not in text


def test_a_fault_ends_the_trust_for_every_model_of_the_profile(plugin):
    mod, ctx = plugin(TRUST)
    ctx.call("terminal", NPM)                                            # model-a: trusted
    mod.pre_api_request(model="model-b", provider="nous", session_id="s1")
    ctx.call("terminal", NPM)
    mod.cli.flag("shell:npm", agent="model-b@nous")
    assert ctx.call("terminal", NPM) == "approved"
    mod.pre_api_request(model="model-a", provider="nous", session_id="s1")   # back to the first model
    assert ctx.call("terminal", NPM) == "approved"
    mod.pre_api_request(model="model-c", provider="nous", session_id="s1")   # and a new one
    assert ctx.call("terminal", NPM) == "approved"
    assert ctx.call("write_file", write("other")) == "ran"               # other types keep their trust


def test_refusing_hermes_own_prompt_on_a_trusted_call_is_a_fault(plugin):
    mod, ctx = plugin(TRUST)
    args = {"command": "rm -rf build"}
    assert pre(mod, "terminal", args, "h1") is None                      # tenure lets it through, Hermes asks
    mod.post_approval_response(pattern_key="recursive delete", tool_call_id="h1", choice="deny",
                               surface="cli", session_id="s1")
    post(mod, "terminal", args, "h1", status="blocked", result='{"error": "denied"}')
    s = state(mod, "shell:rm")
    assert s.faults == 1 and s.distrusted
    assert ctx.call("terminal", args) == "approved"


def test_without_a_start_setting_the_trusted_start_applies(plugin, monkeypatch):
    monkeypatch.setattr(mod_params(), "DEFAULT_START", "trusted")
    mod, ctx = plugin(FAST)
    assert mod.settings()["start"] == "trusted"
    assert ctx.call("write_file", write("d1")) == "ran" and ctx.prompts == []


def mod_params():
    from tenure import params
    return params


def test_the_study_start_asks_first(plugin):
    mod, ctx = plugin({**FAST, "start": "probation"})
    assert ctx.call("write_file", write("p1")) == "approved"


def test_the_passport_replays_a_trusted_record(plugin):
    mod, ctx = plugin(TRUST)
    ctx.call("write_file", write("r1"))
    ctx.call("terminal", NPM)
    mod.cli.flag("shell:npm", agent=A)
    replayed = mod.passport.replay(mod.store_().ledger())[A]
    for key in ("file:write", "shell:npm"):
        live, again = state(mod, key).to_dict(), replayed[key].to_dict()
        live.pop("changed_at"), again.pop("changed_at")
        assert live == again
    assert replayed["shell:npm"].distrusted and not replayed["file:write"].distrusted


def test_the_first_fault_says_so_in_the_chat(plugin):
    mod, ctx = plugin(TRUST)
    ctx.call("write_file", write("n1"))
    uid = int(ctx.posted[-1].rsplit(" ", 1)[1])
    out = mod.cli.slash(f"undo {uid}")
    assert "T1" in out and "On probation · file:write" in out
    tiers = [e for e in ledger(mod, "tier") if e.get("from") == "trusted"]
    assert len(tiers) == 1 and tiers[0]["to"] == mod.rule.T1
    assert mod._say(tiers, 0.1)[0].startswith("tenure · ↓ On probation · file:write")


def test_status_shows_trusted_types_and_the_start(plugin):
    mod, ctx = plugin(TRUST)
    ctx.call("terminal", NPM)
    text = mod.cli.slash("status")
    assert "Trusted start" in text and "Trusted (until a mistake)" in text


def test_the_start_command_saves_the_setting(plugin):
    mod, ctx = plugin(TRUST)
    assert mod.cli.slash("start probation").startswith("Study start")
    assert ctx.settings["start"] == "probation"
    assert ctx.call("write_file", write("st")) == "approved"


def test_a_state_stored_before_the_trusted_start_keeps_its_faults():
    from tenure import rule
    assert rule.TypeState.from_dict({"key": "file:write", "stakes": "low", "faults": 2}).distrusted
    assert not rule.TypeState.from_dict({"key": "file:write", "stakes": "low"}).distrusted


def test_the_signed_passport_says_trusted_not_earned_and_verifies(plugin, tmp_path):
    mod, ctx = plugin(TRUST)
    ctx.call("write_file", write("pp"))
    ctx.call("terminal", NPM)
    mod.pre_api_request(model="model-b", provider="nous", session_id="s1")
    ctx.call("terminal", NPM)
    mod.cli.flag("shell:npm", agent="model-b@nous")                     # ends the trust for model-a too
    rows = mod.store_().ledger()
    p = mod.passport.build(mod.store_(), A, mod.settings(), mod.data_dir(), redact=False, rows=rows)
    t = {e["type"]: e for e in p["types"]}
    assert t["file:write"]["trusted"] is True and t["shell:npm"]["trusted"] is False
    assert mod.passport.verify(p, rows) == []
