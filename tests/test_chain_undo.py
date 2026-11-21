"""Simple mode: chained lines. Real agents join their commands (`git rm ... && rm -rf build && git mv ... && sed -i
...`, `rm -rf tmp && python3 -m unittest ... | tail -40`). A line whose every segment is free on its own or a file
command whose targets can all be saved runs with one undo holding them all; anything else keeps today's question."""
import json
import os
import subprocess
import sys

import pytest

from test_plugin import A, FAST, plugin, pre, post, state  # noqa: F401  (plugin is a fixture)

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the commands are POSIX")

SIMPLE = {"mode": "simple", **FAST}
SED = "sed -i '' " if sys.platform == "darwin" else "sed -i "      # BSD sed takes the suffix as the next word
REPORT = "from inventory.textutil import shout\n\nprint(shout('ok'))\n"
FIRST = ("git rm -rq build app.log debug.log && rm -rf build && git mv inventory/textutil.py inventory/text.py && "
         + SED + "'s/textutil/text/g' inventory/report.py")
SECOND = "rm -rf tmp notes.bak && python3 -m unittest discover -s tests -v 2>&1 | tail -40"
ENV = {**os.environ, "PATH": os.path.dirname(sys.executable) + os.pathsep + os.environ.get("PATH", ""),
       "GIT_CONFIG_NOSYSTEM": "1"}


def make(plugin, settings=None):
    mod, ctx = plugin({**SIMPLE, **(settings or {})})
    return mod, ctx


def touch(ctx, name, text="x\n"):
    path = os.path.join(ctx.cwd, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def read(ctx, name):
    with open(os.path.join(ctx.cwd, name)) as f:
        return f.read()


def git(ctx, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args], cwd=ctx.cwd, check=True,
                   capture_output=True, env=ENV)


def project(ctx, repo=True):
    """The fixture project of the real run: build/, two logs, tmp/, notes.bak, inventory/, tests/."""
    files = {"build/out.txt": "built\n", "build/sub/more.txt": "more\n", "app.log": "app\n", "debug.log": "debug\n",
             "tmp/scratch.txt": "scratch\n", "notes.bak": "notes\n",
             "inventory/__init__.py": "", "inventory/textutil.py": "def shout(s):\n    return s.upper()\n",
             "inventory/report.py": REPORT,
             "tests/test_inventory.py": "import unittest\n\n\nclass T(unittest.TestCase):\n"
                                        "    def test_ok(self):\n        self.assertTrue(True)\n"}
    for name, text in files.items():
        touch(ctx, name, text)
    if repo:
        git(ctx, "init", "-q")
        git(ctx, "add", "-A")
        git(ctx, "commit", "-qm", "start")
    return files


def last_undo(mod):
    return mod.store_().db.execute("SELECT MAX(id) FROM undo").fetchone()[0]


def run(mod, ctx, command, call):
    """pre_tool_call lets it run (no question), the shell runs it in the project, then post_tool_call."""
    args = {"command": command}
    assert pre(mod, "terminal", args, call) is None
    r = subprocess.run(["bash", "-c", command], cwd=ctx.cwd, capture_output=True, text=True, env=ENV)
    post(mod, "terminal", args, call, status="ok" if r.returncode == 0 else "error",
         result=json.dumps({"output": r.stdout + r.stderr, "exit_code": r.returncode}))
    return r


def kind(mod, ctx, command):
    act = mod.classify.classify("terminal", {"command": command}, cwd=ctx.cwd, wide=True)
    return act.type, act.stakes, act.reversible


# --------------------------------------------------------------------------------------- the two real lines
def test_the_first_real_line_runs_free_and_one_undo_puts_it_all_back(plugin):
    mod, ctx = make(plugin)
    files = project(ctx)
    assert kind(mod, ctx, FIRST) == ("file:shell:rm", "low", True)
    r = run(mod, ctx, FIRST, "c1")
    assert r.returncode == 0, r.stderr
    assert not os.path.exists(os.path.join(ctx.cwd, "build")) and not os.path.exists(os.path.join(ctx.cwd, "app.log"))
    assert "inventory.text " in read(ctx, "inventory/report.py") and os.path.exists(os.path.join(ctx.cwd,
                                                                                                  "inventory/text.py"))
    assert ctx.prompts == []
    out = mod.cli.slash(f"undo {last_undo(mod)}")
    for name in ("build/out.txt", "build/sub/more.txt", "app.log", "debug.log", "inventory/textutil.py"):
        assert read(ctx, name) == files[name], out
    assert read(ctx, "inventory/report.py") == REPORT                  # the content before sed
    assert not os.path.exists(os.path.join(ctx.cwd, "inventory/text.py"))   # what the move created is taken back
    assert status(ctx) == "", status(ctx)                              # git's index too: the state before the line
    assert "index" not in out


def status(ctx):
    return subprocess.run(["git", "status", "--porcelain"], cwd=ctx.cwd, capture_output=True, text=True,
                          env=ENV, check=True).stdout


def test_the_index_comes_back_as_it_was_even_with_a_change_staged_before_the_line(plugin):
    mod, ctx = make(plugin)
    project(ctx)
    touch(ctx, "inventory/textutil.py", "def shout(s):\n    return s.upper() + '!'\n")
    git(ctx, "add", "inventory/textutil.py")                          # staged, not committed
    touch(ctx, "notes.bak", "notes, changed\n")                       # changed, not staged
    before = status(ctx)
    assert before == "M  inventory/textutil.py\n M notes.bak\n"
    line = "git rm -q app.log && git mv inventory/textutil.py inventory/text.py && rm -rf tmp notes.bak"
    assert run(mod, ctx, line, "c1").returncode == 0
    assert status(ctx) != before
    mod.cli.slash(f"undo {last_undo(mod)}")
    assert status(ctx) == before and read(ctx, "notes.bak") == "notes, changed\n"


def test_when_git_cannot_put_its_index_back_the_undo_says_so_and_the_files_stay_restored(plugin):
    mod, ctx = make(plugin)
    files = project(ctx)
    assert run(mod, ctx, FIRST, "c1").returncode == 0
    touch(ctx, ".git/index.lock", "")                                 # another git holds the index
    out = mod.cli.slash(f"undo {last_undo(mod)}")
    assert "index was not put back" in out and "index.lock" in out
    assert len([ln for ln in out.splitlines() if "index" in ln]) == 1
    for name in ("build/out.txt", "app.log", "inventory/textutil.py"):
        assert read(ctx, name) == files[name]


def test_a_chained_line_is_read_once_per_hook_call(plugin, monkeypatch):
    mod, ctx = make(plugin)
    project(ctx)
    seen = []
    real = mod.classify._read_chain
    monkeypatch.setattr(mod.classify, "_read_chain", lambda *a: seen.append(a[0]) or real(*a))
    args = {"command": SECOND}
    assert pre(mod, "terminal", args, "c1") is None
    assert len(seen) == 1
    post(mod, "terminal", args, "c1")
    assert len(seen) == 2                                             # read afresh after it ran, once


def test_a_refused_segment_walks_no_folder(plugin, monkeypatch):
    mod, ctx = make(plugin)
    project(ctx, repo=False)
    walked = []
    monkeypatch.setattr(mod.classify, "_undo_tree", lambda folder: walked.append(folder))
    for line in ("rm -rf build && git push origin main", "rm -rf build && curl https://example.com",
                 "rm -rf build tmp && npm i left-pad"):
        assert mod.classify.undo_chain(line, ctx.cwd) is None
    assert walked == []


def test_the_second_real_line_runs_free_and_its_undo_brings_tmp_and_the_backup_back(plugin):
    mod, ctx = make(plugin)
    files = project(ctx)
    assert kind(mod, ctx, SECOND) == ("file:shell:rm", "low", True)
    r = run(mod, ctx, SECOND, "c1")
    assert "test_ok" in r.stdout and not os.path.exists(os.path.join(ctx.cwd, "tmp"))
    assert ctx.prompts == []
    mod.cli.slash(f"undo {last_undo(mod)}")
    assert read(ctx, "tmp/scratch.txt") == files["tmp/scratch.txt"] and read(ctx, "notes.bak") == "notes\n"


def test_the_study_mode_reads_them_as_before(plugin):
    mod, ctx = make(plugin, {"mode": "study", "start": "trusted"})
    project(ctx)
    for line in (FIRST, SECOND):
        act = mod.classify.classify("terminal", {"command": line}, cwd=ctx.cwd)
        assert act.type == "shell:rm" and not act.reversible
        assert ctx.call("terminal", {"command": line}) == "approved"


# ---------------------------------------------------------------------------------------------- refusals
@pytest.mark.parametrize("case,command", [
    ("curl", "rm -rf tmp && curl https://example.com/docs"),
    ("curl-local", "rm -rf tmp && curl localhost:3000"),
    ("push", "rm -rf tmp && git push origin main"),
    ("dependency", "rm -rf tmp && npm i left-pad"),
    ("symlink", "rm -rf tmp link.txt && python3 -m unittest discover -s tests"),
    ("cap", "rm -rf tmp notes.bak && python3 -m unittest discover -s tests"),
    ("redirect", "rm -rf tmp && python3 -m unittest discover -s tests > out.txt"),
    ("substitution", "rm -rf tmp && echo $(whoami)"),
    ("backtick", "rm -rf tmp && echo `whoami`"),
    ("background", "rm -rf tmp & python3 -m unittest"),
    ("tee", "rm -rf tmp && python3 -m unittest 2>&1 | tee log.txt"),
    ("cd", "rm -rf tmp && cd tests && python3 -m unittest"),
    ("assignment", "rm -rf tmp && PYTHONPATH=. python3 -m unittest"),
    ("discard", "rm -rf tmp && git checkout -- inventory/report.py"),
    ("missing", "rm -rf tmp dist && python3 -m unittest"),
    ("unsaved-mv", "rm -rf tmp && mv inventory build/"),
    ("write-then-run", SED + "'s/ok/OK/' inventory/report.py && python3 inventory/report.py"),
    ("reader-file", "rm -rf tmp && python3 -m unittest 2>&1 | grep FAIL notes.bak"),
    ("reader-recursive", "rm -rf tmp && python3 -m unittest 2>&1 | grep -r FAIL"),
    ("pipe-middle", "rm -rf tmp | tail -3 && python3 -m unittest"),
])
def test_a_chain_keeps_its_question_when_a_segment_is_not_free_or_a_target_cannot_be_saved(plugin, case, command):
    mod, ctx = make(plugin)
    project(ctx, repo=False)
    if case == "symlink":
        os.symlink(os.path.join(ctx.cwd, "notes.bak"), os.path.join(ctx.cwd, "link.txt"))
    elif case == "cap":
        touch(ctx, "tmp/big.txt", "x" * 5_100_000)
    assert mod.classify.undo_chain(command, ctx.cwd) is None
    assert kind(mod, ctx, command)[0] not in ("file:shell", "file:shell:rm")
    assert ctx.call("terminal", {"command": command}) == "approved"
    assert os.path.exists(os.path.join(ctx.cwd, "tmp", "scratch.txt"))      # nothing ran without its answer


def test_a_line_of_free_segments_only_is_left_as_it_is():
    from tenure import classify
    assert classify.undo_chain("git status && git diff --stat", os.getcwd()) is None
    assert classify.undo_chain("rm -rf build", os.getcwd()) is None             # one segment: read as before


@pytest.mark.parametrize("command,ok", [
    ("a && b", True), ("a; b", True), ("a || b", True), ("a 2>&1 | tail -40", True), ("a | head -n 5", True),
    ("a | grep -E 'x|y' | head -3", True), ("a | cat -n", True), ("a | grep -iA 3 err", True),
    ("a && b # note", False), ("a && ~/b", False), ("a && (b)", False), ("a && b <in", False),
    ("a &&& b", False), ("a ;; b", False), ("a && \"$b\"", False), ("a 2>&1| tail", False), ("a &", False),
])
def test_what_a_chained_line_may_contain(command, ok):
    from tenure import classify
    parts = classify.chain_parts(command)
    assert (parts is not None) == ok


@pytest.mark.parametrize("reader,ok", [
    ("tail -40", True), ("tail -n 40", True), ("head -5", True), ("cat", True), ("grep -v DEBUG", True),
    ("grep -c ok", True), ("tail -f", False), ("tail -40 app.log", False), ("grep -r x", False),
    ("grep -f pats", False), ("grep x file", False), ("sort", False), ("tee out", False), ("grep", False),
])
def test_a_last_pipe_goes_only_into_pure_readers(reader, ok):
    from tenure import classify
    assert classify._chain_reader(reader, reader) == ok


# ------------------------------------------------------------------------------- outside content, display
def test_after_outside_content_a_chain_that_runs_code_asks_the_lift_question(plugin):
    mod, ctx = make(plugin)
    project(ctx, repo=False)
    ctx.call("web_extract", {"urls": ["https://example.com"]})
    assert ctx.call("terminal", {"command": SECOND}) == "approved"
    assert ":lift:" in ctx.prompts[-1]["rule_key"]
    assert last_undo(mod) is None                                      # asked: run without an undo, as any answer


def test_after_outside_content_a_chain_of_saved_file_commands_keeps_going_with_its_undo(plugin):
    mod, ctx = make(plugin)
    project(ctx, repo=False)
    ctx.call("web_extract", {"urls": ["https://example.com"]})
    line = "rm -rf tmp && rm notes.bak && " + SED + "'s/ok/OK/' inventory/report.py"
    assert mod.classify.undo_chain(line, ctx.cwd).runs is False
    assert ctx.call("terminal", {"command": line}) == "ran" and ctx.prompts == []
    assert last_undo(mod) is not None


def test_a_watched_chained_line_says_how_many_files_its_undo_holds(plugin):
    mod, ctx = make(plugin)
    project(ctx, repo=False)
    touch(ctx, "x.txt")
    ctx.call("terminal", {"command": "rm x.txt"})
    mod.cli.slash(f"undo {last_undo(mod)}")                           # a fault: file:shell:rm is watched now
    ctx.posted.clear()
    assert ctx.call("terminal", {"command": SECOND}) == "ran" and ctx.prompts == []
    mod.post_llm_call(session_id="s1")
    n = last_undo(mod)
    (line,) = ctx.posted
    assert f"#{n} rm -rf tmp notes.bak && python3" in line and "(+2 files)" in line
    home = mod.cli.slash("")
    assert "(+2 files)" in home


def test_a_file_the_line_deletes_never_hides_a_file_it_broke(plugin):
    """After the call, a deleted target cannot be read again: the files saved before it are judged instead."""
    mod, ctx = make(plugin)
    project(ctx, repo=False)
    line = "rm notes.bak && " + SED + "'s/import shout/imprt shout/' inventory/report.py"
    run(mod, ctx, line, "c1")
    assert state(mod, "file:shell:rm").faults == 1


def test_the_friction_bench_of_chained_lines():
    """The chained lines of a real run, on a project holding their files: what leaves the machine still asks, the
    four local lines run with an undo; after a web page, one lift question, then the same."""
    from friction import replay
    rows = replay("trusted", mode="simple", chains=True)
    assert [r["what"] for r in rows if r["tenure"]] == ["rm notes.bak && git push origin main",
                                                        "rm -rf tmp && curl -s https://example.com/api"]
    assert sum(r["undo"] for r in rows) == 4
    web = replay("trusted", mode="simple", chains=True, early_web=True)
    asked = [r["what"] for r in web if r["tenure"]]
    assert len(asked) == 3 and asked[0].startswith("git rm -rq build")
    assert sum(r["undo"] for r in web) == 3
