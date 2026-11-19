"""State and evidence on disk: shared by the CLI, the gateway and cron, safely."""
import json
import multiprocessing as mp
import os
import sqlite3
import time

import pytest

from tenure import rule, store

A = "claude-sonnet@anthropic"


@pytest.fixture
def st(tmp_path):
    return store.Store(str(tmp_path / "tenure.db"))


def _pending(st, pid, **kw):
    args = dict(call=f"call-of-{pid}", agent=A, type="file:write", stakes="low", reversible=True, decision="ask",
                phase="asked", rule_key=f"tenure:ask:file:write:{pid}", session="abc123def456")
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
    path = str(tmp_path / "tenure.db")
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
    path = str(tmp_path / "tenure.db")
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
    path = tmp_path / "tenure.db"
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE types (model TEXT, key TEXT, state TEXT)")
    db.execute("INSERT INTO types VALUES ('m', 'k', '{}')")
    db.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
    db.commit()
    db.close()
    s = store.Store(str(path))
    assert s.get_meta("schema") == "3" and s.agents() == []
    bak = sqlite3.connect(str(path) + ".bak-unknown")
    assert bak.execute("SELECT model FROM types").fetchall() == [("m",)]


def test_schema_2_database_is_recreated(tmp_path):
    """Schema 2 keyed pending rows by the provider's tool call id; it is recreated (no release used it)."""
    path = str(tmp_path / "tenure.db")
    w = store.Store(path)
    with w.transaction():
        w.set_meta("schema", "2")
        w.bump(A, "actions")
    w.db.close()
    s = store.Store(path)
    assert s.get_meta("schema") == "3" and s.totals(A)["actions"] == 0
    old = sqlite3.connect(path + ".bak-2")                              # the dropped file is kept as a copy
    assert old.execute("SELECT SUM(actions) FROM stats").fetchone()[0] == 1


def test_database_is_private(tmp_path):
    path = tmp_path / "sub" / "tenure.db"
    store.Store(str(path))
    if os.name == "posix":
        assert oct(os.stat(path).st_mode & 0o777) == "0o600"


def test_open_readonly(tmp_path):
    path = str(tmp_path / "tenure.db")
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
    path = str(tmp_path / "tenure.db")
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
    path = str(tmp_path / "tenure.db")
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
    path = str(tmp_path / "tenure.db")
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
    path = str(tmp_path / "tenure.db")
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
    assert {"settings", "outcome", "agent", "revoke", "copy", "excuse"} == set(store.INPUT_KINDS)
    with st.transaction():
        for k in sorted(store.INPUT_KINDS | store.DERIVED_KINDS):
            st.log({"event": k})
        with pytest.raises(ValueError):
            st.log({"event": "bogus"})
        with pytest.raises(ValueError):
            st.log({})
    assert len(st.ledger()) == len(store.INPUT_KINDS | store.DERIVED_KINDS)


# ------------------------------------------------------------------------------------------------- recent
def _tables(path):
    db = sqlite3.connect(path)
    try:
        return {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    finally:
        db.close()


def _drop_recent(path):
    """A schema 3 database written by the code before the table ``recent``, with ledger rows."""
    w = store.Store(path)
    with w.transaction():
        w.log({"event": "revoke", "agent": A, "type": "file:write"})
        w.log({"event": "settings", "risks": {"low": 0.2}, "spot": 0.1, "strict": False, "rule": "x"})
        w.bump(A, "actions")
        w.db.execute("DROP TABLE IF EXISTS recent")
    rows = w.ledger()
    w.db.close()
    assert "recent" not in _tables(path)
    return rows


def test_recent_is_one_of_the_tables():
    assert "recent" in store.TABLES and store.SCHEMA_VERSION == "3"


def test_recent_added_without_touching_ledger(tmp_path):
    path = str(tmp_path / "tenure.db")
    before = _drop_recent(path)
    s = store.Store(path)
    assert "recent" in _tables(path)
    assert s.get_meta("schema") == "3" and s.totals(A)["actions"] == 1
    after = s.ledger()
    assert store.verify(after) == [] and [r["hash"] for r in after] == [r["hash"] for r in before]
    assert not [f for f in os.listdir(tmp_path) if ".bak-" in f]                 # nothing dropped, nothing copied
    cols = [r[1] for r in s.db.execute("PRAGMA table_info(recent)")]
    assert cols == ["n", "session", "agent", "type", "at", "flagged", "undo_id", "call"]
    indexed = {r[0] for r in s.db.execute("SELECT sql FROM sqlite_master WHERE type = 'index' AND tbl_name = 'recent'")}
    assert any("(session)" in q for q in indexed) and any("(at)" in q for q in indexed)


def test_open_current_db_takes_no_write_lock(tmp_path, monkeypatch):
    """Guard: opening a database that already has every table only reads, so another writer never delays it."""
    path = str(tmp_path / "tenure.db")
    store.Store(path).db.close()
    monkeypatch.setattr(store, "BUSY_TIMEOUT", 0.2)
    other = sqlite3.connect(path, isolation_level=None)
    other.execute("BEGIN IMMEDIATE")
    try:
        t0 = time.monotonic()
        s = store.Store(path)
        assert time.monotonic() - t0 < 0.15 and s.get_meta("schema") == "3"
    finally:
        other.execute("ROLLBACK")
        other.close()


def _open_locked(path, monkeypatch):
    """A Store opened while another connection holds the write lock: it cannot add ``recent``."""
    monkeypatch.setattr(store, "BUSY_TIMEOUT", 0.2)
    other = sqlite3.connect(path, isolation_level=None)
    other.execute("BEGIN IMMEDIATE")
    try:
        return store.Store(path)
    finally:
        other.execute("ROLLBACK")
        other.close()


def test_a_locked_database_without_recent_still_opens(tmp_path, monkeypatch, caplog):
    """The table cannot be added while another process writes: the store opens without it (said in the log), reads
    are empty, and its first write adds it inside that write's transaction."""
    path = str(tmp_path / "tenure.db")
    _drop_recent(path)
    with caplog.at_level("WARNING", logger="tenure"):
        s = _open_locked(path, monkeypatch)
    assert "numbered actions" in caplog.text
    assert "recent" not in _tables(path) and store.verify(s.ledger()) == [] and s.has_recent is False
    assert s.recent(1) is None and s.recent_rows(None) == [] and s.count_recent("s") == 0
    with s.transaction():
        assert s.add_recent("s", A, "file:write", at=time.time(), flagged=False, undo_id=None) == 1
    assert "recent" in _tables(path) and s.recent(1)["n"] == 1


def test_a_table_added_by_a_rolled_back_write_is_not_believed(tmp_path, monkeypatch):
    path = str(tmp_path / "tenure.db")
    _drop_recent(path)
    s = _open_locked(path, monkeypatch)
    with pytest.raises(RuntimeError):
        with s.transaction():
            s.clear_recent()
            assert s.has_recent is True
            raise RuntimeError("boom")
    assert "recent" not in _tables(path) and s.has_recent is False
    assert s.recent_rows(None) == [] and s.recent(1) is None
    with s.transaction():
        s.mark_flagged(1)                                      # every write adds it
    assert "recent" in _tables(path)


def test_a_store_opened_without_recent_sees_and_flags_another_process_rows(tmp_path, monkeypatch):
    """Gateway A opened under a lock; CLI B then adds the table and numbers an action linked to undo ``u``. A's undo
    flags B's row (one action, at most one fault), A lists it, and A numbers its own actions."""
    path = str(tmp_path / "tenure.db")
    _drop_recent(path)
    a = _open_locked(path, monkeypatch)
    assert a.has_recent is False
    b = store.Store(path)
    with b.transaction():
        u = b.add_undo(A, "file:write", "snap")
        n = b.add_recent("s", A, "file:write", at=time.time(), flagged=False, undo_id=u)
    assert [r["n"] for r in a.recent_rows(None)] == [n] and a.count_recent("x") == 1
    with a.transaction():
        a.flag_by_undo(u)
    assert b.recent(n)["flagged"] is True
    with a.transaction():
        m = a.add_recent("s", A, "shell:npm", at=time.time(), flagged=False, undo_id=None)
    assert m == n + 1 and b.recent(m)["type"] == "shell:npm"
    with a.transaction():
        a.clear_recent()
    assert b.recent_rows(None) == []


def test_open_readonly_without_recent(tmp_path):
    """Guard: the dashboard opens a database the plugin has not reopened since the table was added."""
    path = str(tmp_path / "tenure.db")
    _drop_recent(path)
    r = store.Store.open_readonly(path)
    assert r.get_meta("schema") == "3" and store.verify(r.ledger()) == []
    assert "recent" not in _tables(path)


def test_recent_methods_read_nothing_from_a_readonly_store_without_the_table(tmp_path):
    path = str(tmp_path / "tenure.db")
    _drop_recent(path)
    r = store.Store.open_readonly(path)
    assert r.recent(1) is None and r.recent_rows(None) == [] and r.recent_rows("s") == [] and r.count_recent("") == 0


def test_open_readonly_reads_recent(tmp_path):
    path = str(tmp_path / "tenure.db")
    w = store.Store(path)
    with w.transaction():
        n = w.add_recent("s", A, "file:write", at=time.time(), flagged=True, undo_id=4)
    r = store.Store.open_readonly(path)
    assert r.recent(n) == {"n": n, "session": "s", "agent": A, "type": "file:write", "at": r.recent(n)["at"],
                           "flagged": True, "undo_id": 4, "call": None}


def test_a_recreated_old_schema_has_recent(tmp_path):
    path = str(tmp_path / "tenure.db")
    w = store.Store(path)
    with w.transaction():
        w.set_meta("schema", "2")
    w.db.close()
    s = store.Store(path)
    assert s.get_meta("schema") == "3" and "recent" in _tables(path)


def test_numbers_never_reused_after_purge(st):
    now = time.time()
    with st.transaction():
        a = st.add_recent("s", A, "file:write", at=now - 25 * 3600, flagged=False, undo_id=None)
        b = st.add_recent("s", A, "file:write", at=now - 24.5 * 3600, flagged=False, undo_id=None)
    assert (a, b) == (1, 2)
    with st.transaction():
        c = st.add_recent("s", A, "shell:npm", at=now, flagged=False, undo_id=None)    # purges both, same write
    assert c == 3 and st.db.execute("SELECT n FROM recent").fetchall() == [(3,)]
    with st.transaction():
        st.db.execute("DELETE FROM recent")                                           # even after a full purge
        assert st.add_recent("s", A, "shell:npm", at=now, flagged=False, undo_id=None) == 4


def test_recent_rows_are_filtered_to_24_hours_without_a_write(st, monkeypatch):
    now = time.time()
    with st.transaction():
        old = st.add_recent("s1", A, "file:write", at=now - 3600, flagged=False, undo_id=None)
        for i in range(25):
            st.add_recent("s1" if i % 2 else "s2", A, f"t{i}", at=now + i, flagged=False, undo_id=None)
    rows = st.recent_rows("s1")
    assert len(rows) == 13 and [r["type"] for r in rows[:2]] == ["t23", "t21"]            # newest first
    assert rows[-1]["n"] == old and all(r["session"] == "s1" for r in rows)
    assert len(st.recent_rows(None)) == 20 and len(st.recent_rows(None, limit=50)) == 26
    assert st.count_recent(exclude_session="s1") == 13 and st.count_recent(exclude_session="x") == 26
    monkeypatch.setattr(store.time, "time", lambda: now + 23.5 * 3600)              # the old row is now 24.5 h old
    assert st.recent(old) is None and old not in [r["n"] for r in st.recent_rows("s1", limit=50)]
    assert st.count_recent(exclude_session="s2") == 12
    assert st.db.execute("SELECT COUNT(*) FROM recent").fetchone()[0] == 26                # nothing was deleted
    assert st.recent(9999) is None


def test_flags_on_recent_and_undo(st):
    with st.transaction():
        u = st.add_undo(A, "file:write", "snap")
        n = st.add_recent("s", A, "file:write", at=time.time(), flagged=False, undo_id=u)
        m = st.add_recent("s", A, "file:write", at=time.time(), flagged=False, undo_id=None)
    assert st.recent(n)["flagged"] is False and st.recent(n)["undo_id"] == u
    with st.transaction():
        st.flag_by_undo(u)                                     # an undo marks its action flagged
        st.mark_flagged(m)
    assert st.recent(n)["flagged"] is True and st.recent(m)["flagged"] is True
    assert st.get_undo(u)["fault"] is False
    with st.transaction():
        st.mark_undo_fault(u)                                  # a flag marks its snapshot: the undo counts no fault
    assert st.get_undo(u)["fault"] is True


def test_recent_writes_outside_a_transaction_raise(st):
    calls = [lambda: st.add_recent("s", A, "t", at=time.time(), flagged=False, undo_id=None),
             lambda: st.mark_flagged(1), lambda: st.flag_by_undo(1), lambda: st.mark_undo_fault(1),
             lambda: st.clear_recent()]
    for call in calls:
        with pytest.raises(RuntimeError, match="outside a transaction"):
            call()
