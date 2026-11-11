"""The opt-in community benchmark: the shared record carries counts only (no path, script or profile name), its
signature verifies and a changed record does not, the aggregator keeps one record per key, the dashboard has
nothing to show without a board, and `hermes tenure share` writes the file."""
import copy
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from test_plugin import FAST, NPM, climb, plugin, to_t3  # noqa: F401

pytest.importorskip("cryptography")
ROOT = Path(__file__).resolve().parents[1]


def shared(plugin, tmp_path):
    mod, ctx = plugin(FAST)
    to_t3(ctx)
    ctx.call("terminal", NPM)
    ctx.call("terminal", {"command": "make secret_target_xyz"})
    ctx.call("terminal", {"command": "python3 /home/me/acme-project/deploy_prod.py"})
    ctx.call("terminal", {"command": "npm run my_private_script"})
    return mod, ctx


def test_family_keeps_fixed_words_only():
    from tenure import community as c
    assert c.family("file:write") == "file:write"
    assert c.family("shell:git:commit") == "shell:git:commit"
    assert c.family("shell:npm:run:build") == "shell:npm:run"
    assert c.family("shell:python3:deploy.py") == "shell:python3"
    assert c.family("shell:make:release") == "shell:make"
    assert c.family("shell:deploy.sh") == "shell:other"
    assert c.family("shell:git:my-alias") == "shell:git"
    assert c.family("mcp:notion:create_page") == "mcp"
    assert c.family("tool:acme_internal") == "tool"
    assert c.family("weird:thing") == "other"
    for k in ("shell:npm:run:build", "shell:deploy.sh", "mcp:x:y", "file:write", "shell:git:push", "other"):
        assert c.family(c.family(k)) == c.family(k)
    assert c.model_name("/Users/me/models/llama.gguf") == "local-model" and c.model_name("gpt-5") == "gpt-5"


def test_record_has_counts_only_and_no_names(plugin, tmp_path):
    mod, ctx = shared(plugin, tmp_path)
    from tenure import community
    rec = community.share_record(mod.store_(), mod.settings(), mod.data_dir())
    text = json.dumps(rec)
    for secret in ("secret_target_xyz", "deploy_prod", "acme-project", "/home/me", "my_private_script",
                   str(tmp_path), "s1", "s2"):
        assert secret not in text, secret
    assert set(rec) == set(community.RECORD_KEYS)
    assert len(rec["date"]) == 10 and "T" not in rec["date"]
    fams = {r["family"] for r in rec["rows"]}
    assert "file:write" in fams and all(community.family(f) == f for f in fams)
    for r in rec["rows"]:
        assert set(r) == set(community.ROW_KEYS) and r["model"] == "model-a" and r["provider"] == "nous"
    fw = next(r for r in rec["rows"] if r["family"] == "file:write")
    assert fw["successes"] >= 4 and fw["faults"] == 0
    assert rec["preset"] and set(rec["risks"]) == {"low", "medium", "high"}
    assert community.verify_record(rec) == []


def test_tampered_record_fails(plugin, tmp_path):
    mod, ctx = shared(plugin, tmp_path)
    from tenure import community
    rec = community.share_record(mod.store_(), mod.settings(), mod.data_dir())
    bad = copy.deepcopy(rec)
    bad["rows"][0]["faults"] = 0 if bad["rows"][0]["faults"] else 7
    assert "signature does not match the record's content" in community.verify_record(bad)
    named = copy.deepcopy(rec)
    named["rows"][0]["family"] = "shell:python3:deploy_prod.py"
    assert any("not a coarse action family" in p for p in community.verify_record(named))
    extra = dict(rec, project="acme")
    assert community.verify_record(extra)
    assert community.verify_record(dict(rec, signature=None))


def _record(key, rows, date="2026-11-01"):
    from tenure import community
    rec = {"format": community.FORMAT, "date": date, "tenure": "1.0.0", "rule": "study-rule-B/1",
           "preset": "balanced", "risks": {"low": 0.02, "medium": 0.01, "high": None}, "rows": rows}
    rec["public_key"] = key.public_key().public_bytes_raw().hex()
    rec["signature"] = key.sign(community._payload(rec)).hex()
    return rec


def test_aggregate_dedupes_by_key_and_sums():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from tenure import community, personal
    a, b = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    row = lambda m, s, f, fam="file:write": {"model": m, "provider": "nous", "family": fam, "successes": s, "faults": f}
    old_a = _record(a, [row("m1", 100, 50)], "2026-10-01")
    new_a = _record(a, [row("m1", 30, 1), row("m2", 40, 0)], "2026-11-01")
    rec_b = _record(b, [row("m1", 20, 2)])
    forged = copy.deepcopy(rec_b)
    forged["rows"][0]["successes"] = 9999
    board = community.aggregate([old_a, new_a, rec_b, forged, {"nope": 1}])
    assert board["format"] == community.BOARD_FORMAT and board["records"] == 2 and board["dropped"] == 2
    (fam,) = board["families"]
    assert fam["family"] == "file:write"
    by = {m["model"]: m for m in fam["models"]}
    assert (by["m1"]["successes"], by["m1"]["faults"], by["m1"]["contributors"], by["m1"]["checks"]) == (50, 3, 2, 53)
    assert (by["m1"]["low"], by["m1"]["high"]) == personal.wilson(3, 53)
    assert by["m2"]["contributors"] == 1
    assert [m["model"] for m in fam["models"]] == sorted(by, key=lambda k: by[k]["high"])   # ranked by upper bound


def test_aggregate_script_writes_board(tmp_path):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    recs = tmp_path / "records"
    recs.mkdir()
    good = _record(Ed25519PrivateKey.generate(), [{"model": "m", "provider": "p", "family": "memory:write",
                                                   "successes": 5, "faults": 1}])
    (recs / "a.json").write_text(json.dumps(good))
    (recs / "b.json").write_text("{broken")
    out = tmp_path / "board.json"
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "aggregate_community.py"), str(recs), "--out", str(out)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "dropped b.json" in r.stdout
    board = json.loads(out.read_text())
    assert board["records"] == 1 and board["dropped"] == 1
    from tenure import community
    assert community.load_board(str(out)) == board


def test_load_board_rejects_what_is_not_a_board(tmp_path):
    from tenure import community
    assert community.load_board(str(tmp_path / "missing.json")) is None
    p = tmp_path / "x.json"
    p.write_text(json.dumps({"format": "other"}))
    assert community.load_board(str(p)) is None
    p.write_text(json.dumps({"format": community.BOARD_FORMAT, "families": [{"family": "f", "models": [{"low": "x"}]}]}))
    assert community.load_board(str(p)) is None


def test_no_bundled_board_ships():
    assert not list((ROOT / "tenure").rglob("community-board*.json"))


def test_dashboard_api_without_and_with_board(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from test_dashboard_api import FastAPI, TestClient, load_api     # the TestClient import, warning filtered there
    root = tmp_path / "hermes"
    monkeypatch.setenv("HERMES_HOME", str(root))
    core = importlib.reload(importlib.import_module("tenure"))
    api = load_api()
    app = FastAPI()
    app.include_router(api.router, prefix="/api/plugins/tenure")
    client = TestClient(app)
    d = client.get("/api/plugins/tenure/community").json()
    assert d["board"] is None and d["path"].endswith(os.path.join("plugin-data", "tenure", "community-board.json"))
    assert not (root / "plugin-data").exists()                       # a read creates nothing
    from tenure import community
    board = community.aggregate([])
    os.makedirs(os.path.dirname(d["path"]))
    Path(d["path"]).write_text(json.dumps(board))
    assert client.get("/api/plugins/tenure/community").json()["board"] == board
    assert core.data_dir() in d["path"]


def test_cli_share_writes_the_file(plugin, tmp_path, monkeypatch):
    mod, ctx = shared(plugin, tmp_path)
    monkeypatch.chdir(tmp_path)
    out = mod.cli.slash("share")
    files = list(tmp_path.glob("tenure-record-*.json"))
    assert len(files) == 1 and "Community record written" in out and "Nothing was sent" in out
    assert "otsoa-dubief/tenure-community" in out and "file:write" in out
    assert "secret_target_xyz" not in out and "deploy_prod" not in out
    from tenure import community
    rec = json.loads(files[0].read_text())
    assert community.verify_record(rec) == []
    target = tmp_path / "sub" / "mine.json"
    assert "mine.json" in mod.cli.slash(f"share --out {target}") and target.exists()


def test_cli_share_with_nothing_recorded(plugin, tmp_path, monkeypatch):
    mod, ctx = plugin(FAST)
    monkeypatch.chdir(tmp_path)
    assert mod.cli.slash("share").startswith("No verified outcome yet")
    assert not list(tmp_path.glob("tenure-record-*.json"))
