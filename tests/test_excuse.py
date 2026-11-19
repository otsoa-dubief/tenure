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


def test_a_refusal_then_excuse_restores_the_earned_tier(plugin):
    mod, ctx = plugin(FAST)
    to_t3(ctx)
    t3 = state(mod, "file:write")
    mod.ST.rng = Picks([0.0])                                                # a spot check
    assert ctx.call("write_file", write("spot"), answer="deny") == "refused"
    assert state(mod, "file:write").tier != mod.rule.T3
    assert any("/tenure excuse" in p for p in ctx.posted)
    seq = _seq([p for p in ctx.posted if "/tenure excuse" in p][-1])
    mod.cli.slash(f"excuse {seq}")
    s = state(mod, "file:write")
    assert (s.tier, s.faults, s.series) == (t3.tier, 0, t3.series)
    assert s.neutrals == t3.neutrals + 1
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
    rows = [{"seq": 1, "at": 1.0, "event": {"event": "outcome", "result": "fault"}},
            {"seq": 2, "at": 2.0, "event": {"event": "excuse", "seq": 1}},
            {"seq": 3, "at": 3.0, "event": {"event": "excuse", "seq": 1}}]
    with pytest.raises(ValueError, match="twice"):
        passport._excused(rows)
    with pytest.raises(ValueError, match="not an earlier fault"):
        passport._excused([{"seq": 1, "at": 1.0, "event": {"event": "excuse", "seq": 2}},
                           {"seq": 2, "at": 2.0, "event": {"event": "outcome", "result": "fault"}}])


def test_a_passport_after_an_excuse_verifies(plugin, tmp_path):
    mod, ctx = plugin(TRUST)
    ctx.call("write_file", write("a"))
    mod.cli.slash(f"excuse {_seq(mod.cli.slash(f'undo {int(ctx.posted[-1].rsplit(chr(32), 1)[1])}'))}")
    p = mod.passport.build(mod.store_(), A, mod.settings(), mod.data_dir())
    assert p["protocol"] == "earned-autonomy/0.2"
    assert mod.passport.verify(p, mod.store_().ledger()) == []
