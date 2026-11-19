"""Unseen successes (audit 19/11, item 4): an earned act-then-tell success is credited only once its undo window closed
unused; a subagent's session counts as its root session for the two-sessions condition."""
from test_plugin import A, FAST, climb, credit_now, outcomes, plugin, state, write  # noqa: F401
from test_see_and_flag import replay_matches


def test_an_undone_action_is_never_credited(plugin):
    mod, ctx = plugin(FAST)
    climb(ctx, 12)                                                   # T2
    assert ctx.call("write_file", write("n")) == "ran"
    uid = int(ctx.posted[-1].rsplit(" ", 1)[1])
    mod.cli.slash(f"undo {uid}")
    faults = state(mod, "file:write").faults
    credit_now(mod)
    assert state(mod, "file:write").faults == faults and outcomes(mod)[-1]["source"] == "undo"


def test_a_flagged_action_is_never_credited(plugin):
    mod, ctx = plugin(FAST)
    climb(ctx, 12)
    ctx.call("write_file", write("n"))
    from test_see_and_flag import last
    mod.cli.slash(f"flag {last(mod)['n']}")
    successes = state(mod, "file:write").successes
    credit_now(mod)
    assert state(mod, "file:write").successes == successes


def test_a_later_fault_on_the_type_turns_the_credit_neutral(plugin):
    mod, ctx = plugin(FAST)
    climb(ctx, 12)
    ctx.call("write_file", write("n"))                               # acted, then told: pending credit
    ctx.call("write_file", write("bad", "def x(:\n"))                # a later fault: the series restarts
    series = state(mod, "file:write").series
    credit_now(mod)
    s = state(mod, "file:write")
    assert s.series == series and outcomes(mod)[-1]["source"] == "expired"
    assert replay_matches(mod)


def test_credits_happen_on_the_next_call_after_the_window(plugin):
    mod, ctx = plugin(FAST)
    climb(ctx, 12)
    ctx.call("write_file", write("n"))
    with mod.txn() as st:
        st.db.execute("UPDATE undo SET at = at - 86401")
    before = state(mod, "file:write").successes
    ctx.call("terminal", {"command": "ls"})                          # any call that reaches tenure's decision
    ctx.call("write_file", write("m"))
    assert state(mod, "file:write").successes >= before + 1
    assert replay_matches(mod)


def test_a_subagent_session_counts_as_its_root(plugin):
    mod, ctx = plugin(FAST)
    mod.subagent_start(parent_session_id="s1", child_session_id="kid")
    climb(ctx, 2, session="s1")
    climb(ctx, 2, session="kid")
    s = state(mod, "file:write")
    assert len(s.sessions) == 1 and s.tier != mod.rule.T3            # one conversation, even with a subagent
    climb(ctx, 1, session="s2")
    assert len(state(mod, "file:write").sessions) == 2
    assert replay_matches(mod)
