import pytest

from clearance import personal, store


@pytest.fixture
def st(tmp_path):
    return store.Store(str(tmp_path / "clearance.db"))


def _put(st, agent, key, successes, faults, sessions=("s1",)):
    with st.transaction():
        s = st.get_state(agent, key, "low", True)
        s.successes, s.faults, s.sessions = successes, faults, list(sessions)
        st.put_state(agent, s)


def test_wilson_known_values():
    assert personal.wilson(0, 20) == pytest.approx((0.0, 0.161), abs=1e-3)
    assert personal.wilson(0, 0) == (0.0, 1.0)


def test_table_ranks_models_per_type_with_denominators(st):
    _put(st, "a-model@anthropic", "file:write", 138, 2, ("s1", "s2"))
    _put(st, "b-model@openai", "file:write", 120, 20)
    _put(st, "c-model@openai", "shell:run", 50, 0)
    rows = personal.model_table(st)
    assert [(r["type"], r["model"]) for r in rows] == [
        ("file:write", "a-model"), ("file:write", "b-model"), ("shell:run", "c-model")]
    r = rows[0]
    assert (r["agent"], r["provider"], r["successes"], r["faults"], r["sessions_in_series"]) == \
        ("a-model@anthropic", "anthropic", 138, 2, 2)
    assert r["rate"] == pytest.approx(2 / 140)
    assert r["low"] < r["rate"] < r["high"] and r["enough"] is True
    assert [x["model"] for x in personal.model_table(st, "shell:run")] == ["c-model"]


def test_not_enough_evidence_flag(st):
    _put(st, "m@p", "file:write", 10, 0)
    _put(st, "z@p", "file:write", 0, 0)
    rows = {r["model"]: r for r in personal.model_table(st)}
    assert rows["m"]["enough"] is False
    assert rows["z"]["rate"] is None and rows["z"]["enough"] is False
    assert personal.model_table(st, min_n=10)[0]["enough"] in (True, False)
    assert {r["model"]: r["enough"] for r in personal.model_table(st, min_n=10)}["m"] is True


def test_local_model_names_work(st):
    _put(st, "qwen3:8b-q4_K_M@ollama", "file:write", 30, 1)
    _put(st, "weird@model@unknown", "file:write", 25, 0)
    _put(st, "plain@unknown", "file:write", 25, 0)
    rows = {r["agent"]: r for r in personal.model_table(st)}
    assert (rows["qwen3:8b-q4_K_M@ollama"]["model"], rows["qwen3:8b-q4_K_M@ollama"]["provider"]) == \
        ("qwen3:8b-q4_K_M", "ollama")
    assert rows["weird@model@unknown"]["model"] == "weird@model"
    assert rows["plain@unknown"]["provider"] == "unknown"
