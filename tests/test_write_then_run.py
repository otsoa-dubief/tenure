"""Write then run (audit 19/11, item 3): a script the agent wrote asks once before it runs; adding a package from a
registry is its own kind, outside the trusted start, and suspends the session; after outside content, files that run
when a tool runs ask before they change."""
import os

import pytest

from test_plugin import FAST, NPM, plugin, state, write  # noqa: F401
from test_trust import TRUST
from tenure import classify as C, params

POSIX = pytest.mark.skipif(os.name == "nt", reason="POSIX paths")


@pytest.mark.parametrize("cmd,new", [
    ("npm install left-pad", True), ("npm i -D foo", True), ("pnpm add x", True), ("yarn add x", True),
    ("pip install requests", True), ("python -m pip install x", True), ("uv add httpx", True),
    ("uv pip install x", True), ("poetry add x", True), ("cargo add serde", True), ("go get x/y", True),
    ("cd a && npm install lodash", True), ("FOO=1 npm install lodash", True),
    ("npm install", False), ("npm ci", False), ("pip install -r requirements.txt", False), ("pip install -e .", False),
    ("pip install .", False), ("pip install ./dist/x.whl", False), ("npm test", False), ("yarn", False),
])
def test_adds_dependency(cmd, new):
    assert bool(C.adds_dependency(cmd)) is new
    t = C.classify("terminal", {"command": cmd}, cwd="/tmp/p").type
    assert (t.endswith(":new-dependency")) is new, t
    assert params.trust_covers(t) is not new or t.startswith("shell:cd")


@POSIX
def test_scripts_run():
    assert C.scripts_run("python cleanup.py && ./run.sh; npm test; make build; python -m pytest; "
                         "bash -c 'x'; node src/a.js; sh -e x.sh", "/p") == [
        "/p/cleanup.py", "/p/run.sh", "/p/package.json", "/p/Makefile", "/p/src/a.js", "/p/x.sh"]


@pytest.mark.parametrize("path,runs", [
    ("package.json", True), ("Makefile", True), ("conftest.py", True), ("tests/conftest.py", True),
    ("scripts/x.sh", True), (".github/workflows/ci.yml", True), ("pyproject.toml", True), (".git/hooks/pre-commit", True),
    ("src/app.py", False), ("README.md", False), ("data.json", False),
])
def test_runs_on_execution(path, runs):
    assert C.runs_on_execution(path) is runs


def test_a_script_the_agent_wrote_asks_once_before_it_runs(plugin):
    mod, ctx = plugin(TRUST)
    assert ctx.call("write_file", {"path": "cleanup.py", "content": "print(1)\n"}) == "ran"
    assert ctx.call("terminal", {"command": "python cleanup.py"}) == "approved"     # asked once
    assert "wrote cleanup.py" in ctx.prompts[-1]["message"] or "cleanup.py" in ctx.prompts[-1]["message"]
    assert ctx.call("terminal", {"command": "python cleanup.py"}) == "ran"          # then trusted again
    assert ctx.call("write_file", {"path": "cleanup.py", "content": "print(2)\n"}) == "ran"
    assert ctx.call("terminal", {"command": "python cleanup.py"}) == "approved"     # rewritten: asked again


def test_a_refused_fresh_script_asks_again(plugin):
    mod, ctx = plugin(TRUST)
    ctx.call("write_file", {"path": "x.py", "content": "print(1)\n"})
    assert ctx.call("terminal", {"command": "python x.py"}, answer="deny") == "refused"
    assert ctx.call("terminal", {"command": "python x.py"}) == "approved"


def test_a_script_the_owner_wrote_runs_as_before(plugin):
    mod, ctx = plugin(TRUST)
    with open(os.path.join(ctx.cwd, "mine.py"), "w") as f:
        f.write("print(1)\n")
    assert ctx.call("terminal", {"command": "python mine.py"}) == "ran"


def test_npm_test_after_the_agent_changed_package_json_asks_once(plugin):
    mod, ctx = plugin(TRUST)
    assert ctx.call("terminal", NPM) == "ran"
    ctx.call("write_file", {"path": "package.json", "content": '{"scripts": {"test": "rm -rf ~"}}'})
    assert ctx.call("terminal", NPM) == "approved"
    assert ctx.call("terminal", NPM) == "ran"


def test_a_new_dependency_asks_and_suspends_the_session(plugin):
    mod, ctx = plugin(TRUST)
    assert ctx.call("terminal", {"command": "npm install left-pad"}) == "approved"
    assert mod.store_().is_tainted(mod.anon("s1")) or "s1" in str(mod.ST.tainted) or mod._suspended(
        mod.store_(), mod.anon("s1"))


def test_after_outside_content_build_files_ask_but_source_files_keep_their_undo(plugin):
    mod, ctx = plugin(TRUST)
    ctx.call("web_search", {"query": "x"})
    assert ctx.call("write_file", write("plain")) in ("ran",)                      # undo kept
    assert ctx.call("write_file", {"path": "package.json", "content": "{}"}) == "approved"
    assert ctx.call("write_file", {"path": "tests/conftest.py", "content": "x = 1\n"}) == "approved"
    assert "package.json" in ctx.prompts[-2]["message"]
