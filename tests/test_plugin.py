"""The four hooks inside Hermes, with a fake plugin context: decisions before a call, verified outcomes after it,
act-then-notify with undo, suspension after external reads, carry-over on a model change, and a ledger that a replay
can trust."""
import hashlib
import importlib
import json
import logging
import os
import re
import threading

import pytest

PKG = "clearance"
A, B, C = "model-a@nous", "model-b@nous", "model-c@nous"
FAST = {"risks": {"low": 0.25, "medium": 0.2}}       # series length 4 at low stakes, 5 at medium; high capped
NPM = {"command": "npm test"}
OUTCOME_FIELDS = {"event", "agent", "type", "stakes", "reversible", "result", "source", "session"}


def anon(session_id):
    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:12]


class FakeCtx:
    """Hermes as a plugin sees it: config, the session's cwd, messages, cron state and the hook registry.

    ``call`` runs one tool call the way Hermes' dispatch does: pre_tool_call; for an approve directive, the approval
    gate (Hermes' session/always allowlist, cron_mode, yolo, else a prompt answered by the scripted owner, which fires
    post_approval_response); then the tool, or a blocked result; then post_tool_call with Hermes' status fields."""

    def __init__(self, settings=None, cron=False, cwd="/home/me/project"):
        self.settings = dict(settings or {})
        self.posted = []
        self.cron = cron
        self.cron_mode = "deny"          # approvals.cron_mode: Hermes' default denies what would ask
        self.cwd = cwd
        self.hooks, self.commands, self.cli = {}, {}, {}
        self.granted = set()             # rule keys answered "session"/"always": Hermes asks for them no more
        self.prompts = []                # approve directives that reached the owner
        self.calls = 0

    def get_config(self, key, default=None):
        return self.settings.get(key, default)

    def set_config(self, key, value):
        self.settings[key] = value

    def session_cwd(self):
        return self.cwd

    def post_message(self, text):
        self.posted.append(text)

    def current_cron_execution(self):
        return object() if self.cron else None

    def register_hook(self, name, fn):
        self.hooks[name] = fn

    def register_command(self, name, handler, description=""):
        self.commands[name] = handler

    def register_cli_command(self, name, help, setup_fn, handler_fn):
        self.cli[name] = (setup_fn, handler_fn)

    def call(self, tool, args, answer="once", session="s1", status="ok", result=None, call_id=None,
             blocked_after=False):
        """'ran' (no prompt), 'approved' (prompted, approved), 'refused' (prompted, not approved) or 'blocked'
        (blocked without a prompt)."""
        self.calls += 1
        ids = dict(session_id=session, task_id=session, tool_call_id=f"tc-{self.calls}" if call_id is None else call_id)
        directive = self.hooks["pre_tool_call"](tool_name=tool, args=args, **ids)
        verdict = "ran"
        if isinstance(directive, dict) and directive.get("action") == "approve":
            key = directive.get("rule_key") or tool
            if key in self.granted:
                ok = True
            elif self.cron:
                ok, verdict = self.cron_mode == "approve", "blocked"
            elif os.environ.get("HERMES_YOLO_MODE"):
                ok = True
            else:
                self.prompts.append(directive)
                extra = {"decided_by": "aux_llm"} if answer.startswith("smart") else {}
                self.hooks["post_approval_response"](
                    command=f"<{tool}> (plugin approval rule)", description=directive.get("message", ""),
                    pattern_key=f"plugin_rule:{key}", pattern_keys=[f"plugin_rule:{key}"], session_key=session,
                    surface="cli", tool_call_id=ids["tool_call_id"], choice=answer, **extra)
                ok = answer in ("once", "session", "always", "smart_approve")
                if answer in ("session", "always"):
                    self.granted.add(key)
                verdict = "approved" if ok else "refused"
            if not ok:
                self.hooks["post_tool_call"](tool_name=tool, args=args, result=json.dumps({"error": "blocked"}),
                                             status="blocked", error_type="plugin_block", **ids)
                return verdict
            verdict = "ran" if verdict == "blocked" else verdict
        if blocked_after:                # a later guard (ACP edit approval) blocks the call after ours
            self.hooks["post_tool_call"](tool_name=tool, args=args, result=json.dumps({"error": "denied"}),
                                         status="blocked", error_type="edit_approval_denied", **ids)
            return verdict
        if status == "ok" and tool == "write_file":
            path = os.path.join(self.cwd, args["path"])
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(args.get("content", ""))
        self.hooks["post_tool_call"](
            tool_name=tool, args=args, result=result if result is not None else json.dumps({"success": True}),
            status=status, error_type=None if status == "ok" else "tool_error", **ids)
        return verdict


class Picks:
    """Deterministic draws for spot checks: 0.99 = no check, 0.0 = check."""
    def __init__(self, values=None):
        self.values = list(values or [])

    def random(self):
        return self.values.pop(0) if self.values else 0.99


@pytest.fixture
def plugin(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    monkeypatch.delenv("HERMES_YOLO_MODE", raising=False)
    mod = importlib.reload(importlib.import_module(PKG))
    project = tmp_path / "project"
    project.mkdir()

    def make(settings=None, **kw):
        kw.setdefault("cwd", str(project))
        ctx = FakeCtx(settings, **kw)
        mod.register(ctx)
        mod.ST.rng = Picks()
        mod.pre_api_request(model="model-a", provider="nous", session_id="s1")
        return mod, ctx
    return make


# ------------------------------------------------------------------------------------------------------- helpers
def state(mod, key, agent=A):
    return {s.key: s for _, s in mod.store_().states(agent)}.get(key)


def ledger(mod, kind=None):
    rows = [r["event"] for r in mod.store_().ledger()]
    return rows if kind is None else [e for e in rows if e["event"] == kind]


def outcomes(mod, **match):
    return [e for e in ledger(mod, "outcome") if all(e.get(k) == v for k, v in match.items())]


def write(name="a", content="x = 1\n"):
    return {"path": f"src/{name}.py", "content": content}


def pre(mod, tool, args, call, session="s1"):
    return mod.pre_tool_call(tool_name=tool, args=args, session_id=session, task_id=session, tool_call_id=call)


def answer(mod, directive, call, choice, **kw):
    return mod.post_approval_response(pattern_key=f"plugin_rule:{directive['rule_key']}", tool_call_id=call,
                                      choice=choice, surface="cli", session_key="s1", **kw)


def post(mod, tool, args, call, status="ok", result='{"success": true}', session="s1"):
    return mod.post_tool_call(tool_name=tool, args=args, result=result, session_id=session, task_id=session,
                              tool_call_id=call, status=status, error_type=None if status == "ok" else "tool_error")


def climb(ctx, n, session="s1", name="a", tool="write_file"):
    for i in range(n):
        args = write(f"{name}{session}{i}") if tool == "write_file" else {"action": "add", "content": f"{name}{i}"}
        ctx.call(tool, args, session=session)


def to_t3(ctx, tool="write_file"):
    """Two sessions, four verified successes: T3 under FAST at low stakes."""
    climb(ctx, 2, "s1", tool=tool)
    climb(ctx, 2, "s2", tool=tool)


def age(mod, call, seconds=90000):
    with mod.txn() as st:
        st.db.execute("UPDATE pending SET at = at - ? WHERE tool_call_id = ?", (seconds, call))


# ------------------------------------------------------------------------------------------------ registration
def test_registers_four_hooks_and_commands(plugin):
    mod, ctx = plugin()
    assert set(ctx.hooks) == {"pre_api_request", "pre_tool_call", "post_approval_response", "post_tool_call"}
    assert "clearance" in ctx.commands and "clearance" in ctx.cli


def test_settings_validate_spot_and_add_strict_and_preset(plugin):
    mod, ctx = plugin({"spot_check": 1.5})
    cfg = mod.settings()
    assert cfg["spot"] == mod.params.DEFAULT_SPOT and cfg["strict"] is False and cfg["preset"] == "balanced"
    for bad in (0, 1, -0.2, "nan", "inf", "cap", "abc", None):
        ctx.settings["spot_check"] = bad
        assert mod.settings()["spot"] == mod.params.DEFAULT_SPOT
    ctx.settings.update(spot_check="1/20", strict=True, preset="careful")
    cfg = mod.settings()
    assert cfg["spot"] == pytest.approx(0.05) and cfg["strict"] is True and cfg["preset"] == "careful"
    assert cfg["risks"] == mod.params.PRESETS["careful"]


def test_data_dir_agent_of_and_anonymous_sessions(plugin):
    mod, ctx = plugin()
    assert mod.data_dir().endswith(os.path.join("plugin-data", "clearance"))
    assert mod.agent_of("s1") == A
    mod.pre_api_request(model="local:8b-q4", provider="", session_id="s9")
    assert mod.agent_of("s9") == "local:8b-q4@unknown"
    assert mod.agent_of("never-seen") == "local:8b-q4@unknown"       # the agent of the latest API request
    assert mod.anon("s1") == anon("s1") and mod.anon("") == ""


# ------------------------------------------------------------------------------------------------ pre_api_request
def test_pre_api_request_sets_agent_last(plugin):
    mod, _ = plugin()
    assert mod.store_().get_meta("agent:last") == A
    mod.pre_api_request(model="model-b", provider="openrouter", session_id="s2")
    assert mod.store_().get_meta("agent:last") == "model-b@openrouter"
    assert mod.pre_api_request(model="", provider="x", session_id="s2") is None
    assert mod.store_().get_meta("agent:last") == "model-b@openrouter"


def test_model_switch_carries_half_on_trial(plugin):
    mod, ctx = plugin()                                       # balanced: 52 in a row at low stakes
    climb(ctx, 20)                                            # 12 asks to T2, then 8 acts-then-notifies
    a = state(mod, "file:write")
    assert (a.series, a.tier) == (20, mod.rule.T2)
    mod.pre_api_request(model="model-b", provider="nous", session_id="s1")
    b = state(mod, "file:write", B)
    assert (b.series, b.provisional, b.tier, b.sessions, b.successes) == (10, 10, mod.rule.T1, [], 0)
    assert b.wald == pytest.approx(a.wald / 2)
    assert state(mod, "file:write").series == 20              # the old agent's record is untouched
    assert ledger(mod, "agent")[-1] == {"event": "agent", "old": A, "new": B, "mode": "carry", "vetoed": []}
    assert mod.store_().get_meta("agent:last") == B
    assert any("1 carried over on trial, 0 reset, 0 vetoed" in p for p in ctx.posted)
    assert mod.rule.guarantee(b, 52, 0.1)["conditional"]
    for i in range(4):                                        # half of the old score: four own successes to T2
        assert ctx.call("write_file", write(f"b{i}")) == "approved"
    b = state(mod, "file:write", B)
    assert (b.tier, b.series, b.provisional) == (mod.rule.T2, 14, 6)


def test_veto_comes_from_public_benchmarks_with_the_model_part(plugin, monkeypatch):
    mod, ctx = plugin(FAST)
    climb(ctx, 3)
    ctx.call("terminal", NPM)
    ctx.call("terminal", NPM)
    seen = []

    def veto(old_model, new_model, type_key, margin=5.0):
        seen.append((old_model, new_model, type_key))
        return type_key == "file:write"
    monkeypatch.setattr(mod.benchmarks, "veto", veto)
    mod.pre_api_request(model="model-x@20250514", provider="vertex", session_id="s1")   # Vertex ids hold an "@"
    new = "model-x@20250514@vertex"
    assert sorted(seen) == [("model-a", "model-x@20250514", "file:write"),
                            ("model-a", "model-x@20250514", "shell:npm")]
    assert ledger(mod, "agent")[-1]["vetoed"] == ["file:write"]
    assert (state(mod, "file:write", new).series, state(mod, "shell:npm", new).provisional) == (0, 1)
    assert any("1 carried over on trial, 0 reset, 1 vetoed" in p for p in ctx.posted)


def test_strict_mode_resets(plugin):
    mod, ctx = plugin({"strict": True, **FAST})
    assert ctx.call("terminal", NPM, answer="deny") == "refused"     # a medium fault stays on record
    climb(ctx, 3)
    mod.pre_api_request(model="model-b", provider="nous", session_id="s1")
    w, npm = state(mod, "file:write", B), state(mod, "shell:npm", B)
    assert (w.series, w.provisional, w.wald, w.tier) == (0, 0, 0.0, mod.rule.T1)
    assert npm.trial_left == 3 and npm.unresolved_fault and npm.series == 0     # the old fault becomes a trial
    assert ledger(mod, "agent")[-1] == {"event": "agent", "old": A, "new": B, "mode": "strict", "vetoed": []}
    assert any("0 carried over on trial, 2 reset, 0 vetoed" in p and "Strict mode" in p for p in ctx.posted)


def test_a_known_agent_keeps_its_own_record(plugin):
    mod, ctx = plugin(FAST)
    climb(ctx, 3)
    mod.pre_api_request(model="model-b", provider="nous", session_id="s1")
    climb(ctx, 1, name="b")
    mod.pre_api_request(model="model-a", provider="nous", session_id="s1")       # back to a model with a record
    assert state(mod, "file:write").series == 3 and len(ledger(mod, "agent")) == 1
    assert mod.store_().get_meta("agent:last") == A


def test_a_new_model_in_a_new_session_inherits_from_the_last_agent(plugin):
    mod, ctx = plugin(FAST)
    climb(ctx, 2)
    mod.pre_api_request(model="model-c", provider="nous", session_id="fresh-session")    # e.g. a config change
    assert state(mod, "file:write", C).provisional == 1
    assert ledger(mod, "agent")[-1]["old"] == A


# --------------------------------------------------------------------------------------------------- pre_tool_call
def test_free_actions_never_ask_and_leave_no_record(plugin):
    mod, _ = plugin()
    for tool, args in (("read_file", {"path": "a.py"}), ("terminal", {"command": "git status"}),
                       ("search_files", {"pattern": "x"})):
        assert pre(mod, tool, args, "f") is None
    assert mod.store_().states() == [] and mod.store_().get_pending("f") is None


def test_cap_asks_with_a_one_off_cap_key(plugin):
    mod, _ = plugin()
    d1, d2 = pre(mod, "write_file", {"path": ".env"}, "c1"), pre(mod, "write_file", {"path": ".env"}, "c2")
    assert d1["action"] == "approve" and d1["rule_key"] == "clearance:cap:file:sensitive:c1"
    assert d1["rule_key"] != d2["rule_key"] and "always asked" in d1["message"]
    assert mod.store_().get_pending("c1") is None and mod.store_().states() == []


def test_ask_adds_a_pending_row_in_phase_asked(plugin):
    mod, _ = plugin(FAST)
    d = pre(mod, "write_file", write(), "c1")
    assert d == {"action": "approve", "rule_key": "clearance:ask:file:write:c1", "message": d["message"]}
    assert "0/4" in d["message"] and "src/a.py" in d["message"]
    p = mod.store_().get_pending("c1")
    assert (p["phase"], p["decision"], p["agent"], p["type"], p["stakes"], p["reversible"], p["session"],
            p["snap_id"]) == ("asked", "ask", A, "file:write", "low", True, anon("s1"), None)


def test_spot_check_asks_with_a_spot_key(plugin):
    mod, ctx = plugin(FAST)
    to_t3(ctx)
    assert state(mod, "file:write").tier == mod.rule.T3
    mod.ST.rng = Picks([0.0])
    assert ctx.call("write_file", write("spot1")) == "approved"
    d = ctx.prompts[-1]
    assert d["rule_key"].startswith("clearance:spot:file:write:") and "spot check" in d["message"]
    assert outcomes(mod)[-1]["result"] == "success" and outcomes(mod)[-1]["source"] == "spot"
    assert state(mod, "file:write").spot_checks == 1
    mod.ST.rng = Picks([0.0])
    assert ctx.call("write_file", write("spot2"), answer="deny") == "refused"
    assert outcomes(mod)[-1]["result"] == "fault" and outcomes(mod)[-1]["source"] == "spot"
    s = state(mod, "file:write")
    assert (s.spot_checks, s.faults, s.tier) == (2, 1, mod.rule.T2)        # one tier down at low stakes


def test_notify_saves_the_files_then_runs(plugin):
    mod, ctx = plugin(FAST)
    climb(ctx, 11)
    assert state(mod, "file:write").tier == mod.rule.T1
    climb(ctx, 1, name="z")
    assert state(mod, "file:write").tier == mod.rule.T2        # one session: no T3, the Wald test gives T2
    target = os.path.join(ctx.cwd, "src", "x.py")
    with open(target, "w") as f:
        f.write("old = 1\n")
    assert pre(mod, "write_file", {"path": "src/x.py", "content": "new = 2\n"}, "n1") is None
    p = mod.store_().get_pending("n1")
    assert (p["phase"], p["decision"], p["rule_key"]) == ("notify", "notify", "") and p["snap_id"]
    assert os.path.isfile(os.path.join(mod.data_dir(), "undo", p["snap_id"], "manifest.json"))


def test_notify_falls_back_to_ask_when_the_file_cannot_be_saved(plugin, monkeypatch):
    mod, ctx = plugin(FAST)
    climb(ctx, 12)
    assert state(mod, "file:write").tier == mod.rule.T2
    src = os.path.join(ctx.cwd, "src")
    with open(os.path.join(src, "blob.py"), "wb") as f:
        f.write(b"\x00\x01binary")
    with open(os.path.join(src, "huge.py"), "wb") as f:
        f.write(b"#" * 5_000_001)
    for i, name in enumerate(("blob", "huge")):
        d = pre(mod, "write_file", {"path": f"src/{name}.py", "content": "x = 1\n"}, f"f{i}")
        assert d["action"] == "approve" and d["rule_key"] == f"clearance:ask:file:write:f{i}"
        assert "undo" in d["message"]
        p = mod.store_().get_pending(f"f{i}")
        assert (p["phase"], p["decision"], p["snap_id"]) == ("asked", "ask", None)
    monkeypatch.setattr(mod.undo, "snapshot", lambda *a, **k: None)
    assert pre(mod, "write_file", write("plain"), "f2")["action"] == "approve"


def test_allow_adds_an_alone_row_and_runs(plugin):
    mod, ctx = plugin(FAST)
    to_t3(ctx)
    assert pre(mod, "write_file", write("alone"), "a1") is None
    p = mod.store_().get_pending("a1")
    assert (p["phase"], p["decision"], p["rule_key"], p["snap_id"]) == ("alone", "allow", "", None)


def test_nobody_answers_earned_tiers_run_and_the_rest_falls_to_hermes(plugin):
    mod, ctx = plugin(FAST)
    climb(ctx, 12)                                           # file:write at T2
    to_t3(ctx, tool="memory")                                # memory:write at T3
    ctx.cron = True
    d = pre(mod, "terminal", NPM, "n1")
    assert d["action"] == "approve" and d["rule_key"] == "clearance:ask:shell:npm:n1"
    assert mod.store_().get_pending("n1")["phase"] == "nobody"
    assert ctx.call("terminal", NPM) == "blocked"            # cron_mode denied it; nobody's answer teaches nothing
    s = state(mod, "shell:npm")
    assert (s.successes, s.faults, s.neutrals) == (0, 0, 1)
    assert outcomes(mod, type="shell:npm")[-1]["source"] == "nobody"
    assert ctx.call("write_file", write("cron")) == "ran"   # T2 still acts, with its snapshot and undo
    assert outcomes(mod)[-1]["source"] == "notify" and "/clearance undo" in ctx.posted[-1]
    mod.ST.rng = Picks([0.0])                                # a spot check would have been drawn: nobody answers
    assert pre(mod, "memory", {"action": "add", "content": "c"}, "m1") is None
    assert mod.store_().get_pending("m1")["phase"] == "alone"


def test_yolo_learns_nothing(plugin, monkeypatch):
    mod, ctx = plugin(FAST)
    monkeypatch.setenv("HERMES_YOLO_MODE", "1")
    assert ctx.call("write_file", write()) == "ran" and ctx.prompts == []
    s = state(mod, "file:write")
    assert (s.successes, s.neutrals) == (0, 1) and outcomes(mod)[-1]["source"] == "nobody"


def test_internal_error_asks_unless_the_action_is_free(plugin, monkeypatch):
    mod, _ = plugin()

    def boom(*a, **k):
        raise RuntimeError("disk on fire")
    monkeypatch.setattr(mod, "store_", boom)
    d = pre(mod, "write_file", write(), "c1")
    assert d["action"] == "approve" and d["rule_key"].startswith("clearance:ask:file:write:")
    assert d["message"].startswith("clearance: internal error (RuntimeError); asking you instead")
    assert pre(mod, "read_file", {"path": "a.py"}, "c2") is None              # classified free before any error
    monkeypatch.setattr(mod.classify, "classify", boom)
    d = pre(mod, "read_file", {"path": "a.py"}, "c3")                         # not classified: ask
    assert d["action"] == "approve" and "internal error" in d["message"]


def test_high_stakes_capped_by_the_preset_count_successes_but_never_climb(plugin):
    mod, ctx = plugin()
    for _ in range(5):
        assert ctx.call("terminal", {"command": "git push origin main"}) == "approved"
    keys = [d["rule_key"] for d in ctx.prompts]
    assert all(k.startswith("clearance:capped:shell:git:push:") for k in keys) and len(set(keys)) == 5
    assert "capped by your settings" in ctx.prompts[0]["message"]
    s = state(mod, "shell:git:push")
    assert (s.successes, s.series, s.tier) == (5, 0, mod.rule.T1)


def test_classification_uses_the_session_cwd(plugin, tmp_path):
    mod, ctx = plugin()
    inside = os.path.join(ctx.cwd, "deep", "a.py")
    pre(mod, "write_file", {"path": inside}, "c1")
    pre(mod, "write_file", {"path": "rel.py"}, "c2")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    ctx.cwd = str(elsewhere)                                  # the terminal moved: Hermes keeps the session's cwd
    pre(mod, "write_file", {"path": inside}, "c3")
    st = mod.store_()
    assert [st.get_pending(c)["type"] for c in ("c1", "c2", "c3")] == ["file:write", "file:write",
                                                                       "file:write-outside"]


def test_undo_snapshots_are_purged_at_most_once_an_hour(plugin, monkeypatch):
    mod, ctx = plugin(FAST)
    roots = []
    monkeypatch.setattr(mod.undo, "purge", lambda root, older_than=86400: roots.append(root) or 0)
    for i in range(3):
        ctx.call("write_file", write(f"p{i}"))
    assert roots == [mod.data_dir()]
    mod.ST.purged_at -= 3601
    ctx.call("write_file", write("p3"))
    assert len(roots) == 2


def test_expired_pending_rows_are_neutral(plugin):
    mod, ctx = plugin(FAST)
    d = pre(mod, "write_file", write(), "old")
    answer(mod, d, "old", "once")                             # approved, but the tool never reported back
    assert mod.store_().get_pending("old")["phase"] == "approved"
    age(mod, "old")
    ctx.call("terminal", NPM)
    assert mod.store_().get_pending("old") is None
    s = state(mod, "file:write")
    assert (s.successes, s.neutrals) == (0, 1)
    assert outcomes(mod, type="file:write") == [{"event": "outcome", "agent": A, "type": "file:write",
                                                 "stakes": "low", "reversible": True, "result": "neutral",
                                                 "source": "expired", "session": anon("s1")}]


# ------------------------------------------------------------------------------------------ post_approval_response
def test_answers_match_by_tool_call_id_or_one_off_key(plugin):
    mod, _ = plugin(FAST)
    st = mod.store_()
    d = pre(mod, "write_file", write(), "")                   # no tool call id: a uuid makes the key one-off
    one_off = d["rule_key"].rsplit(":", 1)[1]
    assert re.fullmatch(r"[0-9a-f]{32}", one_off)
    mod.post_approval_response(pattern_key=f"plugin_rule:{d['rule_key']}", tool_call_id="", choice="once")
    assert st.get_pending(one_off)["phase"] == "approved"
    d = pre(mod, "write_file", write(), "call:7:x")           # an id with colons is found by its key too
    mod.post_approval_response(pattern_key=f"plugin_rule:{d['rule_key']}", tool_call_id="", choice="once")
    assert st.get_pending("call:7:x")["phase"] == "approved"
    pre(mod, "write_file", write(), "c3")
    mod.post_approval_response(pattern_key="", tool_call_id="c3", choice="once")
    assert st.get_pending("c3")["phase"] == "approved"
    pre(mod, "write_file", write(), "c4")                     # other prompts for the same call are not ours
    mod.post_approval_response(pattern_key="plugin_rule:other-plugin:x:c4", tool_call_id="c4", choice="deny")
    mod.post_approval_response(pattern_key="recursive delete", tool_call_id="c4", choice="deny")
    assert st.get_pending("c4")["phase"] == "asked"
    mod.post_approval_response(pattern_key="plugin_rule:clearance:ask:file:write:c3", tool_call_id="c3",
                               choice="deny")                 # a second answer to a settled ask
    assert st.get_pending("c3")["phase"] == "approved"
    assert state(mod, "file:write") is None                  # no outcome yet: approvals wait for the execution


def test_refusal_is_a_fault(plugin):
    mod, ctx = plugin(FAST)
    climb(ctx, 3)
    assert ctx.call("write_file", write("no"), answer="deny") == "refused"
    s = state(mod, "file:write")
    assert (s.faults, s.series, s.sessions, s.successes) == (1, 0, [], 3)
    assert outcomes(mod)[-1] == {"event": "outcome", "agent": A, "type": "file:write", "stakes": "low",
                                 "reversible": True, "result": "fault", "source": "refusal", "session": anon("s1")}
    assert len(outcomes(mod)) == 4                           # the blocked call reports nothing more


def test_approval_waits_for_the_execution(plugin):
    mod, _ = plugin(FAST)
    d = pre(mod, "write_file", write(), "c1")
    answer(mod, d, "c1", "once")
    assert outcomes(mod) == [] and mod.store_().get_pending("c1")["phase"] == "approved"
    post(mod, "write_file", write(), "c1")
    s = state(mod, "file:write")
    assert (s.successes, s.series, s.sessions) == (1, 1, [anon("s1")])
    assert outcomes(mod)[-1]["source"] == "approval" and mod.store_().get_pending("c1") is None


def test_other_answers_are_neutral(plugin):
    mod, _ = plugin(FAST)
    answers = [("timeout", {}), ("cancelled", {}), ("notify_failed", {}), ("transport_timeout", {}),
               ("smart_approve", {"decided_by": "aux_llm"}), ("smart_deny", {"decided_by": "aux_llm"}),
               ("once", {"decided_by": "aux_llm"})]
    for i, (choice, kw) in enumerate(answers):
        d = pre(mod, "write_file", write(), f"c{i}")
        answer(mod, d, f"c{i}", choice, **kw)
        assert mod.store_().get_pending(f"c{i}") is None
        post(mod, "write_file", write(), f"c{i}")                 # a smart approval runs: nothing more to count
    s = state(mod, "file:write")
    assert (s.successes, s.faults, s.neutrals) == (0, 0, len(answers))
    assert {e["source"] for e in outcomes(mod)} == {"timeout"}


# --------------------------------------------------------------------------------------------------- post_tool_call
def test_external_reads_suspend_the_session(plugin):
    mod, ctx = plugin()
    st = mod.store_()
    ctx.call("web_extract", {"urls": ["https://example.com"]}, session="s1")
    ctx.call("read_file", {"path": "/etc/hosts"}, session="s3")       # a file outside the project
    ctx.call("read_file", {"path": "src/a.py"}, session="s4")
    assert st.is_tainted(anon("s1")) and st.is_tainted(anon("s3"))
    assert not st.is_tainted(anon("s2")) and not st.is_tainted(anon("s4"))


def test_post_tool_call_without_a_pending_row_returns_and_runs_once(plugin):
    mod, _ = plugin(FAST)
    post(mod, "write_file", write(), "unknown")
    assert outcomes(mod) == []
    d = pre(mod, "write_file", write(), "c1")
    answer(mod, d, "c1", "once")
    post(mod, "write_file", write(), "c1")
    post(mod, "write_file", write(), "c1")
    assert len(outcomes(mod)) == 1 and state(mod, "file:write").successes == 1


def test_failed_execution_is_neutral(plugin):
    mod, ctx = plugin(FAST)
    assert ctx.call("write_file", write(), status="error") == "approved"
    assert ctx.call("terminal", NPM, result=json.dumps({"output": "", "exit_code": 1})) == "approved"
    assert [(e["type"], e["result"], e["source"]) for e in outcomes(mod)] == [
        ("file:write", "neutral", "error"), ("shell:npm", "neutral", "error")]
    assert state(mod, "file:write").successes == 0 and state(mod, "shell:npm").neutrals == 1


def test_a_failed_check_is_a_fault(plugin):
    mod, ctx = plugin(FAST)
    assert ctx.call("write_file", write("bad", "def x(:\n")) == "approved"
    assert outcomes(mod)[-1]["result"] == "fault" and outcomes(mod)[-1]["source"] == "check"
    to_t3(ctx)
    assert state(mod, "file:write").tier == mod.rule.T3
    assert ctx.call("write_file", write("bad2", '{"json": ')) == "ran"           # acted alone, check failed
    assert ctx.call("write_file", {"path": "src/c.json", "content": "{bad"}) == "ran"
    s = state(mod, "file:write")
    assert s.faults == 3 and s.tier != mod.rule.T3
    assert ledger(mod, "tier")[-1]["reason"] == "fault"
    assert any("automatic check failed (json syntax error)" in p for p in ctx.posted)


def test_notify_success_adds_an_undo_and_posts(plugin):
    mod, ctx = plugin(FAST)
    climb(ctx, 12)
    assert pre(mod, "write_file", write("n"), "n1") is None
    snap = mod.store_().get_pending("n1")["snap_id"]
    post(mod, "write_file", write("n"), "n1")
    uid = int(re.fullmatch(r"clearance: file:write acted on its own · /clearance undo (\d+)", ctx.posted[-1])[1])
    assert mod.store_().get_undo(uid) == {"id": uid, "agent": A, "type": "file:write", "snap_id": snap,
                                          "at": mod.store_().get_undo(uid)["at"], "undone": False}
    assert outcomes(mod)[-1]["source"] == "notify" and state(mod, "file:write").successes == 13


def test_alone_is_neutral_and_counted_in_stats(plugin):
    mod, ctx = plugin(FAST)
    to_t3(ctx)
    assert ctx.call("write_file", write("alone")) == "ran"
    s = state(mod, "file:write")
    assert (s.successes, s.neutrals) == (4, 1) and outcomes(mod)[-1]["source"] == "alone"
    assert mod.store_().totals(A)["alone"] == 1


def test_blocked_after_our_decision_is_neutral(plugin):
    mod, ctx = plugin(FAST)
    assert ctx.call("write_file", write(), blocked_after=True) == "approved"
    s = state(mod, "file:write")
    assert (s.successes, s.faults, s.neutrals) == (0, 0, 1) and outcomes(mod)[-1]["source"] == "blocked"


def test_outcome_events_have_exact_fields_and_stats_follow(plugin):
    mod, ctx = plugin(FAST)
    climb(ctx, 2)
    ctx.call("write_file", write("r"), answer="deny")
    ctx.call("write_file", write("t"), answer="timeout")
    ctx.call("write_file", write("e"), status="error")
    rows = outcomes(mod)
    assert all(set(e) == OUTCOME_FIELDS for e in rows)
    assert [(e["result"], e["source"]) for e in rows] == [("success", "approval"), ("success", "approval"),
                                                          ("fault", "refusal"), ("neutral", "timeout"),
                                                          ("neutral", "error")]
    assert mod.store_().totals(A) == {"actions": 5, "checked": 3, "alone": 0, "faults": 1}


# -------------------------------------------------------------------------------------------------------- settings
def test_first_settings_are_logged_before_any_outcome(plugin):
    mod, ctx = plugin(FAST)
    ctx.call("write_file", write())
    ctx.call("write_file", write("b"))
    rows = ledger(mod)
    assert rows[0] == {"event": "settings", "risks": {"low": 0.25, "medium": 0.2, "high": None}, "spot": 0.1,
                       "strict": False, "rule": "study-rule-B/1"}
    assert len(ledger(mod, "settings")) == 1


def test_settings_change_is_logged_and_reevaluates_every_agent(plugin):
    mod, ctx = plugin(FAST)
    for s in ("s1", "s1", "s1", "s2", "s2"):
        ctx.call("terminal", NPM, session=s)
    assert state(mod, "shell:npm").tier == mod.rule.T3
    mod.pre_api_request(model="model-b", provider="nous", session_id="s1")
    for s in ("s1", "s1", "s2"):
        ctx.call("terminal", NPM, session=s)
    assert state(mod, "shell:npm", B).tier == mod.rule.T3
    mod.pre_api_request(model="model-a", provider="nous", session_id="s1")
    ctx.settings["risks"] = {"low": 0.25, "medium": 0.05}                 # stricter: 21 in a row
    assert ctx.call("terminal", NPM) == "approved"
    assert ledger(mod, "settings")[-1]["risks"]["medium"] == 0.05
    drops = {(e["agent"], e["type"]) for e in ledger(mod, "tier") if e["reason"] == "settings"}
    assert drops == {(A, "shell:npm"), (B, "shell:npm")}
    assert state(mod, "shell:npm", B).tier == mod.rule.T1


# ---------------------------------------------------------------------------------------------- the wait (R17)
def test_the_wait_counts_executed_actions_only(plugin):
    mod, ctx = plugin(FAST)
    ctx.call("terminal", NPM, answer="deny")                  # medium fault: a trial opens
    ctx.call("terminal", NPM, answer="deny")                  # it fails: wait 50 executed actions
    assert (state(mod, "shell:npm").trial_wait, state(mod, "shell:npm").trial_left) == (50, 0)
    ctx.call("terminal", NPM, answer="timeout")
    ctx.call("terminal", NPM, answer="deny")
    assert state(mod, "shell:npm").trial_wait == 50           # never executed
    ctx.call("terminal", NPM)
    ctx.call("terminal", NPM, status="error")
    assert state(mod, "shell:npm").trial_wait == 48           # executed: a success and a tool failure
    ctx.cron = True
    ctx.call("terminal", NPM)
    ctx.cron = False
    d = pre(mod, "terminal", NPM, "late")
    answer(mod, d, "late", "once")
    age(mod, "late")
    assert state(mod, "shell:npm").trial_wait == 48           # nobody's phase
    ctx.call("terminal", NPM)                                 # the expired ask does not count; this success does
    assert state(mod, "shell:npm").trial_wait == 47
    for _ in range(46):
        ctx.call("terminal", NPM)
    assert (state(mod, "shell:npm").trial_wait, state(mod, "shell:npm").trial_left) == (1, 0)
    ctx.call("terminal", NPM)
    assert (state(mod, "shell:npm").trial_wait, state(mod, "shell:npm").trial_left) == (0, 3)
    assert ledger(mod, "trial")[-1]["reason"] == "wait over"


def test_the_action_failing_the_trial_does_not_count(plugin, tmp_path):
    mod, ctx = plugin(FAST)
    outside = str(tmp_path / "outside" / "m.py")              # file:write-outside: medium stakes
    ctx.call("write_file", {"path": outside, "content": "x = 1\n"}, answer="deny")
    assert state(mod, "file:write-outside").trial_left == 3
    assert ctx.call("write_file", {"path": outside, "content": "def x(:\n"}) == "approved"   # ran, check failed
    assert state(mod, "file:write-outside").trial_wait == 50
    ctx.call("write_file", {"path": outside, "content": "x = 2\n"})
    assert state(mod, "file:write-outside").trial_wait == 49


# ---------------------------------------------------------------------------------------------- named scenarios
def test_one_off_keys_everywhere(plugin):
    mod, ctx = plugin(FAST)
    for i in range(3):                                        # "session" answers: the next ask still reaches you
        assert ctx.call("write_file", write(f"k{i}"), answer="session") == "approved"
    assert len(ctx.prompts) == 3 and state(mod, "file:write").successes == 3
    for _ in range(2):
        assert ctx.call("write_file", {"path": ".env", "content": "K=1"}, answer="always") == "approved"
        assert ctx.call("terminal", {"command": "git push origin main"}, answer="always") == "approved"
    ctx.call("terminal", NPM, answer="deny")
    for _ in range(2):
        assert ctx.call("terminal", NPM, answer="always") == "approved"
    to_t3(ctx, tool="memory")
    mod.ST.rng = Picks([0.0, 0.0])
    for i in range(2):
        assert ctx.call("memory", {"action": "add", "content": f"m{i}"}, answer="always") == "approved"
    keys = [d["rule_key"] for d in ctx.prompts]
    kinds = [re.fullmatch(r"clearance:(ask|spot|cap|capped|trial):(.+):(tc-\d+)", k)[1] for k in keys]
    assert {"ask", "spot", "cap", "capped", "trial"} <= set(kinds)
    assert len(set(keys)) == len(keys) == len(ctx.prompts) == ctx.calls          # every call reached the owner


def test_full_climb_low_reversible_type(plugin):
    mod, ctx = plugin()                                       # balanced: 52 in a row at low stakes
    for i in range(11):
        assert ctx.call("write_file", write(f"a{i}")) == "approved"
    assert state(mod, "file:write").tier == mod.rule.T1
    assert ctx.call("write_file", write("a11")) == "approved"
    assert state(mod, "file:write").tier == mod.rule.T2
    for i in range(20):
        assert ctx.call("write_file", write(f"b{i}"), session="s1") == "ran"
    for i in range(19):
        assert ctx.call("write_file", write(f"c{i}"), session="s2") == "ran"
    assert (state(mod, "file:write").tier, state(mod, "file:write").series) == (mod.rule.T2, 51)
    assert ctx.call("write_file", write("c19"), session="s2") == "ran"
    s = state(mod, "file:write")
    assert (s.tier, s.series, len(s.sessions)) == (mod.rule.T3, 52, 2)
    assert len(os.listdir(os.path.join(mod.data_dir(), "undo"))) == 40       # one snapshot per act-then-notify
    assert sum("/clearance undo" in p for p in ctx.posted) == 40
    assert any("now acts alone" in p for p in ctx.posted)
    assert pre(mod, "write_file", write("next"), "next") is None
    assert mod.store_().get_pending("next")["decision"] in (mod.rule.ALLOW, mod.rule.SPOT)


def test_undo_after_notify_is_a_fault(plugin):
    mod, ctx = plugin(FAST)
    climb(ctx, 12)
    target = os.path.join(ctx.cwd, "src", "u.py")
    with open(target, "w") as f:
        f.write("before = 1\n")
    assert ctx.call("write_file", {"path": "src/u.py", "content": "after = 2\n"}) == "ran"
    uid = int(ctx.posted[-1].rsplit(" ", 1)[1])
    entry = mod.store_().get_undo(uid)
    assert (entry["agent"], entry["type"], entry["undone"]) == (A, "file:write", False) and entry["snap_id"]
    assert mod.undo.restore(entry["snap_id"], mod.data_dir()) == 1
    with open(target) as f:
        assert f.read() == "before = 1\n"
    cfg = mod.settings()
    with mod.txn() as st:
        mod.sync_settings(st, cfg)
        mod.record_outcome(st, cfg, agent=A, type_key="file:write", stakes="low", reversible=True,
                           result="fault", source="undo")
        st.mark_undone(uid)
    s = state(mod, "file:write")
    assert (s.faults, s.series, s.tier) == (1, 0, mod.rule.T1)
    assert mod.store_().get_undo(uid)["undone"] is True
    assert (outcomes(mod)[-1]["result"], outcomes(mod)[-1]["source"]) == ("fault", "undo")


def test_tainted_session_asks_even_cleared_types(plugin):
    mod, ctx = plugin(FAST)
    to_t3(ctx)
    assert ctx.call("write_file", write("x"), session="s1") == "ran"
    ctx.call("web_extract", {"urls": ["https://example.com/page"]}, session="s1")
    assert ctx.call("write_file", write("y"), session="s1") == "approved"
    assert ctx.prompts[-1]["rule_key"].startswith("clearance:ask:file:write:")
    assert "suspended: external content read" in ctx.prompts[-1]["message"]
    assert ctx.call("write_file", write("z"), session="s2") == "ran"        # other sessions keep the tier


def test_ledger_contains_no_paths_or_commands(plugin, tmp_path):
    mod, ctx = plugin(FAST)
    secret_session = "raw-session-id-42"
    ctx.call("write_file", {"path": "src/zz_secret_dir/plan_7f3.py", "content": "x = 1\n"}, session=secret_session)
    ctx.call("write_file", {"path": str(tmp_path / "outside_q9" / "leak.py"), "content": "def x(:\n"})
    ctx.call("terminal", {"command": "npm install left-pad --token=SECRET-TOKEN-123"}, answer="deny")
    ctx.call("web_extract", {"urls": ["https://evil.example/page-xyz"]}, session=secret_session)
    climb(ctx, 12, name="notify_target_")
    ctx.call("write_file", {"path": "src/notified_k2.py", "content": "y = 2\n"})
    mod.cli.slash("flag file:write private note n0te-77")
    rows = json.dumps(mod.store_().ledger())
    dump = "\n".join(mod.store_().db.iterdump())
    for needle in ("zz_secret_dir", "plan_7f3", "outside_q9", "leak.py", "left-pad", "SECRET-TOKEN-123",
                   "evil.example", "page-xyz", secret_session, "notify_target_", "notified_k2", "n0te-77",
                   str(tmp_path), "src/"):
        assert needle not in rows and needle not in dump, needle
    assert anon(secret_session) in rows


# ------------------------------------------------------------------------------------------------- robustness
def test_parallel_tool_calls_share_one_connection_safely(plugin, caplog):
    mod, _ = plugin()
    errors = []

    def worker(t):
        try:
            for i in range(10):
                cid = f"t{t}-{i}"
                d = pre(mod, "terminal", NPM, cid)
                assert d["action"] == "approve" and "internal error" not in d["message"]
                answer(mod, d, cid, "once")
                post(mod, "terminal", NPM, cid, result='{"exit_code": 0}')
        except Exception as e:                                  # reported below
            errors.append(e)
    with caplog.at_level(logging.ERROR, logger="clearance"):
        threads = [threading.Thread(target=worker, args=(t,)) for t in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    assert errors == [] and not [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert state(mod, "shell:npm").successes == 60


def replay(rows, rule, params, store):
    """The ledger contract of ``store``, read back: settings, outcomes, agent changes and revocations only."""
    cfg, states = None, {}
    for row in rows:
        e = row["event"]
        if e["event"] == "settings":
            cfg = e
            for s in states.values():
                rule.reevaluate(s, params.required_n(cfg["risks"], s.stakes))
        elif e["event"] == "outcome":
            s = states.get((e["agent"], e["type"])) or rule.TypeState(key=e["type"], stakes=e["stakes"])
            s.stakes, s.reversible = e["stakes"], e["reversible"]
            n = params.required_n(cfg["risks"], e["stakes"])
            if e["result"] == "neutral":
                events = rule.on_neutral(s, e["source"])
            else:
                fn = rule.on_success if e["result"] == "success" else rule.on_fault
                events = fn(s, n, session=e["session"], source=e["source"])
            failed = any(v["event"] == "trial" and v["reason"] == "failed" for v in events)
            if (e["result"], e["source"]) in store.COUNTED and not failed:
                rule.count_action(s)
            states[(e["agent"], e["type"])] = s
        elif e["event"] == "agent":
            have = {k for (a, k) in states if a == e["new"]}
            for (a, k), s in list(states.items()):
                if a == e["old"] and k not in have:
                    states[(e["new"], k)] = rule.carry_over(s, n_new=params.required_n(cfg["risks"], s.stakes),
                                                            veto=k in e["vetoed"], strict=e["mode"] == "strict")
        elif e["event"] == "revoke":
            rule.revoke(states[(e["agent"], e["type"])])
    return states


def test_ledger_inputs_replay_to_the_live_states(plugin, monkeypatch, tmp_path):
    mod, ctx = plugin(FAST)
    monkeypatch.setattr(mod.benchmarks, "veto", lambda old, new, key, margin=5.0: key == "memory:write")
    climb(ctx, 12)                                                       # file:write to T2
    ctx.call("write_file", write("n1"))                                  # act then notify
    ctx.call("write_file", write("bad", "def x(:\n"))                    # notify, check fails
    to_t3(ctx, tool="memory")
    ctx.call("memory", {"action": "add", "content": "alone"})           # alone
    mod.ST.rng = Picks([0.0, 0.0])
    ctx.call("memory", {"action": "add", "content": "spot ok"})         # spot check approved
    ctx.call("memory", {"action": "add", "content": "spot no"}, answer="deny")
    for verdict in ("deny", "deny", "timeout", "once"):                  # trial, failed trial, the wait
        ctx.call("terminal", NPM, answer=verdict)
    ctx.call("terminal", NPM, status="error")
    ctx.call("write_file", {"path": str(tmp_path / "out" / "o.py"), "content": "x = 1\n"}, blocked_after=True)
    d = pre(mod, "terminal", NPM, "late")
    answer(mod, d, "late", "once")
    age(mod, "late")
    ctx.call("web_extract", {"urls": ["https://example.com"]}, session="s3")
    ctx.call("write_file", write("suspended"), session="s3")            # expires "late", asks while suspended
    ctx.cron = True
    ctx.call("terminal", {"command": "make build"})
    ctx.cron = False
    ctx.settings["risks"] = {"low": 0.25, "medium": 0.1}
    ctx.call("terminal", NPM)
    mod.pre_api_request(model="model-b", provider="nous", session_id="s1")   # carry, memory:write vetoed
    climb(ctx, 2, name="b")
    mod.cli.revoke("file:write", B)
    ctx.settings["strict"] = True
    mod.pre_api_request(model="model-c", provider="nous", session_id="s1")   # strict
    ctx.call("write_file", write("c"), answer="deny")
    mod.cli.flag("memory:write", agent=A)
    live = {(a, s.key): s.to_dict() for a, s in mod.store_().states()}
    replayed = {k: s.to_dict() for k, s in replay(mod.store_().ledger(), mod.rule, mod.params, mod.store).items()}
    for d in list(live.values()) + list(replayed.values()):
        d.pop("changed_at")
    assert set(live) == set(replayed) and len(live) >= 8
    for k in live:
        assert replayed[k] == live[k], k


# ------------------------------------------------------------------------------------------------------- commands
def test_cli_status_flag_and_revoke_on_the_new_record(plugin):
    mod, ctx = plugin(FAST)
    climb(ctx, 3)
    to_t3(ctx, tool="memory")
    text = mod.cli.slash("status")
    assert re.search(r"file:write\s+low\s+T1 ask\s+3/4 in a row, 1 session", text)
    assert re.search(r"memory:write\s+low\s+T3 alone", text) and "chain intact" in text
    out = mod.cli.slash("flag file:write")
    assert "file:write" in out and state(mod, "file:write").faults == 1
    assert (outcomes(mod)[-1]["result"], outcomes(mod)[-1]["source"], outcomes(mod)[-1]["session"]) == (
        "fault", "flag", "")
    assert "memory:write" in mod.cli.slash("revoke all")
    assert state(mod, "memory:write").tier == mod.rule.T1
    assert ledger(mod, "revoke")[-1] == {"event": "revoke", "agent": A, "type": "memory:write"}
    assert mod.cli.slash("flag nothing:here").startswith("No record of nothing:here")
