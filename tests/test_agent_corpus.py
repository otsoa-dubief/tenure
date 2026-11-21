"""The agent corpus (tests/agent_corpus.py) played in simple mode: each line in a fresh project holding its files,
through the hooks as Hermes runs them, compared with what the rule decided says. A known gap is an xfail that says
why it is left; a gap that touches safety is listed, not fixed here. Hermes' own questions are checked against its
dangerous-command check when its source is found (HERMES_AGENT_DIR), skipped otherwise."""
import os
import subprocess
import sys

import pytest

from agent_corpus import CORPUS, FILES, WROTE
from friction import _hermes_detect
from test_plugin import plugin  # noqa: F401  (plugin is a fixture)

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the commands are POSIX")

DETECT = _hermes_detect()
SETTINGS = {"start": "trusted", "mode": "simple"}               # what a new owner gets

# Where the code differs from the rule, and why it is left as it is.
GAPS = {
    "find . -name '*.py' -exec grep -l TODO {} +":
        "safety: find -exec runs a program per file; reading it as a read means trusting the -exec command line",
    "curl -sSo src/app.py https://example.com/app.py":
        "safety: curl -o overwrites a project file with outside content, read as a free curl, nothing saved",
    "sed -i '' 's/old_name/new_name/g' src/*.py" if sys.platform == "darwin" else
    "sed -i 's/old_name/new_name/g' src/*.py":
        "safety: sed's glob targets would need the rm glob reading (last part only, any glob option) to be saved",
    "mkdir -p tests/unit && cat > tests/unit/test_x.py <<'EOF'\ndef test_x():\n    assert True\nEOF":
        "bigger: a heredoc after a mkdir in the same line; its folder does not exist yet, so it cannot be saved now",
}


def project(ctx):
    for name, text in FILES.items():
        path = os.path.join(ctx.cwd, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com"]
    for args in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "start"]):
        subprocess.run(git + args, cwd=ctx.cwd, check=True, capture_output=True)


def why(mod, act, message: str) -> str:
    """Why tenure asked, in the corpus' words, read from the kind it gave and its message (English)."""
    parts = act.type.split(":")
    if mod.classify.NEW_DEPENDENCY in parts:
        return "dependency"
    if "now runs it" in message or act.type == "shell:stdin-code" or parts[-1] == "inline":
        return "script"
    if "discard" in parts:
        return "no-undo"
    if not mod.params.simple_covers(act.type) or (act.stakes == "high" and act.type not in ("file:unknown",
                                                                                           "shell:rm")):
        return "outside"
    return "no-undo"


def outcome(mod, ctx, line: str) -> str:
    """What simple mode does with the line: free, free+undo or asks:<why>."""
    for path, text in WROTE.get(line, {}).items():
        assert ctx.call("write_file", {"path": path, "content": text}) == "ran"
    act = mod.classify.classify("terminal", {"command": line}, cwd=ctx.cwd, wide=True)
    last = lambda: mod.store_().db.execute("SELECT MAX(id) FROM undo").fetchone()[0]     # noqa: E731
    asked, before = len(ctx.prompts), last()
    ctx.call("terminal", {"command": line})
    if len(ctx.prompts) > asked:
        return "asks:" + why(mod, act, ctx.prompts[-1]["message"])
    return "free+undo" if last() != before else "free"


def _params():
    for family, line, expected in CORPUS:
        marks = [pytest.mark.xfail(reason=GAPS[line], strict=True)] if line in GAPS else []
        yield pytest.param(line, expected, id=f"{family}:{line.splitlines()[0][:60]}", marks=marks)


@pytest.mark.parametrize("line,expected", list(_params()))
def test_the_corpus_line_does_what_the_rule_says(plugin, line, expected):
    if expected == "hermes-asks":
        if DETECT is None:
            pytest.skip("Hermes' source is not here (HERMES_AGENT_DIR)")
        assert DETECT(line), "Hermes' own check does not ask"
        return
    if DETECT is not None:
        assert not DETECT(line), "Hermes asks by itself: the expected outcome is hermes-asks"
    mod, ctx = plugin(SETTINGS)
    project(ctx)
    assert outcome(mod, ctx, line) == expected


def test_the_corpus_covers_every_family_and_outcome():
    families = {f for f, _l, _e in CORPUS}
    assert families == {"tests", "reads", "edits", "deletions", "git", "installs", "network", "mixed"}
    kinds = {e for _f, _l, e in CORPUS}
    assert {"free", "free+undo", "hermes-asks", "asks:outside", "asks:no-undo", "asks:dependency",
            "asks:script"} <= kinds
    assert len(CORPUS) >= 60 and len({line for _f, line, _e in CORPUS}) == len(CORPUS)
    assert set(GAPS) <= {line for _f, line, _e in CORPUS} and set(WROTE) <= {line for _f, line, _e in CORPUS}


@pytest.mark.parametrize("scripts,ok", [
    (["'s/a/b/'", "'s/c/d/g'"], True), (["'s/a/b/'", "'/^#/d'"], True), (["'s/a/b/'", "'w out.txt'"], False),
    (["'s/a/b/'", "'1r other.txt'"], False), (["'s/a/b/'", "'e date'"], False), (["'s/a/b\\'", "'/'"], False),
    (["'{'", "'s/a/b/'", "'}'"], False),
])
def test_sed_in_place_with_several_scripts_saves_its_file_only_when_each_and_all_are_plain(plugin, scripts, ok):
    from agent_corpus import SED_I
    mod, ctx = plugin(SETTINGS)
    project(ctx)
    line = SED_I + " ".join("-e " + s for s in scripts) + " src/app.py"
    found = mod.classify.files_written("terminal", {"command": line}, ctx.cwd, wide=True)
    assert (found == [os.path.join(ctx.cwd, "src", "app.py")]) == ok
