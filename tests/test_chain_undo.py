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
    ("pipe-middle-program", "rm -rf tmp | sh && python3 -m unittest"),
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
    ("grep -f pats", False), ("grep x file", False), ("sort", True), ("tee out", False), ("grep", False),
])
def test_a_pipe_goes_only_into_pure_readers(reader, ok):
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
    assert state(mod, "file:shell").faults == 1                        # sed broke it: the writer's kind, not rm's
    assert state(mod, "file:shell:rm") is None or state(mod, "file:shell:rm").faults == 0


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


# ------------------------------------------------------------------------------------ audits of PR #32, 1 to 16
@pytest.mark.parametrize("line", ["rm -rf build && git apply link.patch && rm -rf build/*",
                                  "git checkout evil && rm -rf build/*", "git stash pop && rm -rf build",
                                  "python3 -m unittest && rm -rf tmp"])
def test_r1_a_program_run_before_a_saved_segment_keeps_the_question(plugin, line):
    mod, ctx = make(plugin)
    project(ctx)
    assert mod.classify.undo_chain(line, ctx.cwd) is None
    assert ctx.call("terminal", {"command": line}) == "approved"
    assert mod.classify.undo_chain("git status && " + SECOND, ctx.cwd) is not None     # a read stays allowed anywhere


def test_r2_a_program_the_person_pinned_makes_the_line_ask_for_its_reason(plugin):
    mod, ctx = make(plugin)
    project(ctx, repo=False)
    touch(ctx, "build.py", "print('build')\n")                        # (deploy.py is high stakes by its name)
    touch(ctx, "x.tmp")
    assert ctx.call("terminal", {"command": "python3 build.py"}) == "ran"            # recorded, free
    mod.cli.slash("trust python ask")                                                  # every time, a person's word
    assert ctx.call("terminal", {"command": "rm -f x.tmp && python3 build.py"}) == "approved"
    assert "shell:python:build.py" in ctx.prompts[-1]["message"] and last_undo(mod) is None
    assert ctx.call("terminal", {"command": "rm -f x.tmp && python3 deploy.py"}) == "approved"


def test_r2_the_owners_setting_on_a_program_holds_inside_a_line(plugin):
    mod, ctx = make(plugin, {"types": {"shell:python*": "high"}})
    project(ctx, repo=False)
    assert ctx.call("terminal", {"command": SECOND}) == "approved"
    assert ":shell:python" in ctx.prompts[-1]["rule_key"]


@pytest.mark.parametrize("line", ["git rm -q 'a*.log' && rm -rf tmp", "git rm -q *.log && rm -rf tmp",
                                  "git rm -q :app.log && rm -rf tmp", "git rm -q 'app\\.log' && rm -rf tmp",
                                  "git mv 'inventory/text[u]til.py' inventory/text.py && rm -rf tmp"])
def test_r3_git_never_gets_a_pathspec_it_would_expand(plugin, line):
    mod, ctx = make(plugin)
    project(ctx)
    assert mod.classify.undo_chain(line, ctx.cwd) is None


@pytest.mark.parametrize("line,name", [(SED + "'s/a/b/' RUN.py && python3 run.py", "run.py"),
                                       (SED + "'s/a/b/' makefile && make", "makefile"),
                                       (SED + "'s/a/b/' GNUmakefile && make", "GNUmakefile")])
def test_r4_a_file_changed_then_run_is_read_as_the_file_system_reads_names(plugin, line, name):
    mod, ctx = make(plugin)
    project(ctx, repo=False)
    touch(ctx, name, "a = 1\n")
    assert mod.classify.undo_chain(line, ctx.cwd) is None


def test_r5_a_broken_file_blames_its_writer_and_an_undo_blames_the_line(plugin):
    mod, ctx = make(plugin)
    project(ctx, repo=False)
    run(mod, ctx, "rm notes.bak && " + SED + "'s/import shout/imprt shout/' inventory/report.py", "c1")
    assert state(mod, "file:shell").faults == 1
    run(mod, ctx, "rm -rf tmp && python3 -m unittest discover -s tests", "c2")
    mod.cli.slash(f"undo {last_undo(mod)}")
    assert state(mod, "file:shell:rm").faults == 1 and state(mod, "file:shell").faults == 1


def test_r6_outside_any_session_a_chained_line_is_settled_by_its_type_before_it_ran(plugin):
    mod, ctx = make(plugin)
    project(ctx, repo=False)
    args = {"command": SECOND}
    assert pre(mod, "terminal", args, "c1", session="") is None
    subprocess.run(["bash", "-c", SECOND], cwd=ctx.cwd, capture_output=True, env=ENV)
    post(mod, "terminal", args, "c1", session="")
    assert mod.store_().pending_rows(mod.anon(""), "c1") == [] and last_undo(mod) is not None


def test_r7_a_worktree_or_a_submodule_index_is_not_promised(plugin, tmp_path):
    from tenure import undo
    mod, ctx = make(plugin)
    project(ctx)
    wt = str(tmp_path / "wt")
    git(ctx, "worktree", "add", "-q", wt)
    line = "git rm -q app.log && rm -rf tmp"
    assert mod.classify.undo_chain(line, ctx.cwd) is not None
    assert mod.classify.undo_chain(line, wt) is None                     # .git is a file there
    assert undo.snapshot([os.path.join(wt, "app.log")], str(tmp_path / "data"), key=b"k" * 32, cwd=wt,
                         git=[os.path.join(wt, "app.log")]) is None


def test_r8_one_budget_for_the_whole_line(plugin, monkeypatch):
    mod, ctx = make(plugin)
    project(ctx, repo=False)
    for folder in ("a", "b"):
        for i in range(1100):
            touch(ctx, f"{folder}/f{i}.txt", "x")
    assert mod.classify.undo_chain("rm -rf a a a && true", ctx.cwd) is not None       # one operand given thrice
    assert mod.classify.undo_chain("rm -rf a && rm -rf b && true", ctx.cwd) is None   # 2200 files in all
    touch(ctx, "big/one.txt", "x" * 3_000_000)
    touch(ctx, "big2/two.txt", "x" * 3_000_000)
    assert mod.classify.undo_chain("rm -rf big && true", ctx.cwd) is not None
    assert mod.classify.undo_chain("rm -rf big big2 && true", ctx.cwd) is None         # 6 MB together
    monkeypatch.setattr(mod.classify, "CHAIN_SECONDS", -1.0)
    assert mod.classify.undo_chain("rm -rf big && true", ctx.cwd) is None              # past its deadline: asks


def test_r9_the_index_of_a_folder_comes_back_with_entries_that_had_no_file(plugin, monkeypatch):
    mod, ctx = make(plugin)
    project(ctx)
    os.remove(os.path.join(ctx.cwd, "build", "out.txt"))               # tracked, gone from the disk
    monkeypatch.setattr(mod.undo, "LS_BATCH", 2)                       # several git ls-files calls
    before = status(ctx)
    run(mod, ctx, "git rm -rq build app.log debug.log && rm -rf tmp", "c1")
    mod.cli.slash(f"undo {last_undo(mod)}")
    assert status(ctx) == before


@pytest.mark.parametrize("flag,line", [
    (["add", "-N", "new.txt"], "git mv new.txt newer.txt && rm -rf tmp"),
    (["update-index", "--skip-worktree", "app.log"], "git rm -q app.log && rm -rf tmp"),
    (["update-index", "--assume-unchanged", "app.log"], "git rm -q app.log && rm -rf tmp"),
])
def test_r9_an_index_entry_with_a_flag_is_not_promised_back(plugin, flag, line):
    mod, ctx = make(plugin)
    project(ctx)
    touch(ctx, "new.txt", "new\n")
    git(ctx, *flag)
    assert mod.classify.undo_chain(line, ctx.cwd) is not None           # read as a chain...
    d = pre(mod, "terminal", {"command": line}, "c9")
    assert d is not None and "can't save" in d["message"]               # ...but no undo it could not keep: asked


def test_r9_a_failed_index_is_kept_and_put_back_by_the_same_undo(plugin):
    mod, ctx = make(plugin)
    project(ctx)
    run(mod, ctx, FIRST, "c1")
    n = last_undo(mod)
    lock = os.path.join(ctx.cwd, ".git", "index.lock")
    touch(ctx, ".git/index.lock", "")
    out = mod.cli.slash(f"undo {n}")
    assert f"/tenure undo {n}" in out
    os.remove(lock)
    again = mod.cli.slash(f"undo {n}")
    assert "index is back" in again and status(ctx) == ""


def test_r9_no_word_about_an_index_outside_git(plugin):
    mod, ctx = make(plugin)
    project(ctx, repo=False)
    run(mod, ctx, SECOND, "c1")
    assert "index" not in mod.cli.slash(f"undo {last_undo(mod)}")


def test_r10_a_link_to_git_data_is_git_data(plugin):
    mod, ctx = make(plugin)
    project(ctx)
    os.symlink(".git", os.path.join(ctx.cwd, "g"))
    assert not mod.classify._undo_target_ok(os.path.join(ctx.cwd, "g", "HEAD"), ctx.cwd, os.path.expanduser("~"),
                                            wide=True)
    assert mod.classify.undo_chain("rm g/HEAD && true", ctx.cwd) is None


def test_r11_one_reading_whatever_the_spaces_around_the_line(plugin, monkeypatch):
    mod, ctx = make(plugin)
    project(ctx, repo=False)
    seen = []
    real = mod.classify._read_chain
    monkeypatch.setattr(mod.classify, "_read_chain", lambda *a: seen.append(1) or real(*a))
    with mod.classify.one_reading():
        mod.classify.undo_chain(SECOND, ctx.cwd)
        mod.classify.undo_chain("  " + SECOND + " ", ctx.cwd)
    assert len(seen) == 1


@pytest.mark.parametrize("line,ok", [("set -euo pipefail && rm -rf tmp && python3 -m unittest", True),
                                     ("set -x; rm -rf tmp", True), ("set -f && rm -rf tmp", False),
                                     ("shopt -s dotglob && rm -rf tmp", False), ("rm -rf tmp && echo =ls", False),
                                     ("rm -rf tmp =ls && true", False)])
def test_r12_what_the_shell_may_be_told(plugin, line, ok):
    mod, ctx = make(plugin)
    project(ctx, repo=False)
    assert (mod.classify.undo_chain(line, ctx.cwd) is not None) == ok


def test_r12_a_zsh_equals_word_is_never_an_rm_target():
    from tenure import classify
    assert classify._undo_rm(["=ls"], os.getcwd(), os.path.expanduser("~"), wide=True) is None


def test_r13_a_program_of_the_project_is_a_script_the_agent_may_have_written(plugin):
    mod, ctx = make(plugin)
    project(ctx, repo=False)
    ctx.call("write_file", {"path": "bin/python3", "content": "#!/bin/sh\n"})
    assert ctx.call("terminal", {"command": "./bin/python3 x.py"}) == "approved"     # written, now run: asked once


@pytest.mark.parametrize("command", ["git checkout-index -a -f", "git read-tree -u --reset HEAD"])
def test_r13_more_ways_to_throw_work_away(command):
    from tenure import classify
    assert classify.classify("terminal", {"command": command}, cwd=os.getcwd(), wide=True).type == "shell:git:discard"
    assert classify.classify("terminal", {"command": command}, cwd=os.getcwd()).type != "shell:git:discard"   # study


def test_r14_the_count_says_the_files_that_come_back(plugin):
    mod, ctx = make(plugin)
    project(ctx)
    touch(ctx, "x.txt")
    ctx.call("terminal", {"command": "rm x.txt"})
    mod.cli.slash(f"undo {last_undo(mod)}")                           # watched now
    ctx.posted.clear()
    assert ctx.call("terminal", {"command": FIRST}) == "ran"
    mod.post_llm_call(session_id="s1")
    assert "(+6 files)" in ctx.posted[-1]                            # text.py did not exist: not counted


def test_r15_study_mode_writes_no_count_and_old_counts_go(plugin):
    mod, ctx = make(plugin, {"mode": "study", "start": "trusted"})
    project(ctx, repo=False)
    run(mod, ctx, "rm notes.bak && rm app.log", "c1")
    assert last_undo(mod) is not None
    st = mod.store_()
    assert st.db.execute("SELECT COUNT(*) FROM meta WHERE key LIKE 'undo_files:%'").fetchone()[0] == 0
    with mod.txn() as st:
        st.set_meta(mod.UNDO_FILES + str(last_undo(mod)), "2")
        st.db.execute("UPDATE undo SET at = at - ?", (mod.UNDO_WINDOW + 10,))
        st.drop_undo_meta((mod.UNDO_FILES,), __import__("time").time() - mod.UNDO_WINDOW)
        assert st.get_meta(mod.UNDO_FILES + str(last_undo(mod))) is None


def test_r16_the_lift_question_says_what_a_long_line_hides(plugin):
    mod, ctx = make(plugin)
    project(ctx, repo=False)
    ctx.call("web_extract", {"urls": ["https://example.com"]})
    long = SECOND + " | grep -v DEBUG" * 12
    assert len(long) > 200 and mod.classify.hidden_segments(long) > 0
    assert ctx.call("terminal", {"command": long}) == "approved"
    assert f"(+{mod.classify.hidden_segments(long)} segments)" in ctx.prompts[-1]["message"]


# ---------------------------------------------------------------------------------- targeted review of 40d767b
@pytest.mark.parametrize("line", ["rm -f x.txt >main.py && true", "rm -f x.txt >>main.py && true",
                                  "git rm -q app.log >main.py && true"])
def test_ra_a_redirect_beside_rm_or_git_rm_keeps_the_question(plugin, line):
    mod, ctx = make(plugin)
    project(ctx)
    for name in ("x.txt", ">main.py", ">>main.py", "main.py"):
        touch(ctx, name, "keep\n")
    assert mod.classify.undo_chain(line, ctx.cwd) is None
    verdict = ctx.call("terminal", {"command": line})
    assert last_undo(mod) is None                                       # never an undo that would not hold main.py
    # rm asks; git rm with its output redirected runs as a covered tool's output always did (`pytest > log`)
    assert verdict == ("ran" if line.startswith("git") else "approved")


def test_rb_git_rm_and_file_writes_beside_rm_must_be_free_on_their_own(plugin):
    mod, ctx = make(plugin)
    project(ctx)
    assert ctx.call("terminal", {"command": "git rm -q --cached debug.log"}) == "ran"    # shell:git:rm recorded
    mod.cli.slash("trust git:rm ask")
    line = "git rm -q app.log && rm -rf tmp"
    assert ctx.call("terminal", {"command": line}) == "approved" and "shell:git:rm" in ctx.prompts[-1]["message"]
    mod2, ctx2 = make(plugin)
    project(ctx2, repo=False)
    ctx2.call("terminal", {"command": SED + "'s/ok/OK/' inventory/report.py"})          # file:shell, saved
    mod2.cli.slash(f"undo {last_undo(mod2)}")                                          # a mistake: watched
    line = "rm -rf tmp && " + SED + "'s/ok/OK/' inventory/report.py"
    assert ctx2.call("terminal", {"command": line}) == "approved" and "file:shell" in ctx2.prompts[-1]["message"]


def test_rc_a_program_at_capped_stakes_keeps_the_question(plugin):
    mod, ctx = make(plugin, {"risks": {"low": "1/50", "medium": "cap", "high": "cap"}})
    project(ctx, repo=False)
    line = "rm -rf tmp && python3 -m unittest discover -s tests"       # the line is low, python is medium
    assert ctx.call("terminal", {"command": line}) == "approved"


def test_rc_bis_a_free_setting_on_the_line_keeps_the_pins_of_its_programs(plugin):
    mod, ctx = make(plugin, {"types": {"file:shell:rm": "free"}})
    project(ctx, repo=False)
    touch(ctx, "build.py", "print(1)\n")
    assert ctx.call("terminal", {"command": "python3 build.py"}) == "ran"
    mod.cli.slash("trust python ask")
    assert ctx.call("terminal", {"command": "rm -rf tmp && python3 build.py"}) == "approved"


@pytest.mark.parametrize("line", ["rm -rf build && mv notes.bak build", "rm -rf build && cp notes.bak build/x.bak",
                                  "git rm -rq build && git mv notes.bak build"])
def test_rd_a_move_into_what_the_line_deleted_keeps_the_question(plugin, line):
    mod, ctx = make(plugin)
    project(ctx)
    assert mod.classify.undo_chain(line, ctx.cwd) is None


def test_re_a_program_named_git_elsewhere_is_an_ordinary_program(plugin):
    mod, ctx = make(plugin)
    project(ctx)
    touch(ctx, "git", "#!/bin/sh\n")
    assert mod.classify.undo_chain("./git rm -q app.log && rm -rf tmp", ctx.cwd) is None       # a program, then rm
    chain = mod.classify.undo_chain("rm -rf tmp && ./git rm -q app.log", ctx.cwd)
    assert chain is None or chain.git == ()                                                   # never saved as git rm


def test_rg_two_identical_lines_outside_a_session_each_keep_their_undo(plugin):
    mod, ctx = make(plugin)
    project(ctx, repo=False)
    args = {"command": "rm -rf tmp && python3 -m unittest discover -s tests"}
    assert pre(mod, "terminal", args, "call_0", session="") is None
    assert pre(mod, "terminal", args, "call_0", session="") is None
    post(mod, "terminal", args, "call_0", session="")
    snaps = [r[0] for r in mod.store_().db.execute("SELECT snap_id FROM undo WHERE snap_id IS NOT NULL")]
    assert len(snaps) == 2 and len(set(snaps)) == 2
    import shutil
    shutil.rmtree(os.path.join(ctx.cwd, "tmp"))
    mod.cli.slash(f"undo {last_undo(mod)}")
    assert read(ctx, "tmp/scratch.txt") == "scratch\n"


def test_rh_a_late_index_retry_says_it_can_no_longer_be_done(plugin):
    mod, ctx = make(plugin)
    project(ctx)
    run(mod, ctx, FIRST, "c1")
    n = last_undo(mod)
    touch(ctx, ".git/index.lock", "")
    mod.cli.slash(f"undo {n}")
    os.remove(os.path.join(ctx.cwd, ".git", "index.lock"))
    snap = mod.store_().get_undo(n)["snap_id"]
    mod.undo.discard(snap, mod.data_dir())                             # purged meanwhile
    again = mod.cli.slash(f"undo {n}")
    assert "no longer" in again and "index is back" not in again


@pytest.mark.parametrize("command", ["git diff --output=out.txt", "git diff --output out.txt"])
def test_git_diff_output_writes_a_file_and_is_no_read(command):
    from tenure import classify
    for wide in (True, False):
        assert classify.classify("terminal", {"command": command}, cwd=os.getcwd(), wide=wide).stakes != "free"
