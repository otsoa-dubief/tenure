import json

import pytest

from clearance import benchmarks as b

FIXTURE = {
    "source": "Epoch AI Benchmarking Hub", "license": "CC BY 4.0", "url": "https://epoch.ai/benchmarks",
    "accessed": "2026-11-08",
    "benchmarks": {"Terminal-Bench": {"version": "2.0", "unit": "percent"},
                   "SWE-bench Verified": {"version": "Verified", "unit": "percent"},
                   "OSWorld": {"version": "1", "unit": "percent"}},
    "models": {
        "claude-opus-4-5-20251101": {"aliases": ["claude-opus-4-5-20251101_unknown"],
                                     "scores": {"Terminal-Bench": 60.0, "SWE-bench Verified": 80.0}},
        "gpt-5.1-2025-11-13_medium": {"aliases": [], "scores": {"Terminal-Bench": 50.0, "SWE-bench Verified": 74.0,
                                                                "OSWorld": 40.0}},
        "five": {"aliases": [], "scores": {"SWE-bench Verified": 75.0}},
        "tiny": {"aliases": [], "scores": {"OSWorld": 10.0}},
    },
}


@pytest.fixture(autouse=True)
def snapshot(tmp_path, monkeypatch):
    p = tmp_path / "benchmarks.json"
    p.write_text(json.dumps(FIXTURE))
    monkeypatch.setattr(b, "DATA_PATH", p)
    b._cache.clear()
    yield p
    b._cache.clear()


def test_type_mapping():
    assert b.benchmark_for("shell:ls") == "Terminal-Bench"
    assert b.benchmark_for("shell:rsync") == "Terminal-Bench"
    assert b.benchmark_for("file:write") == "SWE-bench Verified"
    assert b.benchmark_for("code:execute") == "SWE-bench Verified"
    assert b.benchmark_for("computer:use") == "OSWorld"
    assert b.benchmark_for("message:send") is None
    assert b.benchmark_for("shell:git:push") is None


def test_type_mapping_absent_benchmark_is_none(snapshot):
    d = dict(FIXTURE, benchmarks={"SWE-bench Verified": FIXTURE["benchmarks"]["SWE-bench Verified"]})
    snapshot.write_text(json.dumps(d))
    b._cache.clear()
    assert b.benchmark_for("shell:ls") is None


@pytest.mark.parametrize("mid", ["claude-opus-4-5", "Claude-Opus-4.5", "anthropic/claude-opus-4-5-20251101",
                                 "openrouter/anthropic/claude-opus-4-5@openrouter", "claude-opus-4-5-20251101_unknown",
                                 "claude-opus-4-5-2025-11-01"])
def test_lookup_normalises_ids(mid):
    assert b.lookup(mid)["scores"]["SWE-bench Verified"] == 80.0


def test_lookup_other_model_and_unknown():
    assert b.lookup("openai/GPT-5.1@openai")["scores"]["OSWorld"] == 40.0
    assert b.lookup("qwen3:8b-q4_K_M@ollama") is None
    assert b.lookup("") is None and b.lookup("@") is None


def test_card_unknown_model_says_no_public_measure():
    c = b.card("claude-opus-4-5", "qwen3:8b-q4_K_M@ollama", "file:write")
    assert c["new"] is None and c["delta"] is None
    assert "no public measure" in c["note"].lower()
    assert set(c) == {"benchmark", "version", "source", "accessed", "old", "new", "delta", "note"}
    assert not b.veto("claude-opus-4-5", "qwen3:8b-q4_K_M@ollama", "file:write")
    assert not b.veto("qwen3:8b", "claude-opus-4-5", "file:write")
    c = b.card(None, "claude-opus-4-5", "file:write")
    assert c["old"] is None and c["new"] == 80.0
    assert b.card("a", "b", "message:send")["benchmark"] is None


def test_card_values():
    c = b.card("claude-opus-4-5", "gpt-5.1", "file:write")
    assert (c["benchmark"], c["version"], c["old"], c["new"], c["delta"]) == ("SWE-bench Verified", "Verified", 80.0, 74.0, -6.0)
    assert c["accessed"] == "2026-11-08" and "Epoch" in c["source"]


def test_veto_only_on_same_benchmark_and_version_beyond_margin():
    assert b.veto("claude-opus-4-5", "gpt-5.1", "file:write")                 # 80 -> 74: 6 points under
    assert b.veto("claude-opus-4-5", "gpt-5.1", "shell:ls")                   # 60 -> 50
    assert not b.veto("claude-opus-4-5", "five", "file:write")                # exactly 5 points: not beyond
    assert b.veto("claude-opus-4-5", "five", "file:write", margin=4.0)
    assert not b.veto("gpt-5.1", "claude-opus-4-5", "file:write")             # better, no veto
    assert not b.veto("gpt-5.1", "tiny", "file:write")                        # new model lacks that benchmark
    assert not b.veto("claude-opus-4-5", "gpt-5.1", "computer:use")           # old model lacks that benchmark
    assert not b.veto("gpt-5.1", "tiny", "message:send")                      # no benchmark for the type
    assert not b.veto("claude-opus-4-5", "gpt-5.1", "shell:git:push")


def test_snapshot_has_attribution():
    snap = b.load()
    for k in ("source", "license", "url", "accessed", "benchmarks", "models"):
        assert snap[k]
    assert "CC BY 4.0" in snap["license"]
    real = json.loads(b.Path(__file__).parent.parent.joinpath("clearance", "data", "benchmarks.json").read_text())
    assert real["license"] == "CC BY 4.0" and real["url"].startswith("https://epoch.ai/") and real["accessed"]
    assert real["benchmarks"] and real["models"]
    notice = b.Path(__file__).parent.parent.joinpath("clearance", "NOTICE").read_text()
    assert "Epoch AI" in notice and "CC BY 4.0" in notice and real["accessed"] in notice
