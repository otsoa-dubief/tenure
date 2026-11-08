"""State and evidence on disk: shared by the CLI, the gateway and cron, safely."""
import json
import multiprocessing as mp
import os
import sqlite3
import time

import pytest

from clearance import rule, store

A = "claude-sonnet@anthropic"


@pytest.fixture
def st(tmp_path):
    return store.Store(str(tmp_path / "clearance.db"))


def _pending(st, pid, **kw):
    args = dict(call=f"call-of-{pid}", agent=A, type="file:write", stakes="low", reversible=True, decision="ask",
                phase="asked", rule_key=f"clearance:ask:file:write:{pid}", session="abc123def456")
    args.update(kw)
    st.add_pending(pid, **args)


def test_state_round_trip(st):
    with st.transaction():
        s = st.get_state(A, "file:write", "low", True)
        assert s.tier == rule.T1 and s.series == 0 and s.reversible is True
        s.series, s.sessions, s.wald, s.tier = 3, ["s1", "s2"], -0.5, rule.T2
        st.put_state(A, s)
    with st.transaction():
        got = st.get_state(A, "file:write", "medium", False)
        assert (got.series, got.sessions, got.wald, got.tier) == (3, ["s1", "s2"], -0.5, rule.T2)
        assert got.stakes == "medium" and got.reversible is False     # reclassified since
        assert st.get_state("other@x", "file:write", "low", True).series == 0   # per agent
    assert st.agents() == [A]
    assert [(a, s.key) for a, s in st.states()] == [(A, "file:write")]
    assert st.states("nobody") == []


def test_pending_lifecycle(st):
    with st.transaction():
        _pending(st, "call-1", snap_id="snap-1")
    with st.transaction():
        p = st.get_pending("call-1")
        assert p["type"] == "file:write" and p["reversible"] is True and p["phase"] == "asked"
        assert p["snap_id"] == "snap-1" and p["session"] == "abc123def456" and p["call"] == "call-of-call-1"
        assert p["id"] == "call-1"
        st.set_phase("call-1", "approved")
    with st.transaction():
        assert st.get_pending("call-1")["phase"] == "approved"
        assert st.pop_pending("call-1")["phase"] == "approved"
        assert st.pop_pending("call-1") is None and st.get_pending("call-1") is None
    with st.transaction():
        _pending(st, "call-2")
        assert st.get_pending("call-2")["snap_id"] is None


def test_pending_rows_are_found_by_session_and_call_and_never_replaced(st):
    """Providers reuse tool call ids across sessions (``call_0`` every turn): a row has its own unique id, is found by
    (session, call), and a second row with the same id is refused instead of replacing the first."""
    with st.transaction():
        _pending(st, "u1", call="call_0", session="sess-a", type="shell:npm")
        _pending(st, "u2", call="call_0", session="sess-b", type="file:write")
        with pytest.raises(sqlite3.IntegrityError):
            _pending(st, "u1", call="call_0", session="sess-b", type="message:send")
    assert st.find_pending("sess-a", "call_0")["type"] == "shell:npm"
    assert st.find_pending("sess-b", "call_0")["type"] == "file:write"
    assert st.find_pending("sess-c", "call_0") is None and st.find_pending("sess-a", "call_1") is None
    with st.transaction():
        _pending(st, "u3", call="call_0", session="sess-a", type="shell:make", at=time.time() + 1)
    assert st.find_pending("sess-a", "call_0")["id"] == "u3"          # the newest live row for that call
    with st.transaction():
        assert st.pop_pending("u3")["type"] == "shell:make"
    assert st.find_pending("sess-a", "call_0")["id"] == "u1"


def test_recorded_state_keeps_its_stakes(st):
    with st.transaction():
        s = st.get_state(A, "shell:rsync", "medium", False)
        s.series = 4
        st.put_state(A, s)
    assert st.recorded(A, "shell:rsync").stakes == "medium"
    assert st.get_state(A, "shell:rsync", "high", False).stakes == "high"   # get_state applies today's stakes
    assert st.recorded(A, "shell:rsync").series == 4 and st.recorded(A, "missing") is None


def test_expire_pending_returns_rows(st):
    with st.transaction():
        _pending(st, "old", at=0.0)
        _pending(st, "new")
    with st.transaction():
        rows = st.expire_pending(older_than=3600)
    assert [r["id"] for r in rows] == ["old"] and rows[0]["agent"] == A and rows[0]["call"] == "call-of-old"
    with st.transaction():
        assert st.get_pending("old") is None and st.get_pending("new")
        assert st.expire_pending(older_than=3600) == []


def test_taint_is_per_session(st):
    with st.transaction():
        assert not st.is_tainted("s1")
        st.taint("s1")
        st.taint("s1")
    assert st.is_tainted("s1") and not st.is_tainted("s2")


def test_undo_entries(st):
    with st.transaction():
        i = st.add_undo(A, "file:write", "snap-1")
        j = st.add_undo(A, "file:write", None, fault=True)
    assert i != j
    e = st.get_undo(i)
    assert e["agent"] == A and e["snap_id"] == "snap-1" and e["undone"] is False and e["fault"] is False
    assert st.get_undo(j)["fault"] is True             # its action already counted as a fault
    assert st.get_undo(j)["snap_id"] is None and st.get_undo(999) is None
    with st.transaction():
        st.mark_undone(i)
    assert st.get_undo(i)["undone"] is True and st.get_undo(j)["undone"] is False


def test_totals_by_agent(st):
    with st.transaction():
        for _ in range(3):
            st.bump("a", "actions")
        st.bump("a", "faults")
        st.bump("b", "actions")
        st.bump("b", "alone", n=2)
        st.bump("a", "actions", at=time.time() - 10 * 86400)
    assert st.totals("a") == dict(actions=4, checked=0, alone=0, faults=1)
    assert st.totals("b") == dict(actions=1, checked=0, alone=2, faults=0)
    assert st.totals()["actions"] == 5
    assert st.totals("a", since=time.time() - 86400)["actions"] == 3
    assert st.totals("nobody") == dict(actions=0, checked=0, alone=0, faults=0)
    with st.transaction():
        with pytest.raises(ValueError):
            st.bump("a", "bogus")


def test_ledger_chain_and_verify(st, tmp_path):
    with st.transaction():
        st.log({"event": "outcome", "agent": A, "type": "file:write", "result": "success"})
        st.log({"event": "revoke", "agent": A, "type": "file:write"})
    rows = st.ledger()
    assert [r["event"]["event"] for r in rows] == ["outcome", "revoke"]
    assert rows[1]["prev"] == rows[0]["hash"] and store.verify(rows) == []
    out = tmp_path / "evidence.jsonl"
    st.export(str(out))
    lines = [json.loads(l) for l in out.read_text().splitlines()]
    assert store.verify(lines) == []
    lines[0]["event"]["type"] = "file:delete"                                  # tampering is detected
    assert store.verify(lines)


def _worker(path, n):
    st = store.Store(path)
    for _ in range(n):
        with st.transaction():
            st.bump("m", "actions")
            st.log({"event": "outcome", "agent": "m"})


def test_two_processes_do_not_lose_updates(tmp_path):
    path = str(tmp_path / "clearance.db")
    store.Store(path)
    ctx = mp.get_context("spawn")
    procs = [ctx.Process(target=_worker, args=(path, 100)) for _ in range(2)]
    for p in procs:
        p.start()
    for p in procs:
        p.join(60)
    st = store.Store(path)
    assert st.totals("m")["actions"] == 200
    assert len(st.ledger()) == 200 and store.verify(st.ledger()) == []


def test_two_stores_interleaved(tmp_path):
    path = str(tmp_path / "clearance.db")
    s1, s2 = store.Store(path), store.Store(path)
    for i in range(200):
        with (s1 if i % 2 else s2).transaction() as t:
            t.bump("m", "actions")
    assert s1.totals("m")["actions"] == 200


def test_meta_and_schema(st):
    assert st.get_meta("schema") == "3"
    assert st.db.execute("PRAGMA busy_timeout").fetchone()[0] == 5000      # well under a hook's time limit
    with st.transaction():
        st.set_meta("k", "v")
    assert st.get_meta("k") == "v" and st.get_meta("missing", "x") == "x"


def test_v1_database_is_recreated(tmp_path):
    path = tmp_path / "clearance.db"
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE types (model TEXT, key TEXT, state TEXT)")
    db.execute("INSERT INTO types VALUES ('m', 'k', '{}')")
    db.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
    db.commit()
    db.close()
    s = store.Store(str(path))
    assert s.get_meta("schema") == "3" and s.agents() == []


def test_schema_2_database_is_recreated(tmp_path):
    """Schema 2 keyed pending rows by the provider's tool call id; it is recreated (no release used it)."""
    path = str(tmp_path / "clearance.db")
    w = store.Store(path)
    with w.transaction():
        w.set_meta("schema", "2")
        w.bump(A, "actions")
    w.db.close()
    s = store.Store(path)
    assert s.get_meta("schema") == "3" and s.totals(A)["actions"] == 0


def test_database_is_private(tmp_path):
    path = tmp_path / "sub" / "clearance.db"
    store.Store(str(path))
    if os.name == "posix":
        assert oct(os.stat(path).st_mode & 0o777) == "0o600"


def test_open_readonly(tmp_path):
    path = str(tmp_path / "clearance.db")
    with pytest.raises(FileNotFoundError):
        store.Store.open_readonly(path)
    assert not os.path.exists(path)
    w = store.Store(path)
    with w.transaction():
        s = w.get_state(A, "file:write", "low", True)
        w.put_state(A, s)
        _pending(w, "c1")
        w.taint("s1")
        i = w.add_undo(A, "file:write", None)
        w.bump(A, "actions")
        w.log({"event": "revoke", "agent": A, "type": "file:write"})
    r = store.Store.open_readonly(path)
    assert r.agents() == [A] and len(r.states()) == 1
    assert r.get_pending("c1")["agent"] == A and r.is_tainted("s1") and r.get_undo(i)
    assert r.totals(A)["actions"] == 1 and store.verify(r.ledger()) == []
    assert r.get_meta("schema") == "3"
    with pytest.raises(sqlite3.OperationalError):
        r.db.execute("DELETE FROM pending")


def test_writes_outside_a_transaction_raise(st):
    with st.transaction():
        _pending(st, "c1")
        s = st.get_state(A, "t", "low")
    calls = [lambda: st.pop_pending("c1"), lambda: st.expire_pending(0), lambda: st.put_state(A, s),
             lambda: _pending(st, "c2"), lambda: st.set_phase("c1", "x"), lambda: st.taint("s"),
             lambda: st.add_undo(A, "t", None), lambda: st.mark_undone(1), lambda: st.bump(A, "actions"),
             lambda: st.set_meta("k", "v"), lambda: st.log({"event": "revoke"})]
    for c in calls:
        with pytest.raises(RuntimeError, match="outside a transaction"):
            c()
    assert st.get_pending("c1") is not None


def _popper(path, tcid, q):
    st = store.Store(path)
    with st.transaction():
        got = st.pop_pending(tcid)
    q.put(got is not None)


def test_two_processes_pop_the_same_pending_once(tmp_path):
    path = str(tmp_path / "clearance.db")
    s = store.Store(path)
    ctx = mp.get_context("spawn")
    for n in range(10):
        with s.transaction():
            _pending(s, f"c{n}")
    results = []
    for n in range(10):
        q = ctx.Queue()
        procs = [ctx.Process(target=_popper, args=(path, f"c{n}", q)) for _ in range(2)]
        for p in procs:
            p.start()
        for p in procs:
            p.join(60)
        assert [p.exitcode for p in procs] == [0, 0]
        results.append(sorted([q.get(timeout=5), q.get(timeout=5)]))
    assert results == [[False, True]] * 10


def test_reopen_keeps_data(tmp_path):
    path = str(tmp_path / "clearance.db")
    w = store.Store(path)
    with w.transaction():
        st_ = w.get_state(A, "file:write", "low", True)
        st_.series = 7
        w.put_state(A, st_)
        w.bump(A, "actions")
        w.log({"event": "revoke", "agent": A, "type": "file:write"})
    w.db.close()
    r = store.Store(path)
    assert r.get_state(A, "file:write", "low", True).series == 7
    assert r.totals(A)["actions"] == 1 and len(r.ledger()) == 1


def _opener(path, start):
    start.wait(30)
    store.Store(path)


def test_concurrent_first_open(tmp_path):
    path = str(tmp_path / "clearance.db")
    ctx = mp.get_context("spawn")
    start = ctx.Event()
    procs = [ctx.Process(target=_opener, args=(path, start)) for _ in range(5)]
    for p in procs:
        p.start()
    start.set()
    for p in procs:
        p.join(60)
    assert [p.exitcode for p in procs] == [0] * 5
    s = store.Store(path)
    assert s.get_meta("schema") == "3"
    n = s.db.execute("SELECT COUNT(*) FROM meta WHERE key = 'schema'").fetchone()[0]
    assert n == 1


def test_downgrade_raises_and_keeps_data(tmp_path):
    path = str(tmp_path / "clearance.db")
    w = store.Store(path)
    with w.transaction():
        w.bump("a", "actions")
        w.set_meta("schema", "4")
    w.db.close()
    with pytest.raises(RuntimeError, match="newer"):
        store.Store(path)
    db = sqlite3.connect(path)
    assert db.execute("SELECT COUNT(*) FROM stats").fetchone()[0] == 1


def test_open_readonly_rejects_wrong_schema(tmp_path):
    empty = tmp_path / "empty.db"
    sqlite3.connect(empty).close()
    with pytest.raises(RuntimeError, match="schema"):
        store.Store.open_readonly(str(empty))
    v1 = tmp_path / "v1.db"
    db = sqlite3.connect(v1)
    db.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
    db.commit()
    db.close()
    with pytest.raises(RuntimeError, match="schema"):
        store.Store.open_readonly(str(v1))


def test_log_validates_event_kind(st):
    assert {"settings", "outcome", "agent", "revoke"} == set(store.INPUT_KINDS)
    with st.transaction():
        for k in sorted(store.INPUT_KINDS | store.DERIVED_KINDS):
            st.log({"event": k})
        with pytest.raises(ValueError):
            st.log({"event": "bogus"})
        with pytest.raises(ValueError):
            st.log({})
    assert len(st.ledger()) == len(store.INPUT_KINDS | store.DERIVED_KINDS)
