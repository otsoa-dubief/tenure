"""The decision-time guard on field categories (spec §4.6): a sensitive kind of a tool asks while its tool, or a
recorded kind of the same tool whose categories overlap, carries an unredeemed fault. Read only; no session answer
for a category kind; no field name or value leaves the plugin (§4.8)."""
import glob
import json
import os

from test_plugin import A, plugin, state  # noqa: F401  (pytest fixture)

from tenure import rule


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
    assert ctx.prompts[-1]["message"].count("mcp:crm:update_contact") >= 2      # the kind and the tool holding it


def test_tool_without_state_does_not_hold(plugin):
    mod, ctx = plugin(CAREFUL); seed(mod, F_, **T3)
    assert ctx.call("mcp__crm__update_contact", {"iban": "x"}) == "ran"


def test_overlapping_combination_holds(plugin):
    mod, ctx = plugin({"preset": "careful",
                       "fields": {"stakes": {"finance": "medium", "secret": "medium", "unclassified": "medium"}}})
    seed(mod, "mcp:crm:update_contact:@secret+finance", trial_left=2)
    seed(mod, "mcp:crm:update_contact:@secret+finance+unclassified", **T3)
    assert ctx.call("mcp__crm__update_contact", {"iban": "x", "password": "p", "fld0123456789abcd": 1}) == "approved"
    assert "@secret+finance" in ctx.prompts[-1]["message"]


def test_old_resolved_fault_on_t3_tool_does_not_hold(plugin):
    mod, ctx = plugin(CAREFUL); seed(mod, P, unresolved_fault=True, distrusted=True, **T3); seed(mod, F_, **T3)
    assert ctx.call("mcp__crm__update_contact", {"iban": "x"}) == "ran"


def test_low_fault_wait_holds(plugin):
    mod, ctx = plugin(CAREFUL); seed(mod, P, stakes="low", trial_wait=50); seed(mod, F_, **T3)
    assert ctx.call("mcp__crm__update_contact", {"iban": "x"}) == "approved"


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
