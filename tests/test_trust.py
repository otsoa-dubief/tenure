"""The trusted start: no question Hermes would not ask, until a type makes its first fault. Then the study rule
applies to that type, from T1. Actions that leave the machine, self-protection and suspended sessions still ask."""
import os

from test_plugin import A, FAST, NPM, climb, ledger, outcomes, plugin, state, write  # noqa: F401

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
    climb(ctx, 14, name="back")                                          # the study's Wald climb, after a fault
    assert state(mod, "file:write").tier == mod.rule.T1
    climb(ctx, 1, name="last")
    assert state(mod, "file:write").tier == mod.rule.T2 and len(ctx.prompts) == 16


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


def test_trust_never_asks_for_a_spot_check(plugin):
    mod, ctx = plugin(TRUST)
    mod.ST.rng.values = [0.0] * 20                                       # every draw would be a spot check
    for i in range(8):
        assert ctx.call("write_file", write(f"sp{i}"), session=f"s{i % 2}") == "ran"
    assert ctx.prompts == []


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
