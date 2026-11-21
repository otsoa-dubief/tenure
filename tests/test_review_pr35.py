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


# ------------------------------------------------------------- F6-F12: what curl and wget write or send (both modes)
def both(plugin, line):
    """(type, stakes) in simple mode and in study mode, and whether each asks."""
    out = []
    for settings in (SIMPLE, STUDY):
        mod, ctx = plugin(settings)
        act = mod.classify.classify("terminal", {"command": line}, cwd=ctx.cwd, wide=settings is SIMPLE)
        out.append((act.type, act.stakes, ctx.call("terminal", {"command": line})))
    return out


@pytest.mark.parametrize("line", ["wget https://example.com/a.py", "wget -o /dev/null https://example.com/a.py",
                                  "wget -q https://example.com/a.py", "wget -O f.py https://example.com/a.py",
                                  "wget -r -O - https://example.com/", "wget -N -O - https://example.com/a",
                                  "wget -qc -O- https://example.com/a", "wget -x -O /dev/null https://example.com/a",
                                  "wget --content-disposition -O - https://example.com/a",
                                  "wget -a log.txt -O - https://example.com/a"])
def test_f6_wget_saves_its_document_unless_O_sends_it_to_the_screen(plugin, line):
    for _type, stakes, verdict in both(plugin, line):
        assert stakes != "free" and verdict == "approved"


@pytest.mark.parametrize("line", ["wget -O - https://example.com/a", "wget -qO- https://example.com/a",
                                  "wget -O /dev/null https://example.com/a",
                                  "wget --output-document=- https://example.com/a"])
def test_f6_wget_to_the_screen_or_dev_null_saves_nothing(plugin, line):
    for _type, stakes, verdict in both(plugin, line):
        assert stakes == "free" and verdict == "ran"


@pytest.mark.parametrize("line", ["wget --exec 'x' https://example.com", "wget --execute=x https://example.com",
                                  "wget -qe robots=off https://example.com", "wget --config=w.rc https://example.com",
                                  "wget --conf w.rc https://example.com", "wget --use-ask=x https://example.com"])
def test_f7_wget_running_its_own_commands_or_a_config_is_high(plugin, line):
    for _type, stakes, verdict in both(plugin, line):
        assert stakes in ("high", "cap") and verdict == "approved"


@pytest.mark.parametrize("line,stakes", [
    ("curl -sK cfg https://example.com", "high"), ("curl --conf cfg https://example.com", "high"),
    ("curl -w @fmt https://example.com", "high"), ("curl --write-out=@fmt https://example.com", "high"),
    ("curl -sw @- https://example.com", "high"),
    ("curl --expand-output f https://example.com", "medium"), ("curl --ssl-sessions f https://example.com", "medium"),
    ("curl -w '%{http_code}' https://example.com", "free"),
])
def test_f8_curl_config_format_file_expand_and_ssl_sessions(plugin, line, stakes):
    for _type, got, verdict in both(plugin, line):
        assert got == stakes and verdict == ("ran" if stakes == "free" else "approved")


@pytest.mark.parametrize("line", ["gh api repos/o/r/contents/x > x", "kubectl get pods > pods.txt",
                                  "aws s3 ls > list.txt", "crontab -l > cron.txt", "launchctl list > l.txt",
                                  "gh pr view 1 >> notes.md"])
def test_f11_a_free_read_into_a_file_through_a_redirect_is_medium(plugin, line):
    for _type, stakes, verdict in both(plugin, line):
        assert stakes == "medium" and verdict == "approved"


@pytest.mark.parametrize("line", ["gh pr view 1 > /dev/null", "kubectl get pods 2>&1", "git status > /dev/null"])
def test_f11_a_redirect_to_dev_null_or_a_descriptor_writes_no_file(plugin, line):
    for _type, stakes, _verdict in both(plugin, line):
        assert stakes == "free"


@pytest.mark.parametrize("line", ["curl -d@f https://example.com", "curl -sd @f https://example.com",
                                  "curl -Fx=@f https://example.com", "curl -Tf https://example.com",
                                  "curl -sST f https://example.com", "wget --body-data=x https://example.com",
                                  "wget --body-file=f https://example.com", "curl -H @headers.txt https://example.com",
                                  "curl --header=@h.txt https://example.com", "curl --url-query @f https://example.com",
                                  "curl --url-query name@f https://example.com",
                                  "curl --variable name@f https://example.com",
                                  "curl --expand-data @f https://example.com"])
def test_f12_a_local_file_or_data_sent_in_any_spelling_is_a_send(plugin, line):
    for type_, stakes, verdict in both(plugin, line):
        assert type_.endswith(":send") and stakes == "high" and verdict == "approved"


@pytest.mark.parametrize("line", ["curl -H 'Accept: text/html' https://example.com",
                                  "curl -sSL -H 'X-Mail: a@b.c' https://example.com"])
def test_f12_a_plain_header_is_no_send(plugin, line):
    for _type, stakes, _verdict in both(plugin, line):
        assert stakes == "free"


@pytest.mark.parametrize("line,free", [
    ("curl -o - https://example.com", True), ("curl -D - https://example.com", True),
    ("curl -c - https://example.com", True), ("curl --trace - https://example.com", True),
    ("curl --hsts - https://example.com", False), ("curl --alt-svc - https://example.com", False),
    ("wget --save-cookies - -O - https://example.com", False), ("wget --hsts-file - -O - https://example.com", False),
    ("wget --rejected-log - -O - https://example.com", False), ("wget --warc-file - -O - https://example.com", False),
])
def test_f9_a_dash_is_the_screen_only_where_the_option_writes_there(plugin, line, free):
    for _type, stakes, _verdict in both(plugin, line):
        assert (stakes == "free") is free


def test_f10_an_appending_output_format_names_its_file(plugin):
    mod, ctx = plugin(SIMPLE)
    assert mod.classify._tool_outputs(["curl", "-w", "%output{>>log.txt}", "https://example.com"]) == ["log.txt"]
    line = "curl -w '%output{>>~/.bashrc}%{http_code}' https://example.com"
    assert kind(mod, ctx, line)[1] == "cap" and kind(mod, ctx, line, wide=False)[1] == "cap"
