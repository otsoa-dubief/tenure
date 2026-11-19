"""The audit of the whole 1.3 work (19/11): interactions between the changes merged since 1.2.0."""
import json
import os

from test_plugin import A, FAST, outcomes, plugin  # noqa: F401
from test_trust import TRUST
from tenure import rule
from test_rule import state


def test_the_climb_checks_the_sessions_on_the_trimmed_series():
    """A capped series: the oldest success leaves before the climb looks at the sessions (rule B/2)."""
    s = state("medium")
    s.series, s.sessions = 10, ["A", "B", "C"]
    s.session_runs = [["A", 1], ["B", 6], ["C", 3]]
    rule.on_success(s, 10, session="C", source="approval")
    assert s.session_runs == [["B", 6], ["C", 4]]
    assert s.tier != rule.T3 and not rule.sessions_met(s)


def test_a_reused_call_id_never_carries_an_older_fresh_script(plugin):
    mod, ctx = plugin(TRUST)
    ctx.call("write_file", {"path": "a.py", "content": "print(1)\n"})
    assert ctx.call("terminal", {"command": "python a.py"}, answer="timeout", call_id="call_0") == "refused"   # unanswered: no fault
    assert ctx.call("terminal", {"command": "npm install left-pad"}, call_id="call_0") == "approved"
    assert ctx.call("terminal", {"command": "python a.py"}) == "approved"        # still fresh: asked again


def test_a_grouped_message_never_hands_a_ready_made_ok_list():
    import tenure
    assert "/tenure ok 7" in tenure._with_ok("x · /tenure undo 7", [7])
    many = tenure._with_ok("x · /tenure undo 9", [7, 8, 9])
    assert "7 8 9" not in many and "/tenure ok" in many and many.endswith("/tenure undo 9")


def test_a_file_broken_by_a_call_that_then_fails_is_a_fault(plugin):
    mod, ctx = plugin(FAST)
    path = os.path.join(ctx.cwd, "cfg.json")
    with open(path, "w") as f:
        f.write('{"a": 1}\n')
    post = ctx.hooks["post_tool_call"]

    def breaks_then_fails(**kw):
        with open(path, "w") as f:
            f.write('{"a": \n')
        return post(**kw)
    ctx.hooks["post_tool_call"] = breaks_then_fails
    ctx.call("write_file", {"path": "cfg.json", "content": '{"a": \n'}, status="error")
    assert (outcomes(mod)[-1]["result"], outcomes(mod)[-1]["source"]) == ("fault", "check")


def test_a_refused_action_of_an_earned_t3_is_detection_not_excusable(plugin):
    from test_plugin import Picks, pre, row, to_t3, write
    mod, ctx = plugin(FAST)
    to_t3(ctx)
    mod.ST.rng = Picks([0.99])                                    # no spot check drawn: it acts alone
    assert pre(mod, "write_file", write("t3"), "x") is None and row(mod, "x")["phase"] == "alone"
    mod.post_approval_response(pattern_key="dangerous", tool_call_id="x", choice="deny", session_id="s1")
    last = outcomes(mod)[-1]
    assert (last["result"], last["source"]) == ("fault", "spot")
    assert mod.excusable(mod.store_()) == []


def test_at_most_three_excuses_per_type_a_week_and_one_hint_a_day(plugin):
    from test_plugin import write
    mod, ctx = plugin(TRUST)
    hints = 0
    for i in range(4):
        ctx.call("write_file", write(f"u{i}"))                      # trusted: acts, with an undo
        out = mod.cli.slash(f"undo {int(ctx.posted[-1].rsplit(' ', 1)[1])}")
        hints += "/tenure excuse" in out
        open_ = mod.excusable(mod.store_())
        if i < 3:
            mod.cli.slash(f"excuse {open_[0]['seq']}")
        else:
            assert open_ == []                                    # the fourth fault of the week stays a fault
    assert hints == 1


def test_a_passport_shows_a_guarantee_only_for_an_earned_t3(plugin):
    mod, ctx = plugin(FAST)
    from test_plugin import climb, to_t3, write
    to_t3(ctx)
    ctx.call("terminal", {"command": "npm test"})
    p = mod.passport.build(mod.store_(), A, mod.settings(), mod.data_dir())
    g = {e["type"]: e["guarantee"] for e in p["types"]}
    assert g["file:write"]["aoql"] > 0 and any(v is None for k, v in g.items() if k != "file:write")
