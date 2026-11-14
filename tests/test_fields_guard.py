"""The decision-time guard on field categories (spec §4.6): a sensitive kind of a tool asks while its tool, or a
recorded kind of the same tool whose categories overlap, carries an unredeemed fault. Read only; no session answer
for a category kind; no field name or value leaves the plugin (§4.8)."""
import glob
import json
import os

from test_plugin import A, plugin, state  # noqa: F401  (pytest fixture)

from tenure import i18n, rule


def seed(mod, key, stakes="medium", **kw):
    with mod.txn() as st:
        st.put_state(A, rule.TypeState(key=key, stakes=stakes, **kw))


P, F_ = "mcp:crm:update_contact", "mcp:crm:update_contact:@finance"
T3 = dict(tier=rule.T3, series=300, sessions=["a", "b"])
CAREFUL = {"preset": "careful", "fields": {"stakes": {"finance": "medium"}}}
FAST5 = {"risks": {"medium": 0.2}, "fields": {"stakes": {"finance": "medium"}}}


def test_new_category_asks_even_if_tool_is_t3(plugin):
    mod, ctx = plugin(CAREFUL); seed(mod, P, **T3)
    assert ctx.call("mcp__crm__update_contact", {"notes": "x"}) == "ran"
    assert ctx.call("mcp__crm__update_contact", {"iban": "x"}) == "approved"


def test_marked_tool_holds_an_earned_category(plugin):
    mod, ctx = plugin(CAREFUL); seed(mod, P, lengthened=True); seed(mod, F_, **T3)
    assert ctx.call("mcp__crm__update_contact", {"iban": "x"}) == "approved"
    assert i18n.tr("ask.why.held", type=F_, held=P) in ctx.prompts[-1]["message"]


def test_trusted_start_names_the_holding_tool(plugin):
    mod, ctx = plugin({"start": "trusted", "fields": {"stakes": {"finance": "medium"}}})
    seed(mod, P, lengthened=True); seed(mod, F_, **T3)
    assert ctx.call("mcp__crm__update_contact", {"iban": "x"}) == "approved"
    assert i18n.tr("ask.why.held", type=F_, held=P) in ctx.prompts[-1]["message"]


def test_tool_without_state_does_not_hold(plugin):
    mod, ctx = plugin(CAREFUL); seed(mod, F_, **T3)
    assert ctx.call("mcp__crm__update_contact", {"iban": "x"}) == "ran"


def test_overlapping_combination_holds(plugin):
    mod, ctx = plugin({"preset": "careful",
                       "fields": {"stakes": {"finance": "medium", "secret": "medium", "unclassified": "medium"}}})
    seed(mod, "mcp:crm:update_contact:@secret+finance", trial_left=2)
    seed(mod, "mcp:crm:update_contact:@secret+finance+unclassified", **T3)
    assert ctx.call("mcp__crm__update_contact", {"iban": "x", "password": "p", "fld0123456789abcd": 1}) == "approved"
    assert i18n.tr("ask.why.held", type="mcp:crm:update_contact:@secret+finance+unclassified",
                   held="mcp:crm:update_contact:@secret+finance") in ctx.prompts[-1]["message"]


def test_old_resolved_fault_on_t3_tool_does_not_hold(plugin):
    mod, ctx = plugin(CAREFUL); seed(mod, P, unresolved_fault=True, distrusted=True, **T3); seed(mod, F_, **T3)
    assert ctx.call("mcp__crm__update_contact", {"iban": "x"}) == "ran"


LOW_TOOL = {**CAREFUL, "types": {P: "low"}}


def test_low_fault_holds_until_back_at_t3(plugin):
    from tenure import cli
    mod, ctx = plugin(LOW_TOOL); seed(mod, P, stakes="low", **T3); seed(mod, F_, **T3)
    assert ctx.call("mcp__crm__update_contact", {"iban": "x"}) == "ran"
    cli.flag(P, agent=A)                                  # a real low-stakes fault: no trial, no wait, no lengthening
    s = state(mod, P)
    assert s.faults == 1 and s.tier != rule.T3 and not (s.lengthened or s.trial_left or s.trial_wait)
    assert ctx.call("mcp__crm__update_contact", {"iban": "x"}) == "approved"
    assert i18n.tr("ask.why.held", type=F_, held=P) in ctx.prompts[-1]["message"]
    for i in range(400):                                  # the tool earns T3 back: the hold lifts
        if state(mod, P).tier == rule.T3:
            break
        ctx.call("mcp__crm__update_contact", {"notes": "x"}, session=f"s{i % 3}")
    assert state(mod, P).tier == rule.T3 and state(mod, P).faults == 1
    assert ctx.call("mcp__crm__update_contact", {"iban": "x"}) == "ran"


def test_no_session_answer_for_a_category(plugin):
    mod, ctx = plugin({"start": "trusted", "fields": {"stakes": {"finance": "medium"}}})
    ctx.call("mcp__crm__update_contact", {"iban": "x"})
    assert ":session:" not in ctx.prompts[-1]["rule_key"]


def test_earned_notes_never_open_finance(plugin):
    mod, ctx = plugin(FAST5)
    for s in ("s1", "s2"):
        for _ in range(4):
            ctx.call("mcp__crm__update_contact", {"notes": "x"}, session=s)
    assert ctx.call("mcp__crm__update_contact", {"notes": "x"}, session="s2") == "ran"     # the tool has earned
    assert ctx.call("mcp__crm__update_contact", {"iban": "x"}, session="s2") == "approved"


def test_no_field_name_or_value_leaves(plugin):
    mod, ctx = plugin(CAREFUL)
    ctx.call("mcp__crm__update_contact", {"iban": "FR7612345", "notes": "secret-note"})
    from tenure import cli
    dump = json.dumps([r["event"] for r in mod.store_().ledger()]) + cli.passport_cmd(agent=A) + cli.card_text()
    for path in glob.glob(os.path.join(mod.data_dir(), "passport-*.json")):    # passport_cmd writes the passport
        with open(path, encoding="utf-8") as f:
            dump += f.read()
    assert "FR7612345" not in dump and "secret-note" not in dump and '"iban"' not in dump


def test_status_shows_held(plugin):
    mod, ctx = plugin(CAREFUL); seed(mod, P, lengthened=True); seed(mod, F_, **T3)
    from tenure import cli
    assert i18n.tr("cli.status.held", held=P) in cli.status_text(agent=A)


def test_status_signals_unknown_and_broken_vocabulary(plugin, monkeypatch, tmp_path):
    from tenure import cli, fields as F
    mod, ctx = plugin({"fields": {"enable": ["finances"]}}); seed(mod, P)
    assert "finances" in cli.status_text(agent=A)
    bad = tmp_path / "v.json"; bad.write_text("{"); monkeypatch.setattr(F, "DATA_PATH", bad)
    mod, ctx = plugin({}); seed(mod, P)
    assert i18n.tr("cli.status.fields.broken") in cli.status_text(agent=A)


def test_revoke_tool_revokes_its_categories(plugin):
    mod, ctx = plugin(CAREFUL); seed(mod, F_, **T3)                 # outil sans état
    from tenure import cli
    out = cli.revoke("mcp:crm:update_contact", agent=A)
    assert state(mod, F_).tier == rule.T1 and "@finance" in out


def test_revoke_does_not_touch_a_longer_tool_name(plugin):
    mod, ctx = plugin(CAREFUL); seed(mod, "mcp:crm:update_contact_email", **T3); seed(mod, F_, **T3)
    from tenure import cli
    cli.revoke("mcp:crm:update_contact", agent=A)
    assert state(mod, "mcp:crm:update_contact_email").tier == rule.T3
