"""Excuse a fault (protocol 0.2): a refusal or an undo that was not the agent's mistake counts as neutral, with
everything it cost, within 10 minutes."""
import re

import pytest

from test_plugin import A, FAST, NPM, Picks, climb, outcomes, plugin, state, to_t3, write  # noqa: F401
from test_see_and_flag import ledger_rows, replay_matches
from test_trust import TRUST


def _seq(text):
    return int(re.search(r"excuse (\d+)", text).group(1))


def test_undo_under_the_trusted_start_then_excuse_gives_the_trust_back(plugin):
    mod, ctx = plugin(TRUST)
    ctx.call("write_file", write("t1"))
    before = state(mod, "file:write").to_dict()
    out = mod.cli.slash(f"undo {int(ctx.posted[-1].rsplit(' ', 1)[1])}")
    assert "/tenure excuse" in out and state(mod, "file:write").distrusted
    seq = _seq(out)
    done = mod.cli.slash(f"excuse {seq}")
    assert "excused" in done and "file:write" in done
    s = state(mod, "file:write")
    assert not s.distrusted and s.faults == 0 and s.tier == before["tier"]
    assert ctx.call("write_file", write("t2")) == "ran"                     # trusted again: no question
    assert replay_matches(mod)
    assert mod.store_().totals(A)["faults"] == 0


def test_a_refusal_then_excuse_restores_the_record(plugin):
    mod, ctx = plugin(FAST)
    climb(ctx, 2)
    before = state(mod, "file:write")
    assert ctx.call("write_file", write("no"), answer="deny") == "refused"
    assert state(mod, "file:write").faults == 1 and state(mod, "file:write").series == 0
    mod.cli.slash(f"excuse {mod.excusable(mod.store_())[0]['n']}")
    s = state(mod, "file:write")
    assert (s.tier, s.faults, s.series, s.wald) == (before.tier, 0, 0, before.wald)   # the series restarts (CSP-1)
    assert (s.neutrals, s.excused) == (before.neutrals + 1, 1)
    assert replay_matches(mod)


def test_another_fault_keeps_the_trust_lost(plugin):
    mod, ctx = plugin(TRUST)
    ctx.call("write_file", write("a"))
    first = mod.cli.slash(f"undo {int(ctx.posted[-1].rsplit(' ', 1)[1])}")
    ctx.call("write_file", write("b", "def x(:\n"))                         # a real fault: the check
    mod.cli.slash(f"excuse {_seq(first)}")
    assert state(mod, "file:write").distrusted and state(mod, "file:write").faults == 1
    assert replay_matches(mod)


def test_excuse_refusals(plugin):
    mod, ctx = plugin(TRUST)
    ctx.call("write_file", write("a"))
    seq = _seq(mod.cli.slash(f"undo {int(ctx.posted[-1].rsplit(' ', 1)[1])}"))
    count = len(ledger_rows(mod))
    row = mod.excusable(mod.store_())[0]["seq"]
    assert row != seq and "nothing changed" in mod.cli.slash(f"excuse {row}")   # its ledger row is not its number
    assert "nothing changed" in mod.cli.slash(f"excuse {seq + 1}")         # no such number
    mod.cli.slash(f"excuse {seq}")
    assert len(ledger_rows(mod)) == count + 1
    assert "nothing changed" in mod.cli.slash(f"excuse {seq}")              # once
    assert len(ledger_rows(mod)) == count + 1


def test_excuse_window_is_ten_minutes(plugin):
    mod, ctx = plugin(TRUST)
    ctx.call("write_file", write("a"))
    seq = _seq(mod.cli.slash(f"undo {int(ctx.posted[-1].rsplit(' ', 1)[1])}"))
    with mod.txn() as st:
        st.db.execute("UPDATE ledger SET at = at - 601 WHERE seq >= ?", (seq,))
    assert "nothing changed" in mod.cli.slash(f"excuse {seq}")
    assert "No fault to excuse" in mod.cli.slash("excuse")


def test_excuse_list(plugin):
    mod, ctx = plugin(TRUST)
    ctx.call("write_file", write("a"))
    seq = _seq(mod.cli.slash(f"undo {int(ctx.posted[-1].rsplit(' ', 1)[1])}"))
    out = mod.cli.slash("excuse")
    assert str(seq) in out and "file:write" in out and "you undid it" in out


def test_replay_refuses_a_bad_excuse():
    from tenure import passport
    rows = [{"seq": 1, "at": 1.0, "event": {"event": "outcome", "result": "success"}},
            {"seq": 2, "at": 2.0, "event": {"event": "excuse", "seq": 1}}]
    with pytest.raises(ValueError, match="not an earlier fault"):
        passport._excused(rows)
    rows = [{"seq": 1, "at": 1.0, "event": {"event": "outcome", "result": "fault", "source": "undo"}},
            {"seq": 2, "at": 2.0, "event": {"event": "excuse", "seq": 1}},
            {"seq": 3, "at": 3.0, "event": {"event": "excuse", "seq": 1}}]
    with pytest.raises(ValueError, match="twice"):
        passport._excused(rows)
    with pytest.raises(ValueError, match="not an earlier fault"):
        passport._excused([{"seq": 1, "at": 1.0, "event": {"event": "excuse", "seq": 2}},
                           {"seq": 2, "at": 2.0, "event": {"event": "outcome", "result": "fault",
                                                             "source": "refusal"}}])


def test_a_passport_after_an_excuse_verifies(plugin, tmp_path):
    mod, ctx = plugin(TRUST)
    ctx.call("write_file", write("a"))
    mod.cli.slash(f"excuse {_seq(mod.cli.slash(f'undo {int(ctx.posted[-1].rsplit(chr(32), 1)[1])}'))}")
    p = mod.passport.build(mod.store_(), A, mod.settings(), mod.data_dir())
    assert p["protocol"] == "earned-autonomy/0.2"
    assert mod.passport.verify(p, mod.store_().ledger()) == []


def test_only_a_refusal_or_an_undo_can_be_excused(plugin):
    mod, ctx = plugin(TRUST)
    ctx.call("write_file", write("b", "def x(:\n"))                         # the automatic check
    assert [r["source"] for r in mod.excusable(mod.store_())] == []
    seq = ledger_rows(mod)[-1]["seq"]
    seq = next(r["seq"] for r in ledger_rows(mod) if r["event"].get("source") == "check")
    assert "nothing changed" in mod.cli.slash(f"excuse {seq}")
    assert state(mod, "file:write").distrusted


def test_a_replay_refuses_an_excused_check():
    from tenure import passport
    rows = [{"seq": 1, "at": 1.0, "event": {"event": "outcome", "result": "fault", "source": "check"}},
            {"seq": 2, "at": 2.0, "event": {"event": "excuse", "seq": 1}}]
    with pytest.raises(ValueError, match="only a refusal or an undo"):
        passport._excused(rows)


def test_no_excuse_while_nobody_answers(plugin, monkeypatch):
    mod, ctx = plugin(TRUST)
    ctx.call("write_file", write("a"))
    seq = _seq(mod.cli.slash(f"undo {int(ctx.posted[-1].rsplit(' ', 1)[1])}"))
    monkeypatch.setenv("HERMES_YOLO_MODE", "1")
    assert "nobody answers" in mod.cli.slash(f"excuse {seq}")
    assert state(mod, "file:write").distrusted


def test_no_excuse_from_a_non_interactive_terminal(plugin, monkeypatch):
    import io
    from test_see_and_flag import run
    mod, ctx = plugin(TRUST)
    ctx.call("write_file", write("a"))
    seq = _seq(mod.cli.slash(f"undo {int(ctx.posted[-1].rsplit(' ', 1)[1])}"))
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    text, code = run(mod, f"excuse {seq}")
    assert code == 1 and "typed by a person" in text and state(mod, "file:write").distrusted
    assert run(mod, "excuse")[1] == 0                                        # the list is fine


def test_the_passport_counts_excused_faults(plugin):
    mod, ctx = plugin(TRUST)
    ctx.call("write_file", write("a"))
    mod.cli.slash(f"excuse {_seq(mod.cli.slash(f'undo {int(ctx.posted[-1].rsplit(chr(32), 1)[1])}'))}")
    p = mod.passport.build(mod.store_(), A, mod.settings(), mod.data_dir())
    assert [e["excused"] for e in p["types"] if e["type"] == "file:write"] == [1]
    assert mod.passport.verify(p, mod.store_().ledger()) == []


def test_a_01_passport_without_the_excused_field_still_verifies(plugin):
    mod, ctx = plugin(FAST)
    climb(ctx, 2)
    p = mod.passport.build(mod.store_(), A, mod.settings(), mod.data_dir(), create_key=False)
    p["protocol"] = "earned-autonomy/0.1"
    for e in p["types"]:
        e.pop("excused", None)
    assert not [x for x in mod.passport.verify(p, mod.store_().ledger()) if "field" in x or "protocol" in x]


def test_no_hint_after_a_refusal_that_cost_nothing(plugin):
    mod, ctx = plugin(FAST)
    assert ctx.call("write_file", write("a"), answer="deny") == "refused"   # T1 already: no tier change
    assert not any("/tenure excuse" in p for p in ctx.posted)


def test_the_agent_cannot_type_the_excuse_itself():
    from tenure import classify
    for cmd in ("hermes tenure excuse 5", "hermes -p work tenure excuse 5", "HERMES_HOME=/x hermes tenure excuse 5"):
        assert classify.classify("terminal", {"command": cmd}, cwd="/tmp").stakes == classify.CAP, cmd


def test_a_passport_is_02_from_the_start(plugin):
    """A rule B/2 ledger is not what a 0.1 verifier replays: 0.2 always, so an old verifier refuses it clearly."""
    mod, ctx = plugin(TRUST)
    ctx.call("write_file", write("a"))
    p = mod.passport.build(mod.store_(), A, mod.settings(), mod.data_dir())
    assert p["protocol"] == "earned-autonomy/0.2" and all("excused" in e for e in p["types"])
    assert mod.passport.verify(p, mod.store_().ledger()) == []
    mod.cli.slash(f"excuse {_seq(mod.cli.slash(f'undo {int(ctx.posted[-1].rsplit(chr(32), 1)[1])}'))}")
    p = mod.passport.build(mod.store_(), A, mod.settings(), mod.data_dir())
    assert p["protocol"] == "earned-autonomy/0.2"
    p["protocol"] = "earned-autonomy/0.1"
    assert any("should be 0.2" in x for x in mod.passport.verify(p, mod.store_().ledger()))


# ------------------------------------------------------------------- one number: the one the person saw (21/11)
def test_after_an_undo_the_hint_names_the_undo_number(plugin):
    """Seen 21/11: "Undone #3 ... /tenure excuse 12", the ledger row leaked. The hint names the number just undone."""
    mod, ctx = plugin(TRUST)
    ctx.call("write_file", write("a"))
    n = int(ctx.posted[-1].rsplit(" ", 1)[1])
    out = mod.cli.slash(f"undo {n}")
    assert f"Undo {n}:" in out and _seq(out) == n
    row = mod.excusable(mod.store_())[0]
    assert (row["n"], row["source"]) == (n, "undo") and row["seq"] != n   # two numberings: only one is shown
    assert f"fault {n} excused" in mod.cli.slash(f"excuse {n}")
    assert ledger_rows(mod)[-1]["event"] == {"event": "excuse", "seq": row["seq"]}   # the ledger keeps the row
    assert replay_matches(mod)


def test_after_a_refusal_the_hint_number_excuses_it_and_no_undo_ever_has_it(plugin):
    from test_plugin import pre
    mod, ctx = plugin(TRUST)
    ctx.call("write_file", write("a"))                                       # undo number 1 is taken
    assert pre(mod, "write_file", write("b"), "x") is None                   # the trusted start lets it through
    mod.post_approval_response(pattern_key="dangerous", tool_call_id="x", choice="deny", session_id="s1")
    n = _seq(next(p for p in ctx.posted if "/tenure excuse" in p))           # Hermes' own prompt, refused
    row = mod.excusable(mod.store_())[0]
    assert (row["n"], row["source"]) == (n, "refusal") and row["seq"] != n
    assert mod.store_().get_undo(n) is None                                  # its own number, from the same counter
    with mod.txn() as st:
        assert st.add_undo(A, "file:write", None) > n                        # and no later undo gets it
    assert f"fault {n} excused" in mod.cli.slash(f"excuse {n}")
    assert ledger_rows(mod)[-1]["event"] == {"event": "excuse", "seq": row["seq"]}
    assert replay_matches(mod)


def test_an_undo_and_a_refusal_open_at_once_never_share_a_number(plugin):
    mod, ctx = plugin(TRUST)
    ctx.call("write_file", write("a"))                                       # trusted: acts, with an undo
    u = int(ctx.posted[-1].rsplit(" ", 1)[1])
    mod.cli.slash(f"undo {u}")
    assert ctx.call("write_file", write("b"), answer="deny") == "refused"
    open_ = {r["source"]: r for r in mod.excusable(mod.store_())}
    r = open_["refusal"]["n"]
    assert open_["undo"]["n"] == u and r != u
    mod.cli.slash(f"excuse {r}")
    assert ledger_rows(mod)[-1]["event"] == {"event": "excuse", "seq": open_["refusal"]["seq"]}
    mod.cli.slash(f"excuse {u}")
    assert ledger_rows(mod)[-1]["event"] == {"event": "excuse", "seq": open_["undo"]["seq"]}
    assert mod.excusable(mod.store_()) == [] and replay_matches(mod)


def test_a_fault_numbered_by_an_older_tenure_is_not_listed(plugin):
    """A fault logged before excuse numbers (no number in meta) is not offered: no number could name it."""
    mod, ctx = plugin(TRUST)
    ctx.call("write_file", write("a"))
    mod.cli.slash(f"undo {int(ctx.posted[-1].rsplit(' ', 1)[1])}")
    with mod.txn() as st:
        st.set_meta(mod.store.EXCUSE_NUMBERS, "")
    assert mod.excusable(mod.store_()) == [] and "No fault to excuse" in mod.cli.slash("excuse")


# ------------------------------------------------------------------------------- review of PR #36 (21/11): numbers
def test_e1_once_said_today_the_hint_reads_no_ledger(plugin, monkeypatch):
    import time
    mod, ctx = plugin(TRUST)
    ctx.call("write_file", write("a"))
    with mod.txn() as st:
        st.set_meta("excuse_hint:file:write", time.strftime("%Y-%m-%d"))
    calls = []
    monkeypatch.setattr(mod, "excusable", lambda *a, **k: calls.append(1) or [])
    out = mod.cli.slash(f"undo {int(ctx.posted[-1].rsplit(' ', 1)[1])}")
    assert "files restored" in out and "/tenure excuse" not in out and calls == []


def test_e2_a_copied_profile_drops_the_excuse_numbers(plugin, tmp_path, monkeypatch):
    from test_copied_profile import clone, reopen
    mod, ctx = plugin(TRUST)
    ctx.call("write_file", write("a"))
    mod.cli.slash(f"undo {int(ctx.posted[-1].rsplit(' ', 1)[1])}")
    assert mod.store_().fault_numbers()
    original = tmp_path / "hermes"
    reopen(mod, monkeypatch, original)
    copy = clone(original)
    reopen(mod, monkeypatch, copy)
    st = mod.store_()
    assert st.get_meta(mod.store.EXCUSE_NUMBERS) is None and mod.excusable(st) == []
    reopen(mod, monkeypatch, original)
    assert mod.store_().fault_numbers()


def test_e3_flag_undo_and_excuse_read_one_numbering(plugin):
    mod, ctx = plugin(TRUST)
    assert ctx.call("terminal", {"command": "python -c 'print(1)'"}) == "approved"   # ran first, no undo
    ctx.call("write_file", write("a"))                                       # acts, with undo number u
    u = int(ctx.posted[-1].rsplit(" ", 1)[1])
    st = mod.store_()
    rows = st.recent_rows(None)
    assert next(r["n"] for r in rows if r["undo_id"] == u) == u               # the number the person saw
    other = next(r["n"] for r in rows if r["undo_id"] is None)
    assert other != u and st.get_undo(other) is None                         # its own number, from the same counter
    with mod.txn() as st:
        assert st.add_undo(A, "file:write", None) > other                    # and no later undo gets it
    assert f"action {u} flagged" in mod.cli.slash(f"flag {u}") and state(mod, "file:write").faults == 1
    assert f"Action {u} already counted" in mod.cli.slash(f"flag {u}")


def test_n1_an_older_numbering_is_passed_over_once_and_keeps_its_numbers(plugin):
    mod, ctx = plugin(TRUST)
    with mod.txn() as st:                                                   # as an older tenure left it
        st._recent_write()
        st.db.execute("DELETE FROM meta WHERE key = ?", (mod.store.NUMBERS_ALIGNED,))
        for _ in range(40):
            st.db.execute("INSERT INTO recent (session, agent, type, at, flagged) VALUES ('s', ?, 'file:write', ?, 0)",
                          (A, __import__("time").time()))
    mod.ST.store = None                                                     # a new process opens it
    ctx.call("write_file", write("a"))                                       # acts, with an undo
    u = int(ctx.posted[-1].rsplit(" ", 1)[1])
    st = mod.store_()
    assert u > 40 and st.recent(u)["undo_id"] == u                          # above every older number
    assert st.recent(7) is not None and st.recent(7)["undo_id"] is None    # an older number still names its action
    assert st.get_meta(mod.store.NUMBERS_ALIGNED) == "1"
