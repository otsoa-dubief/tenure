"""A verifier (#6): a deterministic check of the owner's reports a fault or a doubt on one action that already ran,
named by its number or by (session, tool call id). Never a success."""
import pytest

from test_plugin import A, FAST, Picks, anon, climb, outcomes, plugin, state, to_t3, write  # noqa: F401
from test_see_and_flag import last, ledger_rows, recent, replay_matches, run, slash


def test_the_call_id_is_kept_hashed(plugin):
    mod, ctx = plugin(FAST)
    ctx.call("write_file", write("a"), call_id="call_abc")
    r = last(mod)
    assert r["call"] == anon("call_abc") and "call_abc" not in str(r)


def test_fault_by_call_is_a_flag(plugin):
    mod, ctx = plugin(FAST)
    climb(ctx, 2)
    ctx.call("write_file", write("x"), call_id="call_7", session="s9")
    n, faults = last(mod)["n"], state(mod, "file:write").faults
    out = mod.cli.report("fault", session="s9", call="call_7")
    assert f"{n}" in out and "file:write" in out
    assert state(mod, "file:write").faults == faults + 1
    e = outcomes(mod)[-1]
    assert (e["agent"], e["type"], e["result"], e["source"]) == (A, "file:write", "fault", "flag")
    assert mod.store_().recent(n)["flagged"] is True and replay_matches(mod)
    count = len(ledger_rows(mod))
    with pytest.raises(mod.cli.CliError, match="already"):                 # once per action
        mod.cli.report("fault", session="s9", call="call_7")
    assert "already" in slash(mod, f"flag {n}") and len(ledger_rows(mod)) == count


def test_a_verifier_fault_adds_no_event_kind_and_is_not_counted_in_a_wait(plugin):
    mod, ctx = plugin(FAST)
    ctx.call("write_file", write("x"), call_id="c1")
    kinds = {r["event"]["event"] for r in ledger_rows(mod)}
    mod.cli.report("fault", n=last(mod)["n"])
    assert {r["event"]["event"] for r in ledger_rows(mod)} - kinds <= {"tier", "trial"}          # no new kind of event
    assert ("fault", "flag") not in mod.store.COUNTED                                # never counted twice in a wait


def test_the_call_id_alone_is_not_enough(plugin):
    mod, ctx = plugin(FAST)
    ctx.call("write_file", write("a"), call_id="same", session="s1")
    ctx.call("write_file", write("b"), call_id="same", session="s2")              # call ids are reused
    count = len(ledger_rows(mod))
    with pytest.raises(mod.cli.CliError, match="24"):
        mod.cli.report("fault", session="s3", call="same")
    mod.cli.report("fault", session="s2", call="same")
    assert recent(mod)[-1]["flagged"] and not recent(mod)[-2]["flagged"] and len(ledger_rows(mod)) > count


def test_an_ambiguous_pair_is_refused(plugin):
    mod, ctx = plugin(FAST)
    ctx.call("write_file", write("a"), call_id="dup")
    ctx.call("write_file", write("b"), call_id="dup")
    count = len(ledger_rows(mod))
    with pytest.raises(mod.cli.CliError, match="1, 2|1 and 2|1,"):
        mod.cli.report("fault", session="s1", call="dup")
    assert len(ledger_rows(mod)) == count


@pytest.mark.parametrize("kw", [dict(verdict="ok", n=1), dict(verdict="success", n=1), dict(verdict="fault"),
                                dict(verdict="fault", session="s1"), dict(verdict="fault", n=1, call="x")])
def test_never_a_success_and_one_way_to_name(plugin, kw):
    mod, ctx = plugin(FAST)
    ctx.call("write_file", write("a"))
    with pytest.raises(ValueError):
        mod.cli.report(kw.pop("verdict"), **kw)


def test_doubt_makes_the_next_action_of_that_kind_ask_once(plugin):
    mod, ctx = plugin(FAST)
    to_t3(ctx)
    mod.ST.rng = Picks([0.99] * 50)                                              # no spot check
    assert ctx.call("write_file", write("alone")) == "ran"
    s, count = state(mod, "file:write").to_dict(), len(ledger_rows(mod))
    out = mod.cli.report("doubt", n=last(mod)["n"])
    assert "file:write" in out
    assert len(ledger_rows(mod)) == count                                        # nothing in the ledger
    after = state(mod, "file:write").to_dict()
    s.pop("changed_at"), after.pop("changed_at")
    assert after == s                                                            # no tier, score or record change
    assert ctx.call("terminal", {"command": "npm test"}) in ("ran", "approved")  # another kind is not held
    assert ctx.call("write_file", write("next")) == "approved"                   # asks first
    assert ctx.call("write_file", write("then")) == "ran"                        # the doubt is settled
    assert not last(mod)["flagged"]


def test_doubt_by_call_and_from_the_command_line(plugin):
    mod, ctx = plugin(FAST)
    to_t3(ctx)
    mod.ST.rng = Picks([0.99] * 50)
    ctx.call("write_file", write("alone"), call_id="tc_z", session="s5")
    text, code = run(mod, "flag --call tc_z --session s5 --doubt")
    assert code == 0 and "file:write" in text
    assert ctx.call("write_file", write("next")) == "approved"


def test_a_refused_doubted_action_is_a_fault_and_settles_the_doubt(plugin):
    mod, ctx = plugin(FAST)
    to_t3(ctx)
    mod.ST.rng = Picks([0.99] * 50)
    ctx.call("write_file", write("alone"))
    mod.cli.report("doubt", n=last(mod)["n"])
    assert ctx.call("write_file", write("next"), answer="deny") == "refused"
    assert not mod.store_().doubted(A, "file:write")


@pytest.mark.parametrize("line", ["flag --call x", "flag --session s", "flag 3 --call x --session s",
                                  "flag --call x --session s --model m", "flag --doubt", "flag file:write --doubt",
                                  "flag --call x --session s note"])
def test_command_line_misuse_is_usage(plugin, line):
    mod, ctx = plugin(FAST)
    ctx.call("write_file", write("a"))
    count = len(ledger_rows(mod))
    assert run(mod, line)[1] == 1 and len(ledger_rows(mod)) == count


def test_unknown_call_from_the_command_line(plugin):
    mod, ctx = plugin(FAST)
    ctx.call("write_file", write("a"))
    text, code = run(mod, "flag --call nope --session s1")
    assert code == 1 and "nope" in text


def test_a_table_from_1_1_gains_the_call_column(tmp_path):
    import sqlite3
    import time
    from tenure import store
    path = str(tmp_path / "tenure.db")
    s = store.Store(path)
    with s.transaction():
        s.db.execute("DROP TABLE recent")
        s.db.execute("CREATE TABLE recent (n INTEGER PRIMARY KEY AUTOINCREMENT, session TEXT, agent TEXT, type TEXT, "
                     "at REAL, flagged INTEGER DEFAULT 0, undo_id INTEGER)")
        s.db.execute("INSERT INTO recent (session, agent, type, at) VALUES ('s', 'a', 't', ?)", (time.time(),))
    s.db.close()
    ro = store.Store.open_readonly(path)
    assert ro.recent(1)["call"] is None and ro.recent_by_call("s", "c") == []
    s = store.Store(path)
    assert s.recent(1)["call"] is None
    with s.transaction():
        n = s.add_recent("s", "a", "t", at=time.time(), flagged=False, undo_id=None, call="c")
    assert [r["n"] for r in s.recent_by_call("s", "c")] == [n]
    assert "call" in [r[1] for r in sqlite3.connect(path).execute("PRAGMA table_info(recent)")]


def test_a_reader_opened_before_the_column_sees_it_later(tmp_path):
    import time
    from tenure import store
    path = str(tmp_path / "tenure.db")
    s = store.Store(path)
    with s.transaction():
        s.db.execute("DROP TABLE recent")
        s.db.execute("CREATE TABLE recent (n INTEGER PRIMARY KEY AUTOINCREMENT, session TEXT, agent TEXT, type TEXT, "
                     "at REAL, flagged INTEGER DEFAULT 0, undo_id INTEGER)")
    s.db.close()
    reader, writer = store.Store(path), store.Store(path)
    assert not reader.has_call
    with writer.transaction():
        writer.add_recent("s", "a", "t", at=time.time(), flagged=False, undo_id=None, call="c")
    assert [r["call"] for r in reader.recent_by_call("s", "c")] == ["c"]
