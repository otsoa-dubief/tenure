"""Simple mode: the forms a real agent writes (second run with Sonnet in Hermes). `rm -f ./*.log`, BSD `sed -i ''` with
several substitutions and delimiters, quoted `#`, `!`, `~`, `{}`, a final `grep -rn ... --include='*.py'`: a chained
line of these runs with one undo. What tenure cannot read still asks, and says what it could not read."""
import os
import shutil
import subprocess
import sys

import pytest

from test_plugin import plugin  # noqa: F401  (plugin is a fixture)
from test_chain_undo import ENV, last_undo, make, read, run, touch

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the commands are POSIX")

BSD = sys.platform == "darwin"
SED_I = "sed -i '' " if BSD else "sed -i "                # the in-place edit as this system's sed spells it
SCRIPT = "'s/inventory\\.textutil/inventory.text/; s/\\.textutil/.text/; s#inventory/textutil\\.py#inventory/text.py#'"
REAL = ("rm -rf build && rm -f ./*.log && mv inventory/textutil.py inventory/text.py && " + SED_I + SCRIPT
        + " tests/test_report.py inventory/report.py README.md && grep -rn \"textutil\" .")
FILES = {"build/a.o": "obj a\n", "build/sub/b.o": "obj b\n", "app.log": "app\n", "debug.log": "debug\n",
         "inventory/__init__.py": "", "inventory/textutil.py": "def shout(s):\n    return s.upper()\n",
         "inventory/report.py": "from inventory.textutil import shout\n",
         "tests/test_report.py": "import inventory.textutil\n", "README.md": "See inventory/textutil.py.\n"}


def project(ctx, logs=True):
    for name, text in FILES.items():
        if logs or not name.endswith(".log"):
            touch(ctx, name, text)


def kind(mod, ctx, command):
    a = mod.classify.classify("terminal", {"command": command}, cwd=ctx.cwd, wide=True)
    return a.type, a.stakes


# ------------------------------------------------------------------------------------------- the real line
@pytest.mark.parametrize("variant", ["as written", "grep with --include", "no log file"])
def test_the_real_line_runs_free_and_its_undo_puts_everything_back(plugin, variant):
    mod, ctx = make(plugin)
    project(ctx, logs=variant != "no log file")
    line = REAL + (" --include='*.py' --include='*.md'" if variant == "grep with --include" else "")
    assert kind(mod, ctx, line) == ("file:shell:rm", "low")
    run(mod, ctx, line, "c1")                                  # grep finds nothing left: the line ends in error
    assert not os.path.exists(os.path.join(ctx.cwd, "build")) and "inventory.text " in read(ctx, "inventory/report.py")
    assert ctx.prompts == []
    mod.cli.slash(f"undo {last_undo(mod)}")
    for name, text in FILES.items():
        if variant != "no log file" or not name.endswith(".log"):
            assert read(ctx, name) == text, name
    assert not os.path.exists(os.path.join(ctx.cwd, "inventory", "text.py"))


# ----------------------------------------------------------------------------------------------- 1. ./ globs
@pytest.mark.parametrize("plain,dotted", [("rm -f *.log", "rm -f ./*.log"), ("rm build/*.o", "rm ./build/*.o")])
def test_a_glob_written_with_dot_slash_is_the_same_glob(plugin, plain, dotted):
    mod, ctx = make(plugin)
    project(ctx)
    files = mod.classify.files_written("terminal", {"command": plain}, ctx.cwd, wide=True)
    assert files and mod.classify.files_written("terminal", {"command": dotted}, ctx.cwd, wide=True) == files
    assert kind(mod, ctx, dotted) == ("file:shell:rm", "low")
    chain = mod.classify.undo_chain(dotted + " && true", ctx.cwd)
    assert chain is not None and list(chain.paths) == files


@pytest.mark.parametrize("command", ["rm -f *.log", "rm *.log", "rm -f ./*.log", "rm -rf ./*.log",
                                     "rm -fv *.log *.tmp"])
def test_an_rm_whose_patterns_match_nothing_removes_nothing_and_runs_free(plugin, command):
    mod, ctx = make(plugin)
    project(ctx, logs=False)
    assert kind(mod, ctx, command) == ("shell:rm", "free")           # without -f it fails, it removes nothing either
    assert ctx.call("terminal", {"command": command}) == "ran" and ctx.prompts == []
    assert last_undo(mod) is None                                                # nothing to save


def test_a_pattern_that_matches_nothing_but_names_a_file_keeps_the_question(plugin):
    mod, ctx = make(plugin)
    project(ctx, logs=False)
    touch(ctx, "[ab].log", "named like the pattern\n")                        # bash would remove this one
    assert kind(mod, ctx, "rm -f [ab].log")[1] != "free"
    assert ctx.call("terminal", {"command": "rm -f [ab].log"}) == "approved"
    assert mod.classify.undo_chain("rm -f [ab].log && rm -rf build", ctx.cwd) is None


def test_in_a_chain_an_rm_that_removes_nothing_is_left_out_of_the_reading(plugin):
    mod, ctx = make(plugin)
    project(ctx, logs=False)
    chain = mod.classify.undo_chain("rm -f ./*.log && rm -rf build", ctx.cwd)     # nothing from it, no refusal
    assert chain is not None and all("build" in p for p in chain.paths)
    assert kind(mod, ctx, "rm -f ./*.log && python3 -m pytest -q") == ("shell:python:-m:pytest", "medium")
    assert ctx.call("terminal", {"command": "rm -f ./*.log && python3 -m pytest -q"}) == "ran"
    assert kind(mod, ctx, "rm -f ./*.log && git push origin main")[0] == "shell:git:push"


# --------------------------------------------------------------------------------------------- 2. sed -i
SCRIPTS = ["'s/a/b/'", "'s/a/b/g; s/c/d/'", "'s#x/y#z#g'", "'s|a|b|I'", "'s,a,b,2'", "'s/a/b/p;s/c/d/i'",
           "'s/a\\.b/c\\/d/'", "'/^#/d'"]


@pytest.mark.parametrize("script", SCRIPTS)
def test_sed_in_place_with_several_substitutions_and_delimiters(plugin, script):
    mod, ctx = make(plugin)
    project(ctx)
    line = SED_I + script + " inventory/report.py README.md"
    assert kind(mod, ctx, line) == ("file:shell", "low")
    assert mod.classify.undo_chain("rm -rf build && " + line, ctx.cwd) is not None


@pytest.mark.parametrize("form,bsd", [("sed -i.bak ", None), ("sed -i '' ", True), ("sed -i ", False),
                                      ("sed -i .bak ", True)])
def test_sed_in_place_spellings(plugin, form, bsd):
    if bsd is not None and bsd != BSD:
        pytest.skip("this spelling is the other system's sed")
    mod, ctx = make(plugin)
    project(ctx)
    files = mod.classify.files_written("terminal", {"command": form + "'s/a/b/' README.md"}, ctx.cwd, wide=True)
    readme = os.path.join(ctx.cwd, "README.md")
    assert readme in files and ((readme + ".bak") in files) == ("bak" in form)


@pytest.mark.parametrize("script", ["'s/a/b/e'", "'s/a/b/w out.txt'", "'e date'", "'1r other.txt'", "'R other.txt'",
                                    "'W out.txt'", "'{ s/a/b/ }'", "s/a/$X/", '"s/$X/b/"'])
def test_sed_scripts_that_run_read_or_write_elsewhere_keep_their_question(plugin, script):
    mod, ctx = make(plugin)
    project(ctx)
    line = SED_I + script + " README.md"
    assert kind(mod, ctx, line)[0] not in ("file:shell", "file:shell:rm")
    assert mod.classify.undo_chain("rm -rf build && " + line, ctx.cwd) is None


# --------------------------------------------------------------------------------------------- 3. quoting
@pytest.mark.parametrize("words,ok", [("'#!{}~'", True), ("'a*b?[c]'", True), ('"#{}~"', True),
                                      ('"wow!"', False), ('"$HOME"', False), ("#comment", False), ("~/x", False)])
def test_what_single_quotes_hide_from_the_shell_is_plain_text(plugin, words, ok):
    mod, ctx = make(plugin)
    project(ctx)
    line = "rm -rf build && grep -n " + words + " README.md"
    assert (mod.classify.undo_chain(line, ctx.cwd) is not None) == ok


def test_a_quoted_glob_given_to_rm_is_a_name_not_a_pattern(plugin):
    mod, ctx = make(plugin)
    project(ctx)
    touch(ctx, "*.log", "a file named star\n")
    chain = mod.classify.undo_chain("rm -f '*.log' && true", ctx.cwd)
    assert chain is not None and [os.path.basename(p) for p in chain.paths] == ["*.log"]


# ------------------------------------------------------------------------------------- 4. words for unknown
def test_unknown_files_have_a_label_and_a_reason(plugin):
    mod, ctx = make(plugin)
    project(ctx)
    assert mod.cli.kind_label("file:unknown") == "files tenure couldn't identify"
    assert ctx.call("terminal", {"command": "rm -f [a-z]*.log"}) == "approved"
    message = ctx.prompts[-1]["message"]
    assert "a pattern tenure couldn't expand" in message and "files tenure couldn't identify" in message
    assert "a pattern tenure couldn't expand" in mod.cli.slash("trust")
    ctx.call("terminal", {"command": "rm -f $TMPDIR/a.txt"})
    assert "a variable or a substitution tenure couldn't read" in ctx.prompts[-1]["message"]
