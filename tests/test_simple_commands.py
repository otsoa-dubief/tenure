"""Three visible commands: ``/tenure`` (what the agent did lately, what can still be undone), ``/tenure undo [N]`` and
``/tenure trust [KIND [ask]]``. Every other command keeps its name, hidden from the help and listed by
``/tenure advanced``. ``trust KIND`` is a person's word, simple mode only, recorded as a ``trust`` ledger event that a
replay reads the same way."""
import argparse
import os
import sys
import time

import pytest

from test_plugin import A, FAST, plugin, state, ledger  # noqa: F401  (plugin is a fixture)
from test_cli import run_line

SIMPLE = {"mode": "simple", **FAST}                       # series length 4 at low stakes, 5 at medium
pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the commands are POSIX")


def make(plugin, settings=None):
    return plugin({**SIMPLE, **(settings or {})})


def last_undo(mod):
    return mod.store_().db.execute("SELECT MAX(id) FROM undo").fetchone()[0]


def stable(s):
    return {**s.to_dict(), "changed_at": 0}


def touch(ctx, name, text="x\n"):
    path = os.path.join(ctx.cwd, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def watched_and_asking(mod, ctx):
    """file:write watched (one fault), shell:npm asking (a flag on an irreversible kind)."""
    ctx.call("write_file", {"path": "src/a.py", "content": "x = 1\n"})
    mod.cli.slash(f"undo {last_undo(mod)}")
    ctx.call("terminal", {"command": "npm test"})
    mod.cli.slash("flag shell:npm")


def live_is_replay(mod):
    st = mod.store_()
    replayed = mod.passport.replay(st.ledger())[A]
    assert {s.key: stable(s) for _, s in st.states(A)} == {k: stable(s) for k, s in replayed.items()}


# --------------------------------------------------------------------------------------------- /tenure
def test_home_lists_what_can_be_undone_newest_first(plugin):
    mod, ctx = make(plugin)
    touch(ctx, "notes.txt")
    ctx.call("write_file", {"path": "src/a.py", "content": "x = 1\n"})
    ctx.call("terminal", {"command": "rm notes.txt"})
    ctx.call("terminal", {"command": "echo token=ghp_abcdefghijklmnopqrstuvwxyz0123456789 > out.txt"})
    out = mod.cli.slash("")
    assert out.startswith("tenure · what the agent did lately")
    rows = [ln for ln in out.splitlines() if ln.startswith("  ") and ln.strip()[:1].isdigit()]
    ids = [int(ln.split()[0]) for ln in rows]
    assert ids == sorted(ids, reverse=True) and len(ids) >= 2
    assert "src/a.py" in out and "rm notes.txt" in out
    assert "ghp_abcdef" not in out                                         # masked as in the end-of-turn line
    assert "Ran without asking today: " in out
    assert out.splitlines()[-1] == "/tenure undo N · /tenure trust"
    assert "watched" not in out.lower().split("today")[1] and "Asks you first" not in out   # nothing held back


def test_home_shows_at_most_ten_and_says_how_many_more(plugin):
    mod, ctx = make(plugin)
    for i in range(12):
        ctx.call("write_file", {"path": f"src/f{i}.py", "content": "x = 1\n"})
    out = mod.cli.slash("")
    rows = [ln for ln in out.splitlines() if ln.startswith("  ") and ln.strip()[:1].isdigit()]
    assert len(rows) == 10 and "and 2 more: /tenure undo" in out
    assert "Ran without asking today: 12 actions." in out


def test_home_names_the_kinds_watched_or_asking(plugin):
    mod, ctx = make(plugin)
    watched_and_asking(mod, ctx)
    out = mod.cli.slash("")
    assert "Watched after a mistake (each action shown to you, with an undo): file:write." in out
    assert "Asks you first: shell:npm." in out
    assert "file:write" in out.split("Watched")[0] or "Nothing left to undo" in out


def test_home_from_the_terminal_says_hermes_tenure(plugin):
    mod, ctx = make(plugin)
    out, code = run_line(mod, "")
    assert code == 0 and out.splitlines()[-1] == "hermes tenure undo N · hermes tenure trust"


def test_home_in_study_mode_keeps_the_status(plugin):
    mod, ctx = plugin({"mode": "study", **FAST})
    ctx.call("write_file", {"path": "src/a.py", "content": "x = 1\n"})
    assert mod.cli.slash("") == mod.cli.slash("status")
    out, code = run_line(mod, "")
    assert code == 0 and out == mod.cli.status_text()


# ----------------------------------------------------------------------------------------------- undo
def test_undo_is_unchanged(plugin):
    mod, ctx = make(plugin)
    ctx.call("write_file", {"path": "src/a.py", "content": "x = 1\n"})
    assert "src/a.py" in mod.cli.slash("undo")                              # alone: the list, as before
    out = mod.cli.slash(f"undo {last_undo(mod)}")
    assert not os.path.exists(os.path.join(ctx.cwd, "src/a.py")) and "watched" in out


# ---------------------------------------------------------------------------------------------- trust
def test_trust_lists_what_is_not_free_and_what_brings_it_back(plugin):
    mod, ctx = make(plugin)
    assert mod.cli.slash("trust") == f"Every kind of action {A} used is free."
    watched_and_asking(mod, ctx)
    ctx.call("terminal", {"command": "git push origin main"})
    ctx.call("terminal", {"command": "pip install requests"})
    out = mod.cli.slash("trust")
    lines = {ln.split()[0]: ln for ln in out.splitlines() if ln.startswith("  ")}
    assert "watched after a mistake: free again after 4 more actions you do not undo" in lines["file:write"]
    assert "asks you first: free again after 5 more approvals in a row" in lines["shell:npm"]   # medium
    assert "always asks: it leaves your machine" in lines["shell:git:push"]
    assert "file:write" in out and "/tenure trust <kind>" in out and "<kind> ask" in out
    assert not any(k.startswith("file:") and k != "file:write" for k in lines)   # free kinds are not listed


def test_trust_kind_frees_it_now_and_a_new_mistake_watches_it_again(plugin):
    mod, ctx = make(plugin)
    watched_and_asking(mod, ctx)
    out = mod.cli.slash("trust shell:npm")
    assert out == "shell:npm is free again, on your word. A new mistake makes it watched again."
    s = state(mod, "shell:npm")
    assert s.tier == mod.rule.T3 and mod.trusted(mod.settings(), s, 5, "medium") and s.faults == 1
    assert ctx.call("terminal", {"command": "npm test"}) == "ran"
    assert ledger(mod, "trust")[-1] == {"event": "trust", "agent": A, "type": "shell:npm", "to": "free"}
    assert mod.cli.slash("trust shell:npm") == "shell:npm is already free."
    mod.cli.slash("trust file:write")
    ctx.call("write_file", {"path": "src/b.py", "content": "x = 1\n"})
    mod.cli.slash(f"undo {last_undo(mod)}")
    assert state(mod, "file:write").tier == mod.rule.T2                     # watched again, as a first mistake
    live_is_replay(mod)


def test_trust_kind_ask_pins_it_until_freed(plugin):
    mod, ctx = make(plugin)
    ctx.call("write_file", {"path": "src/a.py", "content": "x = 1\n"})        # never faulted: free
    out = mod.cli.slash("trust file:write ask")
    assert out == "file:write now asks you first, every time, until you free it: /tenure trust file:write"
    for i in range(6):                                                       # approvals never free it
        assert ctx.call("write_file", {"path": f"src/w{i}.py", "content": "x = 1\n"}) == "approved"
    assert "as you chose: /tenure trust file:write frees it" in ctx.prompts[-1]["message"]
    s = state(mod, "file:write")
    assert s.pinned and s.tier == mod.rule.T1 and s.series == 0 and s.successes >= 6
    assert "asks you first, your choice" in mod.cli.slash("trust")
    assert "Asks you first: file:write." in mod.cli.slash("")
    assert "already asks you first" in mod.cli.slash("trust file:write ask")
    live_is_replay(mod)
    mod.cli.slash("trust file:write")
    assert not state(mod, "file:write").pinned
    assert ctx.call("write_file", {"path": "src/z.py", "content": "x = 1\n"}) == "ran"
    live_is_replay(mod)


@pytest.mark.parametrize("command,why", [("git push origin main", "leaves your machine"),
                                         ("pip install requests", "leaves your machine")])
def test_trust_refuses_what_leaves_the_machine(plugin, command, why):
    mod, ctx = make(plugin)
    ctx.call("terminal", {"command": command})
    key = next(s.key for _, s in mod.store_().states(A))
    before = len(mod.store_().ledger())
    out = mod.cli.slash(f"trust {key}")
    assert why in out and "cannot be freed by hand" in out
    assert len(mod.store_().ledger()) == before


def test_trust_refuses_high_stakes_and_capped_kinds(plugin):
    mod, ctx = make(plugin, {"types": {"file:write": "high"}})
    ctx.call("write_file", {"path": "src/a.py", "content": "x = 1\n"})
    out = mod.cli.slash("trust file:write")
    assert "high stakes" in out and "cannot be freed by hand" in out
    mod, ctx = make(plugin, {"risks": {"low": "cap", "medium": 0.2}})
    ctx.call("write_file", {"path": "src/a.py", "content": "x = 1\n"})
    out = mod.cli.slash("trust file:write")
    assert "capped by your settings" in out and "/tenure setup" in out
    assert not ledger(mod, "trust")


def test_trust_an_unknown_kind(plugin):
    mod, ctx = make(plugin)
    watched_and_asking(mod, ctx)
    out = mod.cli.slash("trust shell:nope")
    assert "No record of shell:nope" in out and "file:write" in out and not ledger(mod, "trust")


# ------------------------------------------------------------------------------------ a person's word only
def test_trust_refuses_a_child_of_the_agents_tools(plugin, monkeypatch):
    mod, ctx = make(plugin)
    watched_and_asking(mod, ctx)
    monkeypatch.setenv("TENURE_AGENT_CHILD", "1")
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    for line in ("trust shell:npm", "trust shell:npm ask"):
        out, code = run_line(mod, line)
        assert code != 0 and "only you" in out
    assert not ledger(mod, "trust")


def test_trust_refuses_a_script(plugin, monkeypatch):
    mod, ctx = make(plugin)
    watched_and_asking(mod, ctx)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    out, code = run_line(mod, "trust shell:npm")
    assert code != 0 and "a person's word" in out and "/tenure trust shell:npm" in out
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    out, code = run_line(mod, "trust shell:npm")
    assert code == 0 and "free again" in out


def test_the_list_is_read_only_and_open_to_scripts(plugin, monkeypatch):
    mod, ctx = make(plugin)
    watched_and_asking(mod, ctx)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    out, code = run_line(mod, "trust")
    assert code == 0 and "shell:npm" in out


@pytest.mark.parametrize("how", ["cron", "yolo"])
def test_trust_refuses_while_nobody_answers(plugin, monkeypatch, how):
    mod, ctx = make(plugin, None)
    watched_and_asking(mod, ctx)
    if how == "cron":
        ctx.cron = True
    else:
        monkeypatch.setenv("HERMES_YOLO_MODE", "1")
    out = mod.cli.slash("trust shell:npm")
    assert "only a person can free a kind" in out and not ledger(mod, "trust")
    with mod.txn() as st:                                   # the function itself refuses too
        with pytest.raises(ValueError):
            mod.owner_trust(st, mod.settings(), A, state(mod, "shell:npm"), mod.rule.FREE)


@pytest.mark.parametrize("command", ["hermes tenure trust shell:npm", "/tenure trust file:write ask",
                                     "python -c 'from tenure import owner_trust'", "hermes tenure trust"])
def test_the_agent_never_runs_trust(plugin, command):
    mod, ctx = make(plugin)
    d = mod.pre_tool_call(tool_name="terminal", args={"command": command}, session_id="s1", tool_call_id="c1")
    assert isinstance(d, dict) and d.get("action") == "block"


# ---------------------------------------------------------------------------------------- study mode
def test_study_mode_lists_but_does_not_free_by_hand(plugin):
    mod, ctx = plugin({"mode": "study", **FAST})
    ctx.call("write_file", {"path": "src/a.py", "content": "x = 1\n"}, answer="once")
    out = mod.cli.slash("trust")
    assert "file:write" in out and "verified successes before acting alone" in out
    assert "belongs to simple mode (/tenure mode simple)" in out
    out = mod.cli.slash("trust file:write")
    assert "belongs to simple mode" in out and not ledger(mod, "trust")
    assert "belongs to simple mode" in mod.cli.slash("trust file:write ask")


def test_the_study_replay_reads_nothing_from_trust_events(plugin):
    mod, ctx = make(plugin)
    watched_and_asking(mod, ctx)
    rows = mod.store_().ledger()
    study_before, _ = mod.passport._replay(rows, mod.rule.STUDY)
    mod.cli.slash("trust shell:npm")
    mod.cli.slash("trust file:write ask")
    study_after, _ = mod.passport._replay(mod.store_().ledger(), mod.rule.STUDY)
    assert {k: stable(s) for k, s in study_before.items()} == {k: stable(s) for k, s in study_after.items()}


# ------------------------------------------------------------------------------------------ replay
def test_the_owner_events_replay_deterministically_across_modes(plugin):
    mod, ctx = make(plugin)
    watched_and_asking(mod, ctx)
    mod.cli.slash("trust shell:npm")
    mod.cli.slash("trust file:write ask")
    ctx.call("write_file", {"path": "src/b.py", "content": "x = 1\n"})
    ctx.call("terminal", {"command": "npm test"})
    live_is_replay(mod)
    simple_states = {s.key: stable(s) for _, s in mod.store_().states(A)}
    assert simple_states["file:write"]["pinned"] and simple_states["shell:npm"]["tier"] == mod.rule.T3
    mod.cli.slash("mode study")
    assert not any(s.pinned for _, s in mod.store_().states(A))             # the study rule knows no pin
    live_is_replay(mod)
    mod.cli.slash("mode simple")
    assert {s.key: stable(s) for _, s in mod.store_().states(A)} == simple_states
    live_is_replay(mod)


def test_a_new_model_keeps_the_pin(plugin):
    mod, ctx = make(plugin)
    ctx.call("write_file", {"path": "src/a.py", "content": "x = 1\n"})
    mod.cli.slash("trust file:write ask")
    mod.pre_api_request(model="model-b", provider="nous", session_id="s1")
    assert state(mod, "file:write", "model-b@nous").pinned
    assert ctx.call("write_file", {"path": "src/b.py", "content": "x = 1\n"}) == "approved"
    st = mod.store_()
    replayed = mod.passport.replay(st.ledger())
    for agent in (A, "model-b@nous"):
        assert {s.key: stable(s) for _, s in st.states(agent)} == {k: stable(s) for k, s in
                                                                   replayed[agent].items()}


def test_a_replay_refuses_a_bad_trust_event(plugin):
    mod, ctx = make(plugin)
    ctx.call("write_file", {"path": "src/a.py", "content": "x = 1\n"})
    rows = mod.store_().ledger()
    head = rows[-1]
    for event in ({"event": "trust", "agent": A, "type": "file:nope", "to": "free"},
                  {"event": "trust", "agent": A, "type": "file:write", "to": "maybe"}):
        with pytest.raises(ValueError):
            mod.passport._replay_rows(rows + [{"seq": head["seq"] + 1, "at": time.time(), "event": event}])


# ------------------------------------------------------------------------------------------- help
def test_the_chat_help_shows_three_commands(plugin):
    mod, ctx = make(plugin)
    for arg in ("help", "--help", "-h"):
        out = mod.cli.slash(arg)
        lines = out.splitlines()
        assert len(lines) == 4 and lines[-1] == "More: /tenure advanced"
        assert [ln.split()[:2] for ln in lines[:3]] == [["/tenure", "what"], ["/tenure", "undo"],
                                                        ["/tenure", "trust"]]
        for hidden in ("status", "passport", "flag", "revoke", "mode", "explain"):
            assert hidden not in out


def test_hermes_tenure_help_shows_three_commands(plugin):
    mod, ctx = make(plugin)
    setup_fn, handler = ctx.cli["tenure"]
    root = argparse.ArgumentParser(prog="hermes")
    tenure = root.add_subparsers().add_parser("tenure", help="tenure")
    setup_fn(tenure)
    out = tenure.format_help()
    assert "hermes tenure undo [N]" in out and "hermes tenure trust [KIND]" in out
    assert "More: hermes tenure advanced" in out
    for hidden in ("status", "passport", "flag", "revoke", "explain", "cleanup", "{"):
        assert hidden not in out, hidden
    for line in ("status", "passport", "flag 3", "revoke all", "week", "mode study", "advanced", "trust", ""):
        root.parse_args(["tenure", *line.split()])                           # every name still parses


def test_advanced_lists_every_other_command_one_line_each(plugin):
    mod, ctx = make(plugin)
    out = mod.cli.slash("advanced")
    first, *lines = out.splitlines()
    assert first.startswith("Every other command") and "/tenure <command>" in first
    names = {ln.split()[0] for ln in lines}
    assert names == {"status", "card", "setup", "explain", "models", "flag", "revoke", "passport", "verify",
                     "anchor", "export", "start", "strict", "mode", "cleanup", "share", "week", "ok", "excuse"}
    assert "undo" not in names and "trust" not in names


@pytest.mark.parametrize("line", ["status", "explain", "week", "setup", "models", "flag", "ok", "excuse",
                                  "card", "cleanup", "anchor", "mode simple"])
def test_old_command_names_still_work(plugin, line):
    mod, ctx = make(plugin)
    ctx.call("write_file", {"path": "src/a.py", "content": "x = 1\n"})
    out = mod.cli.slash(line)
    assert "invalid choice" not in out and "More: /tenure advanced" not in out and not out.startswith("tenure: argument")


def test_the_new_messages_have_every_language():
    import json
    from tenure import i18n
    en = json.load(open(os.path.join(i18n.LOCALES_DIR, "en", "core.json"), encoding="utf-8"))
    keys = [k for k in en if k.startswith(("home.", "trust.", "cli.help", "cli.advanced"))]
    assert len(keys) > 25
    for lang in ("fr", "es", "zh", "ar"):
        tr = json.load(open(os.path.join(i18n.LOCALES_DIR, lang, "core.json"), encoding="utf-8"))
        assert all(k in tr and tr[k] != en[k] for k in keys), lang
        assert "{prefix} advanced" in tr["cli.help"] and "{prefix} trust [KIND]" in tr["cli.help"]


def test_after_install_tells_the_simple_story():
    from tenure import i18n
    text = open(os.path.join(os.path.dirname(i18n.__file__), "after-install.md"), encoding="utf-8").read()
    for needle in ("24 hours", "watched", "asks you first", "`/tenure`", "`/tenure undo N`", "`/tenure trust`",
                   "/tenure mode study", "/tenure advanced"):
        assert needle in text, needle
    assert len(text.splitlines()) <= 20


# ------------------------------------------------------------- the numbers trust gives, against the state machine
def credit_all(mod):
    """Every open act-then-tell action past its undo window, as if a day went by: each counts as not undone."""
    cfg = mod.settings()
    with mod.txn() as st:
        return mod._credit_due(st, cfg, now=time.time() + mod.UNDO_WINDOW + 1)


def trust_line(mod, key):
    return next(ln for ln in mod.cli.slash("trust").splitlines() if ln.startswith(f"  {key} "))


def numbers(line):
    import re
    return [int(x) for x in re.findall(r"after (\d+) more", line)]


def is_free(mod, key):
    s = state(mod, key)
    return mod.trusted(mod.settings(), s, mod.params.required_n(mod.settings()["risks"], s.stakes), s.stakes)


def test_trust_ask_line_of_a_reversible_kind_gives_the_real_next_steps(plugin):
    mod, ctx = make(plugin, {"risks": {"low": "1/50", "medium": "1/100"}})       # n = 52: the score decides first
    for i in range(2):                                                            # two mistakes: it asks first
        ctx.call("write_file", {"path": "src/a.py", "content": f"x = {i}\n"})
        mod.cli.slash(f"undo {last_undo(mod)}")
    line = trust_line(mod, "file:write")
    assert "asks you first: watched again after" in line and "(then free after" in line
    n_approvals, m_unseen = numbers(line)
    assert n_approvals == mod._to_t2(state(mod, "file:write")) and n_approvals + m_unseen == 52
    for i in range(n_approvals - 1):
        assert ctx.call("write_file", {"path": f"src/b{i}.py", "content": "x = 1\n"}) == "approved"
    assert state(mod, "file:write").tier == mod.rule.T1                          # not one approval early
    assert ctx.call("write_file", {"path": "src/b.py", "content": "x = 1\n"}) == "approved"
    s = state(mod, "file:write")
    assert mod.rule.decide(s, 52, 0.1, suspended=False, rng=None, mode="simple") == mod.rule.NOTIFY
    assert "watched after a mistake: free again after %d more actions" % m_unseen in trust_line(mod, "file:write")
    before = len(ctx.prompts)
    for i in range(m_unseen - 1):
        assert ctx.call("write_file", {"path": f"src/w{i}.py", "content": "x = 1\n"}) == "ran"
    credit_all(mod)
    assert not is_free(mod, "file:write")                                         # not one action early
    ctx.call("write_file", {"path": "src/w.py", "content": "x = 1\n"})
    credit_all(mod)
    assert is_free(mod, "file:write") and len(ctx.prompts) == before              # no question on the way


def test_trust_watched_line_gives_the_real_count(plugin):
    mod, ctx = make(plugin)
    ctx.call("write_file", {"path": "src/a.py", "content": "x = 1\n"})
    mod.cli.slash(f"undo {last_undo(mod)}")                                       # one mistake: watched
    (m_unseen,) = numbers(trust_line(mod, "file:write"))
    assert m_unseen == 4
    for i in range(m_unseen - 1):
        ctx.call("write_file", {"path": f"src/w{i}.py", "content": "x = 1\n"})
    credit_all(mod)
    assert not is_free(mod, "file:write") and numbers(trust_line(mod, "file:write")) == [1]
    ctx.call("write_file", {"path": "src/w.py", "content": "x = 1\n"})
    credit_all(mod)
    assert is_free(mod, "file:write")


def test_trust_ask_line_of_an_irreversible_kind_counts_approvals_to_free(plugin):
    mod, ctx = make(plugin)
    ctx.call("terminal", {"command": "npm test"})
    mod.cli.slash("flag shell:npm")                                               # no undo: it asks, never watched
    line = trust_line(mod, "shell:npm")
    assert "asks you first: free again after" in line and "watched" not in line
    (n_approvals,) = numbers(line)
    assert n_approvals == 5                                                       # medium stakes, FAST
    for _ in range(n_approvals - 1):
        assert ctx.call("terminal", {"command": "npm test"}) == "approved"
    assert not is_free(mod, "shell:npm") and state(mod, "shell:npm").tier == mod.rule.T1
    assert ctx.call("terminal", {"command": "npm test"}) == "approved"
    assert is_free(mod, "shell:npm") and ctx.call("terminal", {"command": "npm test"}) == "ran"
