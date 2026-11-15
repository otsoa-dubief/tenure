"""Flag one action: every action settled after it ran gets a number in a record of the last 24 hours (table
``recent``), with its session, agent, type, time, whether it already counted as a fault and its undo id; never an
argument."""
import json
import re
import os
import sqlite3
import time

from test_plugin import A, FAST, NPM, Picks, anon, climb, outcomes, plugin, post, pre, row, state, to_t3, write  # noqa: F401
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


# --------------------------------------------------------------------------------------- flag one action (task 5)
B = "model-b@nous"


def slash(mod, line, session="s1"):
    """The slash command as Hermes calls it: the session id comes in the keyword arguments."""
    return mod._slash(line, session_id=session)


def replay_matches(mod):
    live = {(a, s.key): s.to_dict() for a, s in mod.store_().states()}
    replayed = {(a, k): s.to_dict() for a, t in mod.passport.replay(mod.store_().ledger()).items()
                for k, s in t.items()}
    for d in list(live.values()) + list(replayed.values()):
        d.pop("changed_at")
    return replayed == live


def test_flag_n_hits_acting_agent_and_replays(plugin):
    """The fault falls on the agent that acted and on its type, even after the model changed (spec 4.5)."""
    mod, ctx = plugin(FAST)
    climb(ctx, 3)                                                    # model-a
    n = last(mod)["n"]
    mod.pre_api_request(model="model-b", provider="nous", session_id="s1")
    ctx.call("terminal", NPM)                                        # model-b acts on another type
    fa, fb = state(mod, "file:write").faults, state(mod, "file:write", B)
    out = slash(mod, f"flag {n}")
    assert A in out and "file:write" in out and f"{n}" in out
    b = state(mod, "file:write", B)
    assert state(mod, "file:write").faults == fa + 1
    assert (b.faults, b.tier, b.series, b.successes) == (fb.faults, fb.tier, fb.series, fb.successes)
    assert b.distrusted                         # only its trusted start ends for this type (spec 9, arbitration)
    e = outcomes(mod)[-1]
    assert (e["agent"], e["type"], e["result"], e["source"], e["session"]) == (A, "file:write", "fault", "flag", "")
    assert mod.store_().totals(A)["faults"] == 1 and mod.store_().totals(B)["faults"] == 0
    assert mod.store_().recent(n)["flagged"] is True
    assert replay_matches(mod)


def test_flag_n_uses_the_recorded_stakes(plugin):
    mod, ctx = plugin(FAST)
    climb(ctx, 2)
    s = state(mod, "file:write")
    slash(mod, "flag 1")
    e = outcomes(mod)[-1]
    assert (e["source"], e["stakes"], e["reversible"]) == ("flag", s.stakes, s.reversible)


def test_flag_n_twice_is_refused(plugin):
    mod, ctx = plugin(FAST)
    climb(ctx, 2)
    slash(mod, "flag 2")
    count, faults = len(ledger_rows(mod)), state(mod, "file:write").faults
    out = slash(mod, "flag 2")
    assert "already" in out
    assert len(ledger_rows(mod)) == count and state(mod, "file:write").faults == faults


def ledger_rows(mod):
    return mod.store_().ledger()


def test_flag_n_unknown_or_too_old(plugin):
    mod, ctx = plugin(FAST)
    climb(ctx, 1)
    count = len(ledger_rows(mod))
    assert "24" in slash(mod, "flag 99")
    with mod.txn() as st:
        st.db.execute("UPDATE recent SET at = at - 90000 WHERE n = 1")
    assert "24" in slash(mod, "flag 1")
    assert len(ledger_rows(mod)) == count


def test_flag_n_of_an_action_born_faulty_is_refused(plugin):
    mod, ctx = plugin(FAST)
    ctx.call("write_file", write("bad", "def x(:\n"))                  # failed check: already a fault
    faults, count = state(mod, "file:write").faults, len(ledger_rows(mod))
    assert "already" in slash(mod, "flag 1")
    assert state(mod, "file:write").faults == faults and len(ledger_rows(mod)) == count


def test_flag_n_from_another_session_is_accepted(plugin):
    mod, ctx = plugin(FAST)
    climb(ctx, 1, session="s2")
    faults = state(mod, "file:write").faults
    slash(mod, "flag 1", session="s1")
    assert state(mod, "file:write").faults == faults + 1


def test_flag_n_with_a_model_is_refused(plugin):
    mod, ctx = plugin(FAST)
    climb(ctx, 1)
    count = len(ledger_rows(mod))
    out = slash(mod, "flag 1 --model model-a")
    assert "--model" in out and len(ledger_rows(mod)) == count
    assert run(mod, "flag 1 --model model-a")[1] == 1


def run(mod, line):
    import shlex
    p = mod.cli._Parser(prog="x", add_help=False)
    mod.cli._add_subcommands(p)
    return mod.cli.execute(p.parse_args(shlex.split(line)))


def test_flag_then_undo_one_fault(plugin):
    mod, ctx = plugin(FAST)
    climb(ctx, 12)
    ctx.call("write_file", write("u"))
    uid = int(ctx.posted[-1].rsplit(" ", 1)[1])
    n = last(mod)["n"]
    faults = state(mod, "file:write").faults
    slash(mod, f"flag {n}")
    assert state(mod, "file:write").faults == faults + 1
    assert mod.store_().get_undo(uid)["fault"] is True
    out = slash(mod, f"undo {uid}")
    assert "files restored" in out and "no second fault" in out
    assert state(mod, "file:write").faults == faults + 1
    assert len(outcomes(mod, result="fault")) == 1 and replay_matches(mod)


def test_undo_then_flag_refused(plugin):
    mod, ctx = plugin(FAST)
    climb(ctx, 12)
    ctx.call("write_file", write("u"))
    uid = int(ctx.posted[-1].rsplit(" ", 1)[1])
    n = last(mod)["n"]
    slash(mod, f"undo {uid}")
    faults = state(mod, "file:write").faults
    assert "already" in slash(mod, f"flag {n}")
    assert state(mod, "file:write").faults == faults and len(outcomes(mod, result="fault")) == 1


def test_flag_type_is_unchanged(plugin):
    mod, ctx = plugin(FAST)
    climb(ctx, 1)
    out = slash(mod, "flag file:write a note")
    assert "fault recorded on file:write" in out and outcomes(mod)[-1]["source"] == "flag"


# ------------------------------------------------------------------------------------------------ the list
def test_slash_lists_the_session_with_the_target(plugin):
    mod, ctx = plugin(FAST)
    ctx.call("write_file", {"path": "src/target_one.py", "content": "x = 1\n"})
    ctx.call("terminal", {"command": "npm test -- --grep target_two"})
    out = slash(mod, "flag")
    lines = out.splitlines()
    assert "src/target_one.py" in out and "target_two" in out
    assert out.index("target_two") < out.index("target_one")            # newest first
    assert "shell:npm" in out and "file:write" in out
    assert not any("hermes tenure flag" in ln for ln in lines)          # nothing elsewhere in the profile
    assert "/tenure flag" in out


def test_slash_list_tells_other_actions_of_the_profile(plugin):
    mod, ctx = plugin(FAST)
    climb(ctx, 1, session="s1")
    climb(ctx, 2, session="child")                                     # a subagent has its own session
    out = slash(mod, "flag")
    assert "src/as10.py" in out and "childs" not in out.replace("hermes tenure flag", "")
    assert "2 other actions" in out and "hermes tenure flag" in out
    climb(ctx, 1, session="other2")
    assert "3 other actions" in slash(mod, "flag")


def test_slash_without_session_lists_the_profile(plugin):
    mod, ctx = plugin(FAST)
    climb(ctx, 1, session="s1")
    climb(ctx, 1, session="s2")
    out = mod._slash("flag")
    assert "src/as10.py" in out and "src/as20.py" in out and "other action" not in out


def test_cli_lists_the_profile_without_the_target_but_a_t2_file(plugin):
    """Another process: no summary in memory. A T2 action still shows its file, from its undo snapshot."""
    mod, ctx = plugin(FAST)
    climb(ctx, 12)
    ctx.call("write_file", write("t2file"))                            # T2: acts, snapshot taken
    ctx.call("terminal", {"command": "npm test -- --grep hidden_word"})
    uid = int([p for p in ctx.posted if "/tenure undo" in p][-1].rsplit(" ", 1)[1])
    with mod.ST.mem:
        mod.ST.summaries.clear()
    text, code = run(mod, "flag")
    assert code == 0 and "hidden_word" not in text and "src/as10.py" not in text
    assert "t2file.py" in text and str(uid) in text
    assert "hermes tenure flag" in text and "other action" not in text


def test_memory_summary_keyed_by_store(plugin, tmp_path, monkeypatch):
    """Two profiles in one process, the same number in each: each shows its own target, never the other's."""
    mod, ctx = plugin(FAST)
    first = tmp_path / "hermes"
    reopen(mod, monkeypatch, first)
    ctx.call("write_file", {"path": "src/first_profile.py", "content": "x = 1\n"})
    second = tmp_path / "other"
    reopen(mod, monkeypatch, second)
    mod.pre_api_request(model="model-a", provider="nous", session_id="s1")
    ctx.call("write_file", {"path": "src/second_profile.py", "content": "x = 1\n"})
    assert last(mod)["n"] == 1
    out = slash(mod, "flag")
    assert "second_profile" in out and "first_profile" not in out
    reopen(mod, monkeypatch, first)
    out = slash(mod, "flag")
    assert "first_profile" in out and "second_profile" not in out


def test_memory_summary_needs_the_same_time(plugin):
    mod, ctx = plugin(FAST)
    ctx.call("write_file", {"path": "src/timed.py", "content": "x = 1\n"})
    assert "timed.py" in slash(mod, "flag")
    with mod.txn() as st:
        st.db.execute("UPDATE recent SET at = at - 1 WHERE n = 1")      # another row under the same number
    assert "timed.py" not in slash(mod, "flag")


def test_memory_cleared_no_target(plugin):
    mod, ctx = plugin(FAST)
    ctx.call("write_file", {"path": "src/forgot.py", "content": "x = 1\n"})
    with mod.ST.mem:
        mod.ST.summaries.clear()
    out = slash(mod, "flag")
    assert "forgot.py" not in out and "file:write" in out


def test_memory_summaries_are_bounded(plugin):
    mod, ctx = plugin(FAST)
    with mod.ST.mem:
        for i in range(600):
            mod._remember_summary("x.db", i, 0.0, "s")
    assert len(mod.ST.summaries) == 500 and ("x.db", 599) in mod.ST.summaries and ("x.db", 0) not in mod.ST.summaries


def test_list_is_filtered_to_24_hours_without_writing(plugin, monkeypatch):
    mod, ctx = plugin(FAST)
    climb(ctx, 2)
    later = time.time() + 25 * 3600
    monkeypatch.setattr(mod.store.time, "time", lambda: later)
    out = mod.cli.flag_list(None)
    assert "file:write" not in out
    db = sqlite3.connect(mod.store_().path)
    assert db.execute("SELECT COUNT(*) FROM recent").fetchone()[0] == 2  # read only: no purge


def test_list_shows_the_agent_and_the_undo_number(plugin):
    mod, ctx = plugin(FAST)
    climb(ctx, 12)
    ctx.call("write_file", write("w"))
    uid = int(ctx.posted[-1].rsplit(" ", 1)[1])
    out = slash(mod, "flag")
    row13 = [ln for ln in out.splitlines() if ln.strip().startswith("13 ")][0]
    assert A in row13 and row13.rstrip().endswith(str(uid))


def test_empty_list(plugin):
    mod, ctx = plugin(FAST)
    out = slash(mod, "flag")
    assert "24" in out and "file:write" not in out


def test_flag_n_stores_no_note(plugin):
    mod, ctx = plugin(FAST)
    climb(ctx, 1)
    slash(mod, "flag 1 zebra-quartz-7731 wrong file")
    assert outcomes(mod)[-1]["source"] == "flag"
    dump = "\n".join(sqlite3.connect(mod.store_().path).iterdump())
    assert "zebra-quartz-7731" not in dump and "zebra-quartz-7731" not in json.dumps(mod.store_().ledger())


# ---------------------------------------------------------------------------------- final review (15/11)
def test_a_cross_drive_path_does_not_abort_the_settlement(plugin, monkeypatch):
    """Windows: relpath raises ValueError across drives; the action still settles, the path stays absolute."""
    mod, ctx = plugin(FAST)
    climb(ctx, 12)                                                              # T2

    def cross_drive(path, start=None):
        raise ValueError("path is on mount 'C:', start on mount 'D:'")
    monkeypatch.setattr(os.path, "relpath", cross_drive)
    before = len(outcomes(mod))
    assert ctx.call("write_file", write("w")) == "ran"
    assert len(outcomes(mod)) == before + 1 and outcomes(mod)[-1]["source"] == "notify"
    assert last(mod)["n"] == 13 and mod.store_().pending_rows(anon("s1"), "tc-13") == []
    text = [p for p in ctx.posted if "/tenure undo" in p][-1]
    full = os.path.join(ctx.cwd, "src", "w.py").replace(os.sep, "/").replace("\\", "/")   # absolute, slashes, cap 120
    assert f"({full[:80]}" in text and f"{full[-39:]})" in text


def test_any_display_error_leaves_the_settlement_whole(plugin, monkeypatch):
    mod, ctx = plugin(FAST)
    climb(ctx, 12)

    def broken(*a, **k):
        raise RuntimeError("display")
    monkeypatch.setattr(mod, "_show", broken)
    assert ctx.call("write_file", write("w")) == "ran"
    assert outcomes(mod)[-1]["source"] == "notify" and last(mod)["n"] == 13
    assert re.fullmatch(r"tenure: file:write acted, then told you · /tenure undo \d+", ctx.posted[-1])


def test_a_summary_error_does_not_drop_the_t2_notice(plugin, monkeypatch):
    mod, ctx = plugin(FAST)
    climb(ctx, 12)
    count = len(ctx.posted)

    def broken(*a, **k):
        raise RuntimeError("summary")
    assert pre(mod, "write_file", write("w"), "w1") is None                    # T2: no prompt
    os.makedirs(os.path.join(ctx.cwd, "src"), exist_ok=True)
    with open(os.path.join(ctx.cwd, "src", "w.py"), "w", encoding="utf-8") as f:
        f.write("x = 1\n")
    monkeypatch.setattr(mod.classify, "_summary", broken)                      # fails at settlement only
    post(mod, "write_file", write("w"), "w1")
    assert outcomes(mod)[-1]["source"] == "notify"
    assert len(ctx.posted) > count and "/tenure undo" in ctx.posted[-1]


def test_t2_message_caps_each_path_and_keeps_the_undo_id_last(plugin):
    mod, ctx = plugin(FAST)
    climb(ctx, 12)
    deep = "/".join(["d" * 40] * 5)
    assert ctx.call("write_file", {"path": f"src/{deep}/tail.py", "content": "x = 1\n"}) == "ran"
    text = ctx.posted[-1]
    shown = text[text.index("(") + 1:text.rindex(")")]
    assert len(shown) == 120 and "…" in shown and shown.endswith("tail.py") and shown.startswith("src/d")
    assert text.rsplit(" ", 1)[1].isdigit()


def test_show_caps_with_a_middle_ellipsis():
    import tenure
    long = "a" * 100 + "/" + "b" * 100
    s = tenure._show(long, "", "")
    assert s == long[:80] + "…" + long[-39:] and len(s) == 120
    assert tenure._show("a" * 120, "", "") == "a" * 120


def test_failed_check_messages_name_the_written_path(plugin):
    mod, ctx = plugin(FAST)
    climb(ctx, 12)
    assert ctx.call("write_file", write("bad2", "def y(:\n")) == "ran"
    text = [p for p in ctx.posted if "automatic check failed" in p][-1]
    assert "src/bad2.py" in text and "/tenure undo" in text                    # settle.acted_fault
    assert ctx.call("write_file", write("bad", "def x(:\n")) == "approved"   # the fault dropped the type
    text = [p for p in ctx.posted if "automatic check failed" in p][-1]
    assert "src/bad.py" in text and "/tenure undo" not in text                 # settle.check_failed


def test_flag_a_huge_number_is_unknown_on_slash_and_cli(plugin):
    mod, ctx = plugin(FAST)
    climb(ctx, 1)
    count = len(ledger_rows(mod))
    out = slash(mod, "flag 99999999999999999999")
    assert "24" in out and "Error" not in out
    text, code = run(mod, "flag 99999999999999999999")
    assert "24" in text and code == 1
    assert len(ledger_rows(mod)) == count


def test_flag_a_five_thousand_digit_number_is_unknown_not_a_crash(plugin):
    mod, ctx = plugin(FAST)
    climb(ctx, 1)
    count = len(ledger_rows(mod))
    huge = "9" * 5000
    out = slash(mod, "flag " + huge)
    assert "24" in out and "Error" not in out and "ValueError" not in out
    text, code = run(mod, "flag " + huge)
    assert "24" in text and code == 1
    assert len(ledger_rows(mod)) == count


def test_motdepasse_is_masked_in_a_summary():
    from tenure import classify as C
    s = C._summary("mcp__x__login", {"motdepasse": "hunter2", "user_id": "42"}, "mcp:x:login")
    assert "hunter2" not in s and "\u2022\u2022\u2022" in s
