"""Simple mode: a pipe into a pure reader anywhere in a chained line (third run with Sonnet in Hermes). The agent
ends its lines with `python3 -m unittest ... 2>&1 | tail -30; git status --short`: the segment before the pipe is
read as itself, at its place, and the line runs with one undo. A pipe into anything but a pure reader keeps the
question."""
import os
import subprocess
import sys

import pytest

from test_plugin import plugin  # noqa: F401  (plugin is a fixture)
from test_chain_undo import ENV, git, kind, last_undo, make, read, run, touch

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the commands are POSIX")

SED = "sed -i '' " if sys.platform == "darwin" else "sed -i "      # the in-place edit as this system's sed spells it
FIRST = ("git rm -rq build app.log debug.log && rm -rf build && git mv inventory/textutil.py inventory/text.py && "
         + SED + "'s/from inventory\\.textutil import/from inventory.text import/' tests/test_report.py && "
         + SED + "'s/from \\.textutil import/from .text import/' inventory/report.py && "
         + SED + "'s#inventory/textutil\\.py#inventory/text.py#' README.md && "
         "grep -rn textutil --exclude-dir=.git . ; python3 -m unittest discover -s tests -v 2>&1 | tail -30; "
         "git status --short")
SECOND = "rm -rf tmp notes.bak && python3 -m unittest discover -s tests -v 2>&1 | tail -40; git status --short"
FILES = {".gitignore": "__pycache__/\n", "build/a.o": "obj a\n", "build/sub/b.o": "obj b\n", "app.log": "app\n",
         "debug.log": "debug\n", "tmp/one.txt": "one\n", "tmp/two.txt": "two\n", "notes.bak": "notes\n",
         "inventory/__init__.py": "", "inventory/textutil.py": "def shout(s):\n    return s.upper()\n",
         "inventory/report.py": "from .textutil import shout\n",
         "tests/test_report.py": "import unittest\n\nfrom inventory.textutil import shout\n\n\n"
                                 "class T(unittest.TestCase):\n    def test_shout(self):\n"
                                 "        self.assertEqual(shout('ok'), 'OK')\n",
         "README.md": "See inventory/textutil.py.\n"}


def project(ctx):
    for name, text in FILES.items():
        touch(ctx, name, text)
    git(ctx, "init", "-q")
    git(ctx, "add", "-A")
    git(ctx, "commit", "-qm", "start")


def status(ctx):
    return subprocess.run(["git", "status", "--porcelain"], cwd=ctx.cwd, capture_output=True, text=True, env=ENV,
                          check=True).stdout


def exists(ctx, name):
    return os.path.lexists(os.path.join(ctx.cwd, name))


# --------------------------------------------------------------------------------------- the two real lines
@pytest.mark.parametrize("line", [FIRST, SECOND], ids=["first", "second"])
def test_the_real_lines_run_free_and_one_undo_puts_everything_back_index_included(plugin, line):
    mod, ctx = make(plugin)
    project(ctx)
    assert kind(mod, ctx, line) == ("file:shell:rm", "low", True)
    r = run(mod, ctx, line, "c1")
    assert r.returncode == 0, r.stderr
    assert ctx.prompts == []
    if line == FIRST:
        assert not exists(ctx, "build") and not exists(ctx, "app.log") and exists(ctx, "inventory/text.py")
        assert "Ran 1 test" in r.stdout and "OK" in r.stdout                    # the renamed module still imports
        assert "from .text import" in read(ctx, "inventory/report.py")
    else:
        assert not exists(ctx, "tmp") and not exists(ctx, "notes.bak")
    assert status(ctx) != ""
    out = mod.cli.slash(f"undo {last_undo(mod)}")
    for name, text in FILES.items():
        assert read(ctx, name) == text, (name, out)
    assert not exists(ctx, "inventory/text.py")
    assert status(ctx) == "", status(ctx)                                       # git's index too


# ------------------------------------------------------------------------------- the forms around them
BASE = "rm -rf tmp notes.bak && python3 -m unittest discover -s tests -v 2>&1 | tail -40"


@pytest.mark.parametrize("line", [
    BASE + "; git status", BASE + "; git diff --stat", BASE + "; ls -la", BASE + " && echo done", BASE + " || true",
    "rm -rf tmp notes.bak && echo done", "rm -rf tmp notes.bak || true",
    "rm -rf tmp | tail -3 && python3 -m unittest discover -s tests",               # a pipe in the middle of the line
    "rm -rf tmp notes.bak 2>&1 | head -5; python3 -m unittest discover -s tests 2>&1 | grep -c ok | wc -l",
    "ls | wc -l && rm -rf tmp notes.bak",                                           # a read piped before the deletion
    BASE + " | sort | uniq -c; git status --short",
    BASE + " | sort -rn -k 2,2 | uniq -ci | head -n 3",
])
def test_a_segment_piped_into_pure_readers_counts_as_itself(plugin, line):
    mod, ctx = make(plugin)
    project(ctx)
    assert kind(mod, ctx, line) == ("file:shell:rm", "low", True)
    chain = mod.classify.undo_chain(line, ctx.cwd)
    assert chain is not None and os.path.join(ctx.cwd, "tmp", "one.txt") in chain.paths


@pytest.mark.parametrize("grep", [
    "grep -rn textutil --exclude-dir=.git .", "grep -R -n -i -l shout .", "grep -rL shout inventory",
    "grep -rcEFwvHhoqs shout .", "grep -r --include='*.py' --exclude='*.md' --exclude-dir=.git --color=never shout .",
])
def test_grep_with_its_usual_options_is_a_read_anywhere(plugin, grep):
    mod, ctx = make(plugin)
    project(ctx)
    for line in ("rm -rf tmp && " + grep, grep + " ; rm -rf tmp", "rm -rf tmp && " + grep + " | head -5"):
        assert mod.classify.undo_chain(line, ctx.cwd) is not None, line


# ------------------------------------------------------------------------------------------------ refusals
@pytest.mark.parametrize("line", [
    BASE + " | tee f", BASE + " | tee f; git status", "rm -rf tmp | sh; git status", BASE + " | sh",
    "rm -rf tmp notes.bak | xargs rm", BASE + " | xargs rm", BASE + " | python", BASE + " | python3 -",
    BASE + " | tail -5 /etc/hosts", BASE + " | grep ok /etc/hosts", BASE + " | cat /etc/hosts; git status",
    BASE + " | sort -o out.txt", BASE + " | sort --compress-program=sh", BASE + " | sort -T /tmp",
    BASE + " | uniq - out.txt", BASE + " | wc --files0-from=list", BASE + " | grep -r ok",
    "python3 -m unittest discover -s tests 2>&1 | tail -5; rm -rf tmp",           # a program before a deletion
])
def test_a_pipe_into_anything_but_a_pure_reader_keeps_the_question(plugin, line):
    mod, ctx = make(plugin)
    project(ctx)
    assert mod.classify.undo_chain(line, ctx.cwd) is None
    assert kind(mod, ctx, line)[0] not in ("file:shell", "file:shell:rm")
    assert ctx.call("terminal", {"command": line}) == "approved"
    assert exists(ctx, "tmp/one.txt")                                           # nothing ran without its answer


@pytest.mark.parametrize("reader,ok", [
    ("wc -l", True), ("wc -lw", True), ("wc --lines", True), ("wc -l notes.bak", False),
    ("sort", True), ("sort -rn", True), ("sort -k2", True), ("sort -k 2,2n", True), ("sort --key=1", True),
    ("sort -o x", False), ("sort -ro x", False), ("sort --output=x", False), ("sort -t, -k2", False),
    ("sort notes.bak", False), ("uniq", True), ("uniq -c", True), ("uniq -f 1", True), ("uniq -s2", True),
    ("uniq in.txt", False), ("uniq - out.txt", False), ("grep -L x", True), ("grep -R x", False),
])
def test_the_new_readers_take_no_file_and_write_nothing(reader, ok):
    from tenure import classify
    assert classify._chain_reader(reader, reader) == ok
