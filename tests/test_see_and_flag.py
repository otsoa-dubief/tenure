"""Flag one action: every action settled after it ran gets a number in a record of the last 24 hours (table
``recent``), with its session, agent, type, time, whether it already counted as a fault and its undo id; never an
argument."""
import json
import os
import sqlite3
import time

from test_plugin import A, FAST, NPM, Picks, anon, climb, outcomes, plugin, pre, row, state, to_t3, write  # noqa: F401
from test_copied_profile import clone, reopen


def recent(mod):
    """Every numbered action, oldest first."""
    return list(reversed(mod.store_().recent_rows(None, limit=1000)))


def last(mod):
    rows = recent(mod)
    return rows[-1] if rows else None


def test_each_settled_path_gets_a_number(plugin):
    mod, ctx = plugin(FAST)
    assert ctx.call("write_file", write("ok")) == "approved"
    r = last(mod)
    assert (r["n"], r["session"], r["agent"], r["type"], r["flagged"], r["undo_id"]) == (
        1, anon("s1"), A, "file:write", False, None)
    assert abs(r["at"] - time.time()) < 60
    ctx.call("write_file", write("err"), status="error")                       # error
    ctx.call("terminal", {"command": "npm test", "background": True})           # background
    assert [(e["source"], n["type"]) for e, n in zip(outcomes(mod), recent(mod))] == [
        ("approval", "file:write"), ("error", "file:write"), ("background", "shell:npm")]
    assert [n["n"] for n in recent(mod)] == [1, 2, 3]


def test_spot_and_alone_are_numbered(plugin):
    mod, ctx = plugin(FAST)
    to_t3(ctx)                                                                  # 4 approvals
    assert len(recent(mod)) == 4
    mod.ST.rng = Picks([0.0])
    assert ctx.call("write_file", write("spot")) == "approved"
    assert outcomes(mod)[-1]["source"] == "spot" and last(mod)["n"] == 5 and not last(mod)["flagged"]
    assert ctx.call("write_file", write("alone")) == "ran"
    assert outcomes(mod)[-1]["source"] == "alone" and last(mod)["n"] == 6


def test_notify_is_numbered_with_its_undo(plugin):
    mod, ctx = plugin(FAST)
    climb(ctx, 12)                                                              # T2: acts, then notifies
    assert ctx.call("write_file", write("n")) == "ran"
    uid = int(ctx.posted[-1].rsplit(" ", 1)[1])
    assert outcomes(mod)[-1]["source"] == "notify"
    assert (last(mod)["n"], last(mod)["undo_id"], last(mod)["flagged"]) == (13, uid, False)


def test_nobody_is_numbered_but_a_cron_refusal_is_not(plugin):
    mod, ctx = plugin(FAST, cron=True)
    assert ctx.call("terminal", NPM) == "blocked"                               # cron_mode denies: never ran
    assert outcomes(mod)[-1]["source"] == "nobody" and recent(mod) == []
    ctx.cron_mode = "approve"
    assert ctx.call("terminal", NPM) == "ran"
    assert outcomes(mod)[-1]["source"] == "nobody" and [r["type"] for r in recent(mod)] == ["shell:npm"]


def test_failed_checks_are_born_flagged(plugin):
    mod, ctx = plugin(FAST)
    assert ctx.call("write_file", write("bad", "def x(:\n")) == "approved"
    assert outcomes(mod)[-1]["source"] == "check" and last(mod)["flagged"] is True
    to_t3(ctx)
    mod.ST.rng = Picks([0.0])
    assert ctx.call("write_file", write("bad2", "def y(:\n")) == "approved"     # an approved spot check, failing
    assert (outcomes(mod)[-1]["result"], outcomes(mod)[-1]["source"]) == ("fault", "spot")
    assert last(mod)["flagged"] is True
    assert [r["flagged"] for r in recent(mod)] == [True, False, False, False, False, True]


def test_t2_failed_check_links_its_undo_and_is_flagged(plugin):
    mod, ctx = plugin(FAST)
    climb(ctx, 12)
    assert ctx.call("write_file", write("bad", "def x(:\n")) == "ran"
    uid = int([p for p in ctx.posted if "/tenure undo" in p][-1].rsplit(" ", 1)[1])
    assert outcomes(mod)[-1]["source"] == "check"
    assert (last(mod)["flagged"], last(mod)["undo_id"]) == (True, uid)
    assert mod.store_().get_undo(uid)["fault"] is True


def test_unnumbered_paths(plugin):
    mod, ctx = plugin(FAST)
    assert pre(mod, "read_file", {"path": "a.py"}, "f") is None                 # free
    assert pre(mod, "write_file", {"path": ".env"}, "c")["action"] == "approve"  # capped
    assert ctx.call("write_file", write("no"), answer="deny") == "refused"     # refusal
    assert ctx.call("write_file", write("b"), blocked_after=True) == "approved"  # blocked after our decision
    assert outcomes(mod)[-1]["source"] == "blocked"
    d = pre(mod, "write_file", write("old"), "old")                             # expired
    mod.post_approval_response(pattern_key=f"plugin_rule:{d['rule_key']}", tool_call_id="old", choice="once",
                               surface="cli", session_key="s1")
    with mod.txn() as st:
        st.db.execute("UPDATE pending SET at = at - 90000")
    ctx.call("terminal", NPM, answer="deny")                                    # expires it, then refused
    assert row(mod, "old") is None and [e["source"] for e in outcomes(mod)][-2:] == ["expired", "refusal"]
    assert recent(mod) == []


def test_ambiguous_rows_get_no_number(plugin):
    mod, ctx = plugin(FAST)
    for _ in range(2):
        d = mod.pre_tool_call(tool_name="terminal", args=NPM, session_id=None, task_id=None, tool_call_id="call_0")
        mod.post_approval_response(pattern_key=f"plugin_rule:{d['rule_key']}", tool_call_id="call_0", choice="once")
    mod.post_tool_call(tool_name="terminal", args=NPM, session_id=None, task_id=None, tool_call_id="call_0",
                       result='{"exit_code": 0}', status="ok")
    assert [e["source"] for e in outcomes(mod)] == ["ambiguous"] * 2 and recent(mod) == []


def test_settle_hands_the_number_and_its_time_on(plugin):
    mod, ctx = plugin(FAST)
    d = pre(mod, "write_file", write(), "c1")
    mod.post_approval_response(pattern_key=f"plugin_rule:{d['rule_key']}", tool_call_id="c1", choice="once",
                               surface="cli", session_key="s1")
    cfg = mod.settings()
    with mod.txn() as st:
        p = st.pop_pending(row(mod, "c1")["id"])
        mod._settle(st, cfg, p, blocked=False, failed=False, reason=None)
    assert p["n"] == 1 and p["n_at"] == mod.store_().recent(1)["at"]
    with mod.txn() as st:
        q = {k: v for k, v in p.items() if k not in ("n", "n_at")}
        mod._settle(st, cfg, q, blocked=True, failed=False, reason=None)
    assert "n" not in q and len(recent(mod)) == 1


def test_undo_flags_its_action(plugin):
    mod, ctx = plugin(FAST)
    climb(ctx, 12)
    ctx.call("write_file", write("u"))
    uid = int(ctx.posted[-1].rsplit(" ", 1)[1])
    n = last(mod)["n"]
    with mod.txn() as st:
        msg = mod.undo_entry(st, uid)
    msg.cleanup()
    assert msg.ok and outcomes(mod)[-1]["source"] == "undo"
    assert mod.store_().recent(n)["flagged"] is True


def test_undo_of_an_action_already_counted_counts_no_second_fault(plugin):
    """A flag marks the snapshot (mark_undo_fault): the undo that follows restores the files and counts nothing."""
    mod, ctx = plugin(FAST)
    climb(ctx, 12)
    ctx.call("write_file", write("u"))
    uid = int(ctx.posted[-1].rsplit(" ", 1)[1])
    n = last(mod)["n"]
    with mod.txn() as st:
        st.mark_flagged(n)
        st.mark_undo_fault(uid)
    faults, count = state(mod, "file:write").faults, len(outcomes(mod))
    with mod.txn() as st:
        msg = mod.undo_entry(st, uid)
    msg.cleanup()
    assert msg.ok and "no second fault" in msg and "flag" in msg
    assert state(mod, "file:write").faults == faults and len(outcomes(mod)) == count
    assert mod.store_().get_undo(uid)["undone"] is True and mod.store_().recent(n)["flagged"] is True


def test_a_copied_profile_starts_with_an_empty_record(plugin, tmp_path, monkeypatch):
    mod, ctx = plugin(FAST)
    climb(ctx, 3)
    assert len(recent(mod)) == 3
    original = tmp_path / "hermes"
    reopen(mod, monkeypatch, original)
    copy = clone(original)
    reopen(mod, monkeypatch, copy)
    assert recent(mod) == []
    reopen(mod, monkeypatch, original)
    assert len(recent(mod)) == 3


def test_the_record_holds_no_argument(plugin):
    mod, ctx = plugin(FAST)
    secret = "zebra-quartz-7731"
    ctx.call("write_file", {"path": f"src/{secret}.py", "content": f"x = '{secret}'\n"})
    ctx.call("terminal", {"command": f"npm test -- {secret}"})
    assert len(recent(mod)) == 2
    db = sqlite3.connect(mod.store_().path)
    dump = "\n".join(db.iterdump())
    rows = [line for line in dump.splitlines() if 'INSERT INTO "recent"' in line]
    assert len(rows) == 2 and not any(secret in r or "src/" in r or "npm test" in r for r in rows)
    assert json.dumps(recent(mod)).count(secret) == 0 and os.path.basename(mod.store_().path) == "tenure.db"
