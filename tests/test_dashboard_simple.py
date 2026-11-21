"""The dashboard tab and the Desktop page in simple mode: GET /simple is ``/tenure`` and ``/tenure trust`` as data, read
with the CLI's own functions (same kinds, same states, same numbers), in the page's language; study mode gets the
mode alone and keeps every other payload as it was; no route frees a kind."""
import json
import os
import re
import sys
import warnings

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi import FastAPI                      # noqa: E402
with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message="Using `httpx` with `starlette.testclient` is deprecated")
    from fastapi.testclient import TestClient    # noqa: E402

from test_dashboard_api import Ctx, files, load_api          # noqa: E402
from test_plugin import A, FAST, plugin                        # noqa: E402,F401  (plugin is a fixture)
from test_simple_commands import (last_undo, make, numbers, touch, trust_line,  # noqa: E402
                                  watched_and_asking)

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the commands are POSIX")
STUDY_WORDS = re.compile(r"\b(?:T[123]|trusted|probation|spot|guarantee|tiers?)\b", re.I)


def client_for():
    api = load_api()
    app = FastAPI()
    app.include_router(api.router, prefix="/api/plugins/tenure")
    return api, TestClient(app)


def simple(client, **params):
    r = client.get("/api/plugins/tenure/simple", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def kinds_of(d, agent=A):
    return {k["type"]: k for k in next(a for a in d["agents"] if a["agent"] == agent)["kinds"]}


def trust_lines(mod):
    return {ln.split()[0]: ln for ln in mod.cli.slash("trust").splitlines()
            if ln.startswith("  ") and ":" in ln.split()[0]}          # the kinds' lines, not the header


def test_simple_payload_is_tenure_trust_as_data(plugin):
    mod, ctx = make(plugin)
    watched_and_asking(mod, ctx)                                   # file:write watched, shell:npm asks
    ctx.call("terminal", {"command": "git push origin main"})      # always asks
    ctx.call("terminal", {"command": "pip install requests"})
    api, client = client_for()
    d = simple(client, raw=1)
    assert d["mode"] == "simple" and d["profile"] == "default" and d["agent"] == A and d["enabled"] is True
    assert d["agents"][0]["agent"] == A
    kinds = kinds_of(d)
    lines = trust_lines(mod)
    assert set(kinds) == set(lines)                                # what /tenure trust lists, nothing more
    for key, k in kinds.items():
        assert k["label"] == mod.cli.kind_label(key)
        assert k["text"] in lines[key]                             # the same sentence...
        assert numbers(k["text"]) == numbers(lines[key])           # ...so the same numbers
        assert [x["n"] for x in k["steps"] if "n" in x] == numbers(lines[key])
    assert (kinds["file:write"]["state"], kinds["file:write"]["group"]) == ("watched", "watched")
    assert kinds["file:write"]["steps"] == [{"key": "trust.state.watched", "n": 4}]
    assert (kinds["shell:npm"]["state"], kinds["shell:npm"]["group"]) == ("ask", "ask")
    assert kinds["shell:npm"]["left"] == 5 and kinds["shell:npm"]["n"] == 5
    assert (kinds["shell:git:push"]["state"], kinds["shell:git:push"]["group"]) == ("out", "always")
    states = {s.key: s for _, s in mod.store_().states(A)}
    assert d["agents"][0]["free"] == len(states) - len(kinds)      # free kinds counted, not listed


def test_two_steps_of_a_reversible_kind_carry_the_trust_numbers(plugin):
    mod, ctx = make(plugin, {"risks": {"low": "1/50", "medium": "1/100"}})       # n = 52: the score decides first
    for i in range(2):
        ctx.call("write_file", {"path": "src/a.py", "content": f"x = {i}\n"})
        mod.cli.slash(f"undo {last_undo(mod)}")
    api, client = client_for()
    k = kinds_of(simple(client, raw=1))["file:write"]
    approvals, unseen = numbers(trust_line(mod, "file:write"))
    assert k["state"] == "ask" and k["group"] == "ask"
    assert k["steps"] == [{"key": "trust.state.ask_watched", "n": approvals},
                          {"key": "trust.state.then_free", "n": unseen}]
    assert approvals == mod._to_t2(mod.store_().recorded(A, "file:write")) and approvals + unseen == 52


def test_a_pinned_kind_says_why_and_how_to_free_it(plugin):
    mod, ctx = make(plugin)
    ctx.call("write_file", {"path": "src/a.py", "content": "x = 1\n"})
    mod.cli.slash("trust file:write ask")                          # the person's choice: it asks until freed
    api, client = client_for()
    k = kinds_of(simple(client, raw=1))["file:write"]
    assert (k["state"], k["group"]) == ("pinned", "ask")
    assert k["steps"] == [{"key": "trust.state.pinned", "command": "/tenure trust file:write"}]
    assert k["text"] in trust_line(mod, "file:write")


def test_undo_rows_and_today_are_what_tenure_lists(plugin):
    mod, ctx = make(plugin)
    touch(ctx, "notes.txt")
    ctx.call("write_file", {"path": "src/a.py", "content": "x = 1\n"})
    ctx.call("terminal", {"command": "rm notes.txt"})
    ctx.call("terminal", {"command": "echo token=ghp_abcdefghijklmnopqrstuvwxyz0123456789 > out.txt"})
    home = mod.cli.slash("")
    ids = [int(ln.split()[0]) for ln in home.splitlines() if ln.startswith("  ") and ln.strip()[:1].isdigit()]
    api, client = client_for()
    for raw in (1, 0):
        d = simple(client, raw=raw)
        rows = d["undo"]["rows"]
        assert [r["id"] for r in rows] == ids and d["undo"]["total"] == len(ids)    # newest first, as /tenure
        assert d["today"] == int(re.search(r"Ran without asking today: (\d+)", home).group(1))
        assert d["hours"] == 24
        assert all(r["label"] == mod.cli.kind_label(r["type"]) and r["counts_as_fault"] for r in rows)
        by_type = {r["type"]: r for r in rows}
        assert "src/a.py" in by_type["file:write"]["what"]
        assert not any("ghp_abcdef" in r["what"] for r in rows)                       # masked or not shown
    assert all(r["what"] for r in simple(client, raw=0)["undo"]["rows"])


def test_texts_follow_the_page_language_and_leave_the_owner_s(plugin):
    mod, ctx = make(plugin)
    watched_and_asking(mod, ctx)
    api, client = client_for()
    en = kinds_of(simple(client, raw=1))
    fr = kinds_of(simple(client, raw=1, lang="fr"))
    for key, k in fr.items():
        assert k["steps"] == en[key]["steps"]                      # the same numbers in every language
        want = " ".join(mod.i18n.tr(x["key"], lang="fr", **{a: b for a, b in x.items() if a != "key"})
                        for x in k["steps"])
        assert k["text"] == want and k["text"] != en[key]["text"]
    assert fr["file:write"]["label"] == mod.i18n.tr("kind.file_write", lang="fr")
    assert mod.i18n.language() == "en" and "watched" in mod.cli.slash("trust")    # the owner's language is untouched


def test_nothing_in_simple_mode_speaks_of_tiers(plugin):
    mod, ctx = make(plugin)
    watched_and_asking(mod, ctx)
    ctx.call("terminal", {"command": "git push origin main"})
    api, client = client_for()
    for lang in ("en", "fr", "es", "zh", "ar"):
        d = simple(client, raw=1, lang=lang)
        texts = [k["text"] for a in d["agents"] for k in a["kinds"]]
        assert texts and not any(STUDY_WORDS.search(x) for x in texts), texts
        assert not any(k in d for k in ("tier", "guarantee", "spot", "trusted", "required", "series"))


def test_study_mode_gets_the_mode_alone_and_keeps_its_payloads(plugin):
    mod, ctx = plugin({"mode": "study", **FAST})
    ctx.call("write_file", {"path": "src/a.py", "content": "x = 1\n"})
    api, client = client_for()
    assert simple(client) == {"profile": "default", "mode": "study"}
    agents = client.get("/api/plugins/tenure/agents").json()
    p = agents["profiles"][0]
    assert set(p) == {"profile", "current", "suspended", "settings", "agents"}
    assert set(p["settings"]) == {"preset", "risks", "spot", "strict", "pending", "start", "mode", "enabled",
                                  "copy_pending"}
    assert p["settings"]["mode"] == "study"
    assert set(p["agents"][0]["types"][0]) == {
        "type", "stakes", "reversible", "tier", "effective_tier", "trusted", "distrusted", "capped", "required",
        "series", "sessions", "wald", "successes", "faults", "neutrals", "spot_checks", "provisional", "trial_left",
        "trial_wait", "unresolved_fault", "unresolved_fault_label", "held", "guarantee"}
    act = client.get("/api/plugins/tenure/activity").json()
    assert set(act) == {"since", "totals", "profiles", "undoable"}


def test_no_route_writes_more_than_before_and_none_frees_a_kind(plugin):
    mod, ctx = make(plugin)
    api, client = client_for()
    posts = {r.path for r in api.router.routes if "POST" in getattr(r, "methods", set())}
    assert posts == {"/revoke", "/flag", "/undo", "/settings"}
    gets = {r.path for r in api.router.routes if "GET" in getattr(r, "methods", set())}
    assert "/simple" in gets
    assert not any("trust" in r.path or "free" in r.path for r in api.router.routes)
    assert client.post("/api/plugins/tenure/simple", json={}).status_code == 405
    assert not any("trust" in f or "free" in f for f in api.SettingsBody.model_fields)   # no setting frees one


def test_simple_reads_never_write(plugin, tmp_path):
    mod, ctx = make(plugin)
    watched_and_asking(mod, ctx)
    api, client = client_for()
    root = os.environ["HERMES_HOME"]
    before = files(root)
    for raw in (0, 1):
        simple(client, raw=raw, lang="fr")
    assert files(root) == before


def test_undo_from_the_simple_page_goes_through_the_existing_route(plugin):
    mod, ctx = make(plugin)
    ctx.call("write_file", {"path": "src/a.py", "content": "x = 1\n"})
    api, client = client_for()
    row = simple(client, raw=1)["undo"]["rows"][0]
    r = client.post("/api/plugins/tenure/undo", json={"id": row["id"]})
    assert r.status_code == 200 and r.json()["ok"] and not os.path.exists(os.path.join(ctx.cwd, "src/a.py"))
    d = simple(client, raw=1)
    assert d["undo"]["rows"] == [] and kinds_of(d)["file:write"]["state"] == "watched"


def test_a_profile_without_a_database_is_simple_and_empty(tmp_path, monkeypatch):
    import importlib
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    core = importlib.reload(importlib.import_module("tenure"))
    core.ST.ctx = Ctx()
    core.ST.ctx.settings["mode"] = "simple"
    api, client = client_for()
    d = simple(client)
    assert d == {"profile": "default", "mode": "simple", "enabled": True, "hours": 24, "today": 0, "agent": None,
                 "undo": {"total": 0, "rows": []}, "agents": []}
    assert not os.path.exists(tmp_path / "hermes" / "plugin-data" / "tenure" / "tenure.db")


def test_the_last_active_agent_comes_first(plugin):
    mod, ctx = make(plugin)
    ctx.call("write_file", {"path": "src/a.py", "content": "x = 1\n"})
    mod.pre_api_request(model="model-b", provider="nous", session_id="s2")
    ctx.call("write_file", {"path": "src/b.py", "content": "x = 1\n"}, session="s2")
    api, client = client_for()
    d = simple(client, raw=1)
    assert [a["agent"] for a in d["agents"]] == ["model-b@nous", A] and d["agent"] == "model-b@nous"
    assert json.dumps(d)                                           # plain JSON all through
