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
    seq = mod.excusable(mod.store_())[0]["seq"]
    mod.cli.slash(f"excuse {seq}")
    s = state(mod, "file:write")
    assert (s.tier, s.faults, s.series, s.wald) == (before.tier, 0, before.series, before.wald)
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
    assert "nothing changed" in mod.cli.slash("excuse 1")                   # row 1 is settings, not a fault
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


def test_a_passport_stays_01_until_an_excuse(plugin):
    mod, ctx = plugin(TRUST)
    ctx.call("write_file", write("a"))
    p = mod.passport.build(mod.store_(), A, mod.settings(), mod.data_dir())
    assert p["protocol"] == "earned-autonomy/0.1" and all("excused" not in e for e in p["types"])
    mod.cli.slash(f"excuse {_seq(mod.cli.slash(f'undo {int(ctx.posted[-1].rsplit(chr(32), 1)[1])}'))}")
    p = mod.passport.build(mod.store_(), A, mod.settings(), mod.data_dir())
    assert p["protocol"] == "earned-autonomy/0.2"
    p["protocol"] = "earned-autonomy/0.1"
    assert any("should be 0.2" in x for x in mod.passport.verify(p, mod.store_().ledger()))
