"""State and evidence on disk: shared by the CLI, the gateway and cron, safely."""
import json
import multiprocessing as mp
import os

import pytest

from clearance import rule, store


@pytest.fixture
def st(tmp_path):
    return store.Store(str(tmp_path / "clearance.db"))


def test_new_type_and_round_trip(st):
    with st.transaction():
        s = st.get_state("model-a", "file:write", "low")
        assert s.level == rule.ASK and s.streak == 0
        s.streak = 3
        st.put_state("model-a", s)
    with st.transaction():
        assert st.get_state("model-a", "file:write", "low").streak == 3
        assert st.get_state("model-b", "file:write", "low").streak == 0        # records are per model


def test_pending_asks(st):
    with st.transaction():
        st.add_pending("call-1", "model-a", "file:write", 0, spot=False, rule_key="clearance:file:write:g0")
    with st.transaction():
        assert st.pop_pending(tool_call_id="call-1")["type"] == "file:write"
        assert st.pop_pending(tool_call_id="call-1") is None
    with st.transaction():
        st.add_pending("call-2", "model-a", "shell:npm", 1, spot=True, rule_key="clearance:spot:shell:npm:call-2")
    with st.transaction():
        p = st.pop_pending(rule_key="clearance:spot:shell:npm:call-2")
        assert p["spot"] and p["generation"] == 1


def test_old_pending_asks_expire(st):
    with st.transaction():
        st.add_pending("old", "m", "t", 0, spot=False, rule_key="k", at=0.0)
        st.add_pending("new", "m", "t", 0, spot=False, rule_key="k2")
        st.expire_pending(older_than=3600)
    with st.transaction():
        assert st.pop_pending(tool_call_id="old") is None and st.pop_pending(tool_call_id="new")


def test_ledger_is_a_hash_chain(st, tmp_path):
    with st.transaction():
        st.log({"event": "approved", "type": "file:write"})
        st.log({"event": "cleared", "type": "file:write"})
    rows = st.ledger()
    assert [r["event"]["event"] for r in rows] == ["approved", "cleared"]
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
            s = st.get_state("m", "shell:npm", "medium")
            s.approvals += 1
            st.put_state("m", s)
            st.log({"event": "approved", "type": "shell:npm"})


def test_concurrent_processes_do_not_lose_updates(tmp_path):
    path = str(tmp_path / "clearance.db")
    store.Store(path)
    ctx = mp.get_context("spawn")
    procs = [ctx.Process(target=_worker, args=(path, 50)) for _ in range(4)]
    for p in procs:
        p.start()
    for p in procs:
        p.join(60)
    st = store.Store(path)
    with st.transaction():
        assert st.get_state("m", "shell:npm", "medium").approvals == 200
    assert len(st.ledger()) == 200 and store.verify(st.ledger()) == []


def test_meta(st):
    with st.transaction():
        st.set_meta("model:session-1", "model-a")
    with st.transaction():
        assert st.get_meta("model:session-1") == "model-a" and st.get_meta("missing", "x") == "x"


def test_database_is_private(tmp_path):
    path = tmp_path / "sub" / "clearance.db"
    store.Store(str(path))
    if os.name == "posix":
        assert oct(os.stat(path).st_mode & 0o777) == "0o600"
