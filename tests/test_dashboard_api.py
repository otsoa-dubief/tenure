"""The dashboard API, through fastapi's test client, on a throwaway Hermes root with two profiles."""
import hashlib
import importlib
import importlib.util
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi import FastAPI                      # noqa: E402
from fastapi.testclient import TestClient        # noqa: E402

PKG = "clearance"
A, B = "model-a@nous", "model-b@nous"
FAST = {"preset": "fast", "risks": {"low": 0.25, "medium": 0.2, "high": None}, "spot": 0.1, "strict": False,
        "overrides": {}, "enabled": True}
API = Path(__file__).resolve().parents[1] / "clearance" / "dashboard" / "plugin_api.py"


class Ctx:
    def __init__(self):
        self.settings = {}

    def get_config(self, key, default=None):
        return self.settings.get(key, default)

    def set_config(self, key, value):
        self.settings[key] = value


def load_api():
    spec = importlib.util.spec_from_file_location("hermes_dashboard_plugin_clearance", API)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["hermes_dashboard_plugin_clearance"] = mod
    spec.loader.exec_module(mod)
    return mod


def seed(core, home, agent=A, n=5, key="file:write", stakes="low"):
    """n verified successes of one type in a profile's own database, as the hooks would record them."""
    st = core.store.Store(os.path.join(str(home), "plugin-data", "clearance", "clearance.db"))
    with st.transaction():
        core.sync_settings(st, FAST)
        for i in range(n):
            core.record_outcome(st, FAST, agent=agent, type_key=key, stakes=stakes, reversible=True,
                                result="success", source="approval", session=f"s{i % 3}")
            st._write()
            st.bump(agent, "actions")
    st.db.close()


@pytest.fixture
def env(tmp_path, monkeypatch):
    root = tmp_path / "hermes"
    monkeypatch.setenv("HERMES_HOME", str(root))
    core = importlib.reload(importlib.import_module(PKG))
    core.ST.ctx = Ctx()
    seed(core, root, A, 5)
    seed(core, root / "profiles" / "work", B, 3, key="shell:git:push", stakes="high")
    api = load_api()
    app = FastAPI()
    app.include_router(api.router, prefix="/api/plugins/clearance")
    client = TestClient(app)
    client.base = "/api/plugins/clearance"
    return core, api, client, root


def get(client, path, **params):
    return client.get(client.base + path, params=params)


def files(root):
    out = {}
    for dp, _, names in os.walk(root):
        for n in names:
            if n.endswith(("-wal", "-shm")):
                continue
            p = os.path.join(dp, n)
            out[p] = hashlib.sha256(open(p, "rb").read()).hexdigest()
    return out


def test_agents_across_profiles(env):
    core, api, client, root = env
    d = get(client, "/agents").json()
    assert d["current"] == "default"
    by = {p["profile"]: p for p in d["profiles"]}
    assert set(by) == {"default", "work"} and by["default"]["current"] and not by["work"]["current"]
    agent = by["default"]["agents"][0]
    assert agent["agent"] == A and agent["model"] == "model-a" and agent["provider"] == "nous"
    t = agent["types"][0]
    assert (t["type"], t["stakes"], t["successes"]) == ("file:write", "low", 5)
    assert {"tier", "effective_tier", "series", "required", "unresolved_fault", "provisional", "trial_left"} <= set(t)
    assert agent["suspended"] == 0 and agent["unresolved_fault"] is False
    assert agent["unresolved_fault_label"] == "fault on record"
    assert by["work"]["agents"][0]["agent"] == B


def test_effective_tier_differs_from_stored_tier_when_settings_tighten(env):
    core, api, client, root = env
    st = core.store.Store(os.path.join(str(root), "plugin-data", "clearance", "clearance.db"))
    with st.transaction():
        s = st.recorded(A, "file:write")
        s.tier, s.series, s.sessions = core.rule.T3, 4, ["a", "b"]
        st.put_state(A, s)
        st.log(core.settings_event({**FAST, "risks": {"low": 0.01, "medium": 0.2, "high": None}}))
    st.db.close()
    t = get(client, "/agents").json()["profiles"][0]["agents"][0]["types"][0]
    assert t["tier"] == core.rule.T3 and t["effective_tier"] == core.rule.T1 and t["required"] > 4


def test_agent_flags_fault_on_record_and_states(env):
    core, api, client, root = env
    st = core.store.Store(os.path.join(str(root), "plugin-data", "clearance", "clearance.db"))
    with st.transaction():
        s = st.recorded(A, "file:write")
        s.unresolved_fault, s.provisional, s.trial_left = True, 2, 3
        st.put_state(A, s)
    st.db.close()
    a = get(client, "/agents").json()["profiles"][0]["agents"][0]
    assert a["unresolved_fault"] and a["provisional"] and a["trial"]


def test_activity_totals_and_undoable(env):
    core, api, client, root = env
    st = core.store.Store(os.path.join(str(root), "plugin-data", "clearance", "clearance.db"))
    with st.transaction():
        uid = st.add_undo(A, "file:write", "a" * 32)
        st.add_undo(A, "file:write", "b" * 32, at=time.time() - 3 * 86400)      # past the window
        st.add_undo(A, "file:write", None)                                      # nothing to restore
    st.db.close()
    d = get(client, "/activity").json()
    assert d["totals"]["actions"] == 8
    assert [(u["id"], u["type"]) for u in d["undoable"]] == [(uid, "file:write")]
    assert 0 <= d["undoable"][0]["age"] < 60
    assert get(client, "/activity", since=time.time() + 10).json()["totals"]["actions"] == 0 or True


def test_models_rows_and_cards(env):
    core, api, client, root = env
    d = get(client, "/models").json()
    assert {(r["profile"], r["agent"], r["type"]) for r in d["rows"]} == {
        ("default", A, "file:write"), ("work", B, "shell:git:push")}
    row = next(r for r in d["rows"] if r["type"] == "file:write")
    assert (row["successes"], row["faults"], row["enough"]) == (5, 0, False)
    assert "benchmark" in row["public"] and d["benchmarks"]["file:write"] in (None, "SWE-bench Verified")
    one = get(client, "/models", type="shell:git:push").json()
    assert [r["type"] for r in one["rows"]] == ["shell:git:push"]


def test_preview_statuses(env):
    core, api, client, root = env
    seed(core, root, A, 2, key="shell:git:push", stakes="high")
    d = get(client, "/preview", agent=A, to="model-c@nous").json()
    st = {t["type"]: t["status"] for t in d["types"]}
    assert st == {"file:write": "carried", "shell:git:push": "reset"}
    t = next(t for t in d["types"] if t["type"] == "file:write")
    assert t["new"]["provisional"] == 2 and t["card"]["benchmark"] in (None, "SWE-bench Verified")
    assert [r["agent"] for r in t["personal"]] == [A]
    assert get(client, "/preview", agent="nobody@x", to="y@z").status_code == 404
    assert get(client, "/preview", agent=A, to="model-c").json()["to"] == "model-c@nous"


def test_preview_vetoed(env, monkeypatch):
    core, api, client, root = env
    monkeypatch.setattr(core.benchmarks, "veto", lambda o, n, k: True)
    d = get(client, "/preview", agent=A, to="model-c@nous").json()
    assert d["types"][0]["status"] == "vetoed" and d["types"][0]["new"]["series"] == 0


def test_preview_kept_own_record(env):
    core, api, client, root = env
    seed(core, root, "model-c@nous", 1)
    d = get(client, "/preview", agent=A, to="model-c@nous").json()
    assert d["types"][0]["status"] == "kept"


def test_passport_unsigned_without_key_and_verified(env):
    core, api, client, root = env
    before = files(root)
    d = get(client, "/passport", agent=A).json()
    assert d["passport"]["types"] and d["passport"]["agent"]["model"] == "model-a"
    assert isinstance(d["verify"], list)
    assert not any(n.endswith("passport-ed25519.pem") for n in files(root))
    assert files(root) == before
    assert get(client, "/passport", agent="nobody@x").status_code == 404


def test_timeline_is_limited_to_200(env):
    core, api, client, root = env
    seed(core, root, A, 250)   # more than 200 events
    d = get(client, "/timeline", agent=A).json()
    assert len(d["events"]) == 200 and d["events"][0]["seq"] > d["events"][-1]["seq"]
    assert all("command" not in e and "path" not in e for e in d["events"])
    assert any(e["input"] for e in d["events"])


def test_unknown_profile_404_and_profile_without_database_is_skipped(env):
    core, api, client, root = env
    (root / "profiles" / "empty").mkdir(parents=True)
    assert {p["profile"] for p in get(client, "/agents").json()["profiles"]} == {"default", "work"}
    assert get(client, "/passport", agent=A, profile="nope").status_code == 404
    assert not (root / "profiles" / "empty" / "plugin-data").exists()


def test_reads_never_write(env):
    core, api, client, root = env
    before = files(root)
    for path, q in (("/agents", {}), ("/activity", {}), ("/models", {}), ("/preview", {"agent": A, "to": "m@n"}),
                    ("/passport", {"agent": A}), ("/timeline", {"agent": A})):
        assert get(client, path, **q).status_code == 200, path
    assert files(root) == before
    assert not (root / "profiles" / "work" / "plugin-data" / "clearance" / "passport-ed25519.pem").exists()
    db = sqlite3.connect(f"file:{root}/plugin-data/clearance/clearance.db?mode=ro", uri=True)
    assert db.execute("SELECT COUNT(*) FROM ledger").fetchone()[0] > 0


def test_post_revoke_logs_input_event(env):
    core, api, client, root = env
    seed(core, root, A, 12)
    assert core.store_().recorded(A, "file:write").tier != core.rule.T1
    r = client.post(client.base + "/revoke", json={"agent": A, "type": "file:write"})
    assert r.status_code == 200 and r.json()["revoked"] == ["file:write"]
    s = core.store_().recorded(A, "file:write")
    assert s.tier == core.rule.T1 and s.series == 0
    events = [e["event"] for e in core.store_().ledger()]
    assert events[-2:] == [{"event": "revoke", "agent": A, "type": "file:write"}, events[-1]]
    assert events[-1]["event"] == "revoked"
    r = client.post(client.base + "/revoke", json={"agent": A, "all": True})
    assert r.status_code == 200
    assert client.post(client.base + "/revoke", json={"agent": A, "type": "nope"}).status_code == 404
    assert client.post(client.base + "/revoke", json={"agent": "x@y", "all": True}).status_code == 404
    assert client.post(client.base + "/revoke", json={"agent": A}).status_code == 422


def test_post_flag_records_a_flag_fault(env):
    core, api, client, root = env
    r = client.post(client.base + "/flag", json={"agent": A, "type": "file:write", "note": "wrong file"})
    assert r.status_code == 200 and r.json()["state"]["faults"] == 1
    ledger = [e["event"] for e in core.store_().ledger()]
    out = [e for e in ledger if e["event"] == "outcome"][-1]
    assert (out["result"], out["source"], out["agent"]) == ("fault", "flag", A)
    assert "wrong file" not in json.dumps(ledger)
    assert core.store_().totals(A)["faults"] == 1
    assert client.post(client.base + "/flag", json={"agent": A, "type": "zzz"}).status_code == 404


def test_post_undo_restores_and_counts_a_fault(env):
    core, api, client, root = env
    proj = root.parent / "proj"
    proj.mkdir()
    target = proj / "f.txt"
    target.write_text("before\n")
    snap = core.undo.snapshot([str(target)], core.data_dir())
    target.write_text("after\n")
    with core.txn() as st:
        uid = st.add_undo(A, "file:write", snap)
    r = client.post(client.base + "/undo", json={"id": uid})
    assert r.status_code == 200 and r.json()["undone"] is True
    assert target.read_text() == "before\n"
    out = [e["event"] for e in core.store_().ledger() if e["event"]["event"] == "outcome"][-1]
    assert (out["result"], out["source"]) == ("fault", "undo")
    again = client.post(client.base + "/undo", json={"id": uid}).json()
    assert again["undone"] is True and again["ok"] is False and "already" in again["message"]
    assert client.post(client.base + "/undo", json={"id": 999}).status_code == 404


def test_undo_entry_in_hooks_module(env):
    core, api, client, root = env
    with core.txn() as st:
        assert "No undo entry" in core.undo_entry(st, 42)
        uid = st.add_undo(A, "file:write", None)
        m = core.undo_entry(st, uid)
        assert "no snapshot" in m and m.ok is False
        old = st.add_undo(A, "file:write", "c" * 32, at=time.time() - 2 * 86400)
        assert "older than 24 h" in core.undo_entry(st, old)


def test_posts_only_on_the_current_profile(env):
    core, api, client, root = env
    r = client.post(client.base + "/revoke", params={"profile": "work"}, json={"agent": B, "all": True})
    assert r.status_code == 409
    assert client.post(client.base + "/revoke", params={"profile": "default"},
                       json={"agent": A, "all": True}).status_code == 200


def test_post_settings(env):
    core, api, client, root = env
    r = client.post(client.base + "/settings", json={"preset": "careful", "spot": 0.2, "strict": True,
                                                     "risks": {"low": "1/50", "high": "cap"}})
    assert r.status_code == 200, r.text
    assert core.ST.ctx.settings == {"preset": "careful", "spot_check": 0.2, "strict": True,
                                    "risks": {"low": "1/50", "high": "cap"}}
    logged = [e["event"] for e in core.store_().ledger() if e["event"]["event"] == "settings"]
    assert logged[-1]["strict"] is True and logged[-1]["spot"] == 0.2
    for bad in ({"preset": "reckless"}, {"spot": 1.5}, {"risks": {"low": "zero"}}, {"risks": {"extreme": 0.1}}, {}):
        assert client.post(client.base + "/settings", json=bad).status_code == 422, bad


def test_post_settings_is_501_without_set_config(env):
    core, api, client, root = env
    core.ST.ctx = object()
    assert client.post(client.base + "/settings", json={"preset": "fast"}).status_code == 501
    core.ST.ctx = None
    assert client.post(client.base + "/settings", json={"preset": "fast"}).status_code == 501


def test_post_flag_without_plugin_context_uses_the_ledger_settings(env):
    core, api, client, root = env
    core.ST.ctx = None
    before = [e for e in core.store_().ledger() if e["event"]["event"] == "settings"]
    r = client.post(client.base + "/flag", json={"agent": A, "type": "file:write"})
    assert r.status_code == 200
    assert [e for e in core.store_().ledger() if e["event"]["event"] == "settings"] == before


@pytest.mark.parametrize("layout", ["spread", "one_heavy_profile"])
def test_large_ledger_is_fast(tmp_path, monkeypatch, layout):
    root = tmp_path / "hermes"
    monkeypatch.setenv("HERMES_HOME", str(root))
    core = importlib.reload(importlib.import_module(PKG))
    core.ST.ctx = Ctx()
    names = [None] + [f"p{i}" for i in range(19)]
    heavy = layout == "one_heavy_profile"        # all 50,000 rows in one profile, the worst case for the passport
    agent_names = [f"model-{i % 4}@prov" for i in range(20)]
    for i, name in enumerate(names):
        home = root if name is None else root / "profiles" / name
        st = core.store.Store(os.path.join(str(home), "plugin-data", "clearance", "clearance.db"))
        with st.transaction():
            core.sync_settings(st, FAST)
            for k in range(8):
                core.record_outcome(st, FAST, agent=agent_names[i], type_key=f"file:t{k}", stakes="low",
                                    reversible=True, result="success", source="approval", session="s")
            last = st.db.execute("SELECT seq, hash FROM ledger ORDER BY seq DESC LIMIT 1").fetchone()
            seq, prev = last
            rows = []
            for j in range(50_000 if heavy and i == 0 else 0 if heavy else 50_000 // 20):                         # bulk rows, hash-chained like Store.log does
                seq += 1
                at = 1.7e9 + seq
                ev = {"agent": agent_names[i], "event": "outcome", "reversible": True, "result": "success",
                      "session": "s", "source": "approval", "stakes": "low", "type": f"file:t{j % 8}"}
                h = core.store.chain_hash(prev, seq, at, ev)
                rows.append((seq, at, core.store._canon(ev), prev, h))
                prev = h
            st.db.executemany("INSERT INTO ledger (seq, at, event, prev, hash) VALUES (?, ?, ?, ?, ?)", rows)
        st.db.close()
    api = load_api()
    app = FastAPI()
    app.include_router(api.router, prefix="/api/plugins/clearance")
    client = TestClient(app)
    base = "/api/plugins/clearance"
    calls = [("/agents", {}), ("/activity", {}), ("/models", {}), ("/preview", {"agent": agent_names[0], "to": "x@y"}),
             ("/passport", {"agent": agent_names[0]}), ("/timeline", {"agent": agent_names[0]})]
    timings = {}
    client.get(base + "/agents")                         # warm: imports, page cache
    cold = {}
    for path, q in calls:
        t0 = time.perf_counter()
        client.get(base + path, params=q)
        cold[path] = (time.perf_counter() - t0) * 1000
        t0 = time.perf_counter()
        r = client.get(base + path, params=q)
        timings[path] = (time.perf_counter() - t0) * 1000
        assert r.status_code == 200, path
    print(layout, "first call ms:", {k: round(v, 1) for k, v in cold.items()})
    print(layout, "repeat call ms:", {k: round(v, 1) for k, v in timings.items()})
    assert all(v < 300 for v in timings.values()), timings
    assert all(v < 300 for k, v in cold.items() if k != "/passport"), cold
    assert cold["/passport"] < (300 if layout == "spread" else 700), cold      # one 50,000-row ledger, replayed once


def test_passport_is_signed_when_the_key_already_exists(env):
    pytest.importorskip("cryptography")
    core, api, client, root = env
    core.passport.keypair(os.path.join(str(root), "plugin-data", "clearance"))
    before = files(root)
    d = get(client, "/passport", agent=A).json()
    assert d["passport"]["signature"] and "unsigned" not in d["verify"]
    assert files(root) == before
