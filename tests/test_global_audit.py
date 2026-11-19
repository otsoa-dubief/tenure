"""The audit of the whole 1.3 work (19/11): interactions between the changes merged since 1.2.0."""
import json
import os

from test_plugin import FAST, outcomes, plugin  # noqa: F401
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
