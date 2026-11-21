"""The defensive review of PR #35: what a glob may name (a file read as an option, a home, a variable), grep's bare
pattern before -e, sed's separate suffix under a GNU sed, what curl and wget write or send, a redirect after a free
read, and an exit code a pipe or a `;` hides. Points marked "both modes" hold in study mode too."""
import os
import subprocess
import sys

import pytest

from test_plugin import plugin  # noqa: F401  (plugin is a fixture)

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the commands are POSIX")

SIMPLE = {"start": "trusted", "mode": "simple"}
STUDY = {"start": "trusted"}
SED_I = "sed -i '' " if sys.platform == "darwin" else "sed -i "


def touch(ctx, name, text="a\n"):
    path = os.path.join(ctx.cwd, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def kind(mod, ctx, line, wide=True):
    act = mod.classify.classify("terminal", {"command": line}, cwd=ctx.cwd, wide=wide)
    return act.type, act.stakes


def written(mod, ctx, line):
    return mod.classify.files_written("terminal", {"command": line}, ctx.cwd, wide=True)


# ----------------------------------------------------------------------------- F1: a match read as an option
def test_f1_a_glob_match_named_like_an_option_keeps_the_question(plugin):
    mod, ctx = plugin(SIMPLE)
    touch(ctx, "a.sed")
    touch(ctx, "--file=x.sed", "w stolen.txt\n")                 # sed would read its script from x.sed
    line = SED_I + "'s/a/b/' *.sed"
    assert written(mod, ctx, line) == []
    assert kind(mod, ctx, line)[1] != "free"
    assert ctx.call("terminal", {"command": line}) == "approved"
    chained = "echo > --file=x.sed && " + SED_I + "'s/a/b/' *.sed"
    assert mod.classify.undo_chain(chained, ctx.cwd) is None
    assert ctx.call("terminal", {"command": chained}) == "approved"


def test_f1_rm_over_a_glob_that_matches_an_option_name_keeps_the_question(plugin):
    mod, ctx = plugin(SIMPLE)
    touch(ctx, "a.txt")
    touch(ctx, "-rf.txt")
    assert written(mod, ctx, "rm *.txt") == []
    assert mod.classify.undo_chain("rm -f *.txt && true", ctx.cwd) is None
    assert ctx.call("terminal", {"command": "rm *.txt"}) == "approved"


def test_f1_a_target_named_like_an_option_is_never_saved(plugin):
    mod, ctx = plugin(SIMPLE)
    touch(ctx, "-n")
    assert not mod.classify._undo_target_ok(os.path.join(ctx.cwd, "-n"), ctx.cwd, os.path.expanduser("~"))
    assert written(mod, ctx, "echo x > ./-n") == []


# ---------------------------------------------------------------------------- F2: a home or a variable
@pytest.mark.parametrize("word", ["~/x*.log", "$HOME/x*.log", "${HOME}/*.log", "logs/$X*.log"])
def test_f2_a_glob_with_a_home_or_a_variable_is_not_read(plugin, word):
    mod, ctx = plugin(SIMPLE)
    assert mod.classify._glob_matches(word, ctx.cwd, os.path.expanduser("~")) is None


# ------------------------------------------------------------------------------ F3: grep x -e y
@pytest.mark.parametrize("reader,ok", [("grep foo -e bar", False), ("grep foo --regexp=bar", False),
                                       ("grep foo --regexp bar", False), ("grep foo -ie bar", False),
                                       ("grep -e bar", True), ("grep -e bar -e baz", True), ("grep foo", True),
                                       ("grep -i foo", True)])
def test_f3_a_bare_pattern_then_e_makes_the_bare_word_a_file(reader, ok):
    from tenure import classify
    assert classify._chain_reader(reader, reader) is ok


def test_f3_such_a_reader_keeps_the_chain_asking(plugin):
    mod, ctx = plugin(SIMPLE)
    touch(ctx, "tmp/a.txt")
    assert mod.classify.undo_chain("rm -rf tmp && pytest -q 2>&1 | grep FAIL -e ERROR", ctx.cwd) is None


# ------------------------------------------------------------------- F5: BSD -i SUFFIX under a GNU sed
@pytest.mark.skipif(sys.platform != "darwin", reason="the separate suffix is BSD sed's reading")
def test_f5_a_separate_suffix_that_names_a_file_keeps_the_question(plugin):
    mod, ctx = plugin(SIMPLE)
    touch(ctx, "f.txt")
    line = "sed -i .bak -e 's/a/b/' f.txt"
    assert written(mod, ctx, line) == [os.path.join(ctx.cwd, "f.txt"), os.path.join(ctx.cwd, "f.txt.bak")]
    touch(ctx, ".bak", "a GNU sed would edit me\n")
    assert written(mod, ctx, line) == []
    assert written(mod, ctx, "sed -i '' -e 's/a/b/' f.txt") == [os.path.join(ctx.cwd, "f.txt")]
