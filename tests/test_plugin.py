"""The plugin inside Hermes, with a fake plugin context: asks, counts the owner's answers, clears, revokes."""
import importlib
import os

import pytest

PKG = "clearance"


class FakeCtx:
    def __init__(self, settings=None, cron=False, cwd="/home/me/project"):
        self.settings = dict(settings or {})
        self.posted = []
        self.cron = cron
        self.cwd = cwd
        self.hooks, self.commands, self.cli = {}, {}, {}

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


class Picks:
    """Deterministic draws for spot checks: 0.99 = no check, 0.0 = check."""
    def __init__(self, values=None):
        self.values = list(values or [])

    def random(self):
        return self.values.pop(0) if self.values else 0.99


@pytest.fixture
def plugin(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    for v in ("HERMES_YOLO_MODE",):
        monkeypatch.delenv(v, raising=False)
    mod = importlib.import_module(PKG)
    mod = importlib.reload(mod)

    def make(settings=None, **kw):
        ctx = FakeCtx({"risks": {"low": 0.25, "medium": 0.2}, **(settings or {})}, **kw)
        mod.register(ctx)
        mod.ST.rng = Picks()
        mod.pre_api_request(model="model-a", provider="nous", session_id="s1")
        return mod, ctx
    return make


def ask(mod, tool, args, call):
    return mod.pre_tool_call(tool_name=tool, args=args, session_id="s1", tool_call_id=call)


def answer(mod, decision, call, choice):
    return mod.post_approval_response(pattern_key=f"plugin_rule:{decision['rule_key']}", tool_call_id=call,
                                      choice=choice, surface="cli", session_key="s1")


def test_registers_hooks_and_commands(plugin):
    mod, ctx = plugin()
    assert {"pre_tool_call", "post_approval_response", "pre_api_request"} <= set(ctx.hooks)
    assert "clearance" in ctx.commands and "clearance" in ctx.cli


def test_reads_never_ask(plugin):
    mod, _ = plugin()
    assert ask(mod, "read_file", {"path": "a.py"}, "c0") is None
    assert ask(mod, "terminal", {"command": "git status"}, "c1") is None


def test_asks_counts_and_clears(plugin):
    mod, ctx = plugin()
    i = mod.params.clearance_number(0.25, 0.1)
    for n in range(i):
        d = ask(mod, "write_file", {"path": "src/a.py"}, f"c{n}")
        assert d["action"] == "approve" and d["rule_key"].startswith("clearance:file:write:")
        assert d["rule_key"].endswith(":g0")
        assert f"{n}/{i}" in d["message"]
        answer(mod, d, f"c{n}", "once")
    assert ask(mod, "write_file", {"path": "src/b.py"}, "next") is None          # cleared: acts alone
    assert any("file:write" in p and "cleared" in p for p in ctx.posted)


def test_refusal_resets_and_a_refused_spot_check_revokes(plugin):
    mod, ctx = plugin()
    i = mod.params.clearance_number(0.2, 0.1)
    d = ask(mod, "terminal", {"command": "npm test"}, "x")
    answer(mod, d, "x", "deny")
    s = mod.type_state("model-a", "shell:npm", "medium")
    assert s.streak == 0 and s.lengthened
    for n in range(mod.rule.required(s, i)):
        d = ask(mod, "terminal", {"command": "npm test"}, f"c{n}")
        answer(mod, d, f"c{n}", "once")
    mod.ST.rng = Picks([0.0])                                                    # next action is spot-checked
    d = ask(mod, "terminal", {"command": "npm run build"}, "spot")
    assert d["action"] == "approve" and d["rule_key"].startswith("clearance:spot:shell:npm:")
    assert "spot check" in d["message"]
    answer(mod, d, "spot", "deny")
    d = ask(mod, "terminal", {"command": "npm test"}, "after")
    assert d["action"] == "approve" and d["rule_key"].endswith(":g1")             # new generation
    assert any("revoked" in p for p in ctx.posted)


def test_always_is_a_manual_clearance_until_the_next_refusal(plugin):
    mod, _ = plugin()
    d = ask(mod, "write_file", {"path": "a.py"}, "c1")
    answer(mod, d, "c1", "always")
    s = mod.type_state("model-a", "file:write", "low")
    assert s.level == mod.rule.CLEARED and s.manual


def test_timeouts_and_model_answers_count_for_nothing(plugin):
    mod, _ = plugin()
    for n, choice in enumerate(["timeout", "cancelled", "smart_approve"]):
        d = ask(mod, "write_file", {"path": "a.py"}, f"c{n}")
        answer(mod, d, f"c{n}", choice)
    assert mod.type_state("model-a", "file:write", "low").approvals == 0


def test_capped_actions_always_ask_with_a_one_off_key(plugin):
    mod, _ = plugin()
    d1 = ask(mod, "write_file", {"path": ".env"}, "c1")
    d2 = ask(mod, "write_file", {"path": ".env"}, "c2")
    assert d1["action"] == "approve" and d1["rule_key"] != d2["rule_key"] and "always asked" in d1["message"]


def test_high_stakes_capped_by_the_preset_still_build_a_record(plugin):
    mod, _ = plugin({"risks": {"low": 0.25, "medium": 0.2, "high": None}})
    for n in range(60):
        d = ask(mod, "terminal", {"command": "git push"}, f"c{n}")
        assert d["action"] == "approve"
        answer(mod, d, f"c{n}", "once")
    s = mod.type_state("model-a", "shell:git:push", "high")
    assert s.level == mod.rule.ASK and s.approvals == 60


def test_a_new_model_has_its_own_record(plugin):
    mod, ctx = plugin({"risks": {"low": 0.5, "medium": 0.2}})
    i = mod.params.clearance_number(0.5, 0.1)
    for n in range(i):
        d = ask(mod, "write_file", {"path": "a.py"}, f"c{n}")
        answer(mod, d, f"c{n}", "once")
    assert ask(mod, "write_file", {"path": "a.py"}, "z") is None
    key_a = ask(mod, "terminal", {"command": "npm test"}, "ka")["rule_key"]
    mod.pre_api_request(model="model-b", provider="nous", session_id="s1")
    assert ask(mod, "write_file", {"path": "a.py"}, "y")["action"] == "approve"
    assert any("model-b" in p for p in ctx.posted)
    key_b = ask(mod, "terminal", {"command": "npm test"}, "kb")["rule_key"]
    assert key_a != key_b        # Hermes' "always" for one model's type must not carry over to the next model


def test_nobody_to_answer_cleared_types_run_and_others_fall_to_hermes(plugin, monkeypatch):
    mod, ctx = plugin({"risks": {"low": 0.5, "medium": 0.2}}, cron=True)
    d = ask(mod, "write_file", {"path": "a.py"}, "c1")
    assert d["action"] == "approve"                       # Hermes' cron_mode decides (deny by default)
    answer(mod, d, "c1", "deny")                          # an automatic denial is not the owner's
    assert mod.type_state("model-a", "file:write", "low").refusals == 0


def test_yolo_pauses_learning(plugin, monkeypatch):
    mod, _ = plugin()
    monkeypatch.setenv("HERMES_YOLO_MODE", "1")
    d = ask(mod, "write_file", {"path": "a.py"}, "c1")
    answer(mod, d, "c1", "once")
    assert mod.type_state("model-a", "file:write", "low").approvals == 0


def test_internal_error_asks_rather_than_lets_through(plugin, monkeypatch):
    mod, _ = plugin()
    monkeypatch.setattr(mod.classify, "classify", lambda *a, **k: 1 / 0)
    d = ask(mod, "write_file", {"path": "a.py"}, "c1")
    assert d["action"] == "approve" and "internal error" in d["message"]


def test_ledger_records_outcomes_without_contents(plugin):
    mod, _ = plugin()
    d = ask(mod, "terminal", {"command": "npm install left-pad --token=SECRET"}, "c1")
    answer(mod, d, "c1", "once")
    rows = mod.store_().ledger()
    assert rows and rows[-1]["event"]["event"] == "approved" and "SECRET" not in str(rows)
