"""Ruling R36, the gaps left in the fail-safe principle of R35: a `cd` to a Hermes level or entry (or to a target that
cannot be resolved) is capped even alone, and the terminal's real working directory is followed from one call to the
next; options glued to their value, `$HERMES_HOME`, same-line assignments, comma-separated mount options, `env -C`,
Hermes found on PATH under another name at each call, code literals, globs, `whence -p`; a `.hermes` folder is a level
only at the top of a home; an archive extracted into the user's home asks."""
import json
import os
import sys
import types

import pytest

from tenure import classify as c
from test_plugin import plugin  # noqa: F401 (fixture)
from test_r35 import ENTRY, code, env, sh  # noqa: F401 (fixture)


def cap(result):
    return result[1] == c.CAP and result[0].startswith(c.PROTECTED)


# ---------------------------------------------------------------------- 1. cd alone, and the cwd between calls
@pytest.mark.parametrize("cmd", ["cd ~/.hermes/plugins", "cd ~/.hermes/plugins/tenure", "pushd ~/.hermes",
                                 "cd ~/.hermes/plugins > /dev/null", "cd ~/.hermes", "cd {H}", "cd {R}/profiles",
                                 "cd {R}/profiles/other", "cd $HERMES_HOME", "cd ${{HERMES_HOME}}/..",
                                 'cd "$(dirname ~/.hermes/config.yaml)"', "cd ~/.herm?s"])
def test_cd_alone_to_a_level_an_entry_or_an_unresolved_target_is_capped(env, cmd):
    assert cap(sh(cmd.format(**env), env["P"])), cmd


def test_cd_to_ordinary_places_stays_free_of_caps(env):
    ws = os.path.join(env["H"], "kanban", "workspaces", "t1")
    for cmd in ["cd ..", "cd src", f"cd {ws}", "cd ~", "cd", "cd -", "cd /tmp && ls", "cd ~/dev/proj && git pull"]:
        assert sh(cmd, env["P"])[1] != c.CAP, cmd


def test_writes_in_a_cwd_that_is_an_entry_are_capped(env):
    plugins = os.path.join(env["H"], "plugins")
    os.makedirs(plugins)
    for cmd in ["tar xf /tmp/e.tar", "git clone https://x/y plugins2", "npm install evil"]:
        assert cap(sh(cmd, plugins)), cmd
    assert c.classify("write_file", {"path": "evil/__init__.py"}, cwd=plugins).stakes == c.CAP


def _result(cwd=None):
    out = {"output": "", "exit_code": 0, "error": None}
    if cwd:
        out["cwd"] = cwd
    return json.dumps(out)


def test_the_terminal_cwd_is_followed_between_calls(plugin, tmp_path):
    mod, ctx = plugin({"preset": "fast"})
    level = os.path.join(os.environ["HERMES_HOME"], "profiles", "coder")
    os.makedirs(level)
    before = len(ctx.prompts)
    assert ctx.call("terminal", {"command": f"cd {level}"}, result=_result(level)) == "approved"
    for cmd in ["tar xf /tmp/e.tar", "git clone https://x/y plugins2"]:
        ctx.call("terminal", {"command": cmd}, answer="deny", result=_result())
        assert ":cap:" in ctx.prompts[-1]["rule_key"], cmd
    assert len(ctx.prompts) - before == 3
    # another session is still in the project
    n = len(ctx.prompts)
    ctx.call("terminal", {"command": "tar xf deps.tar -C ./vendor"}, session="s2", result=_result())
    assert all(":cap:" not in p["rule_key"] for p in ctx.prompts[n:])
    # back in the project: ordinary again
    ctx.call("terminal", {"command": f"cd {ctx.cwd}"}, result=_result(ctx.cwd))
    n = len(ctx.prompts)
    ctx.call("terminal", {"command": "tar xf deps.tar -C ./vendor"}, result=_result())
    assert all(":cap:" not in p["rule_key"] for p in ctx.prompts[n:])


def test_the_terminal_cwd_is_read_from_hermes_when_it_records_one(plugin, monkeypatch):
    mod, ctx = plugin({"preset": "fast"})
    level = os.path.join(os.environ["HERMES_HOME"], "profiles", "coder")
    tools = types.ModuleType("tools")
    term = types.ModuleType("tools.terminal_tool")
    term.get_session_cwd = lambda key: level if key == "s1" else None
    appr = types.ModuleType("tools.approval")
    appr.get_current_session_key = lambda default="": ""
    tools.terminal_tool, tools.approval = term, appr
    for name, m in (("tools", tools), ("tools.terminal_tool", term), ("tools.approval", appr)):
        monkeypatch.setitem(sys.modules, name, m)
    ctx.call("terminal", {"command": "tar xf /tmp/e.tar"}, answer="deny", result=_result())
    assert ":cap:" in ctx.prompts[-1]["rule_key"]


def test_a_workdir_argument_is_the_cwd_of_its_call(plugin):
    mod, ctx = plugin({"preset": "fast"})
    level = os.path.join(os.environ["HERMES_HOME"], "profiles", "coder")
    ctx.call("terminal", {"command": "tar xf /tmp/e.tar", "workdir": level}, answer="deny", result=_result())
    assert ":cap:" in ctx.prompts[-1]["rule_key"]


# ------------------------------------------------------------------------------------------ 2. glued options
@pytest.mark.parametrize("cmd", ["tar xf /tmp/e.tar -C~/.hermes", "tar -xf /tmp/e.tar -C{R}/profiles/other",
                                 "unzip -o /tmp/e.zip -d~/.hermes", "tar -xf /tmp/e.tar -C{H}",
                                 "tar xf /tmp/e.tar --directory={H}"])
def test_options_glued_to_their_value_are_read_as_paths(env, cmd):
    assert cap(sh(cmd.format(**env), env["P"])), cmd


# --------------------------------------------------------------------------------------------------- 3. variables
@pytest.mark.parametrize("cmd", ["cd $HERMES_HOME && tar xf /tmp/e.tar", "cd $HERMES_HOME/.. && tar xf /tmp/e.tar",
                                 'tar xf /tmp/e.tar -C "$HERMES_HOME"', "tar xf /tmp/e.tar -C ${{HERMES_HOME}}",
                                 "D=~/.hermes; tar xf /tmp/e.tar -C $D", "D={R}; tar xf /tmp/e.tar -C ${{D}}/profiles/x",
                                 "export D=~/.hermes && unzip /tmp/e.zip -d $D"])
def test_hermes_home_variable_and_same_line_assignments(env, cmd):
    assert cap(sh(cmd.format(**env), env["P"])), cmd


def test_a_bare_hermes_home_variable_is_a_level_even_in_docker(tmp_path, monkeypatch):
    data = tmp_path / "opt-data"
    data.mkdir()
    monkeypatch.setenv("HOME", str(data))
    monkeypatch.setenv("USERPROFILE", str(data))       # Windows reads the home from USERPROFILE
    monkeypatch.setenv("HERMES_HOME", str(data))
    monkeypatch.delitem(sys.modules, "hermes_constants", raising=False)
    assert cap(sh("tar xf /tmp/e.tar -C $HERMES_HOME", str(data)))
    assert cap(sh("cd $HERMES_HOME", str(data)))


def test_writes_after_an_unknown_cwd_are_at_least_high(env):
    for cmd in ["popd && tar xf /tmp/e.tar", "cd ~nobody && make", "pushd && npm install"]:
        assert c.RANK[sh(cmd, env["P"])[1]] >= c.RANK[c.HIGH], cmd
    assert sh("popd && ls", env["P"])[1] != c.CAP


# ------------------------------------------------------------------------------------------------ 4. --mount commas
@pytest.mark.parametrize("cmd", ["docker run --mount type=bind,src=~/.hermes,dst=/opt/data img",
                                 "docker run --mount type=bind,source=$HOME/.hermes,target=/d img",
                                 "docker run --mount=type=bind,src={H},dst=/d img"])
def test_mount_options_split_on_commas(env, cmd):
    assert cap(sh(cmd.format(**env), env["P"])), cmd


# ----------------------------------------------------------------------------------------------------- 5. env -C
@pytest.mark.parametrize("cmd", ["env -C ~/.hermes tar xf /tmp/e.tar", "env --chdir={H} tar xf /tmp/e.tar",
                                 "env --chdir {R}/profiles/other npm install", "sudo env -C ~/.hermes/plugins make",
                                 "env -C ~/.hermes ls"])
def test_env_chdir_is_a_cd(env, cmd):
    assert cap(sh(cmd.format(**env), env["P"])), cmd


def test_env_chdir_elsewhere_runs_there(env):
    assert sh("env -C src make", env["P"])[1] == c.MEDIUM


# --------------------------------------------------------------------------------- 6. Hermes on PATH, every call
def test_path_names_are_looked_up_at_each_call(env):
    V, U, P = env["V"], env["U"], env["P"]
    os.makedirs(f"{U}/bin")
    assert sh("hh plugins disable tenure", P)[1] != c.CAP          # nothing named hh yet
    os.symlink(f"{V}/bin/hermes", f"{U}/bin/hh")                       # made out of band, no reset
    assert sh("hh plugins disable tenure", P) == ("self:hermes", c.CAP)
    with open(f"{V}/bin/hermes") as src, open(f"{U}/bin/hc", "w") as dst:
        dst.write(src.read())
    os.chmod(f"{U}/bin/hc", 0o755)
    assert sh("hc plugins disable tenure", P) == ("self:hermes", c.CAP)
    os.link(f"{V}/bin/hermes", f"{U}/bin/hl")
    assert sh("hl plugins disable tenure", P) == ("self:hermes", c.CAP)
    assert sh("hl status", P) == ("shell:hermes:status", c.FREE)


def test_a_hard_link_to_a_binary_hermes_is_hermes(env, monkeypatch):
    V, U, P = env["V"], env["U"], env["P"]
    os.makedirs(f"{U}/bin")
    blob = f"{V}/bin/hermes-bin"
    with open(blob, "wb") as f:
        f.write(b"\x7fELF" + b"\0" * 64)
    os.chmod(blob, 0o755)
    os.link(blob, f"{U}/bin/hb")
    monkeypatch.setattr(c, "_hermes_targets", lambda: ({os.path.realpath(blob).lower()}, []))
    assert sh("hb plugins disable tenure", P) == ("self:hermes", c.CAP)


# ------------------------------------------------------------------------------- 7. code literals (execute_code)
@pytest.mark.parametrize("text", ["import tarfile; tarfile.open('/tmp/e.tar').extractall('{U}/.hermes')",
                                  "import shutil,os; shutil.unpack_archive('/tmp/e.zip', "
                                  "os.path.expanduser('~/.hermes'))",
                                  "import shutil; shutil.unpack_archive('/tmp/e.zip', '{H}')",
                                  "import zipfile; zipfile.ZipFile('/tmp/e.zip').extractall(\"{R}/profiles/other\")"])
def test_code_literals_naming_a_level_are_capped(env, text):
    assert cap(code(text.format(**env), env["P"])), text
    assert cap(sh(f'python3 -c "{text.format(**env)}"', env["P"])), text


def test_code_without_hermes_paths_stays_medium(env):
    assert code("import tarfile; tarfile.open('/tmp/e.tar').extractall('./vendor')", env["P"])[1] == c.MEDIUM


# ------------------------------------------------------------------------------------------------------ 8. globs
def test_globs_that_may_reach_a_level_an_entry_or_the_program_are_capped(env):
    V, P = env["V"], env["P"]
    for cmd in ["tar xf /tmp/e.tar -C ~/.herm?s", "tar xf /tmp/e.tar -C ~/.herm[e]s/plugins",
                f"cp {V}/bin/her?es ./h && ./h plugins disable tenure", f"cp {V}/bin/h* ./b",
                "tar xf /tmp/e.tar -C ~/.hermes/plug*", f"unzip /tmp/e.zip -d {env['R']}/profiles/c*"]:
        t = sh(cmd, P)
        assert t[1] == c.CAP, (cmd, t)


def test_ordinary_globs_stay_uncapped(env):
    for cmd in ["rm -f *.pyc", "cp src/*.py build/", "tar czf ../b.tgz src/*", "rm -rf ./build/*"]:
        assert sh(cmd, env["P"])[1] != c.CAP, cmd


# ---------------------------------------------------------------------------------------------- 9. whence and co
@pytest.mark.parametrize("cmd", ["cp $(whence -p hermes) ./h", "cp $(type -p hermes) ./h", "cp $(which hermes) ./h",
                                 "cp $(command -v hermes) ./h", "cp $(whence hermes) ./h", "cp $(which -a hermes) ./h"])
def test_lookups_of_the_program_are_hermes(env, cmd):
    assert sh(cmd, env["P"]) == ("self:hermes", c.CAP), cmd


# --------------------------------------------------------------------------------- 10. a project's .hermes folder
@pytest.mark.parametrize("cmd", ["mkdir -p .hermes", "rm -rf ./build/.hermes",
                                 "mkdir -p ./fixtures/.hermes && cp conf.yaml ./fixtures/.hermes/",
                                 "cd src/.hermes 2>/dev/null || true; ls", "tar xf fx.tar -C tests/.hermes"])
def test_a_hermes_folder_inside_a_project_is_ordinary(env, cmd):
    assert sh(cmd, env["P"])[1] != c.CAP, cmd


def test_a_hermes_folder_at_the_top_of_a_home_is_a_level(env):
    assert cap(sh("mkdir -p ~/.hermes", env["P"]))
    assert cap(sh("git clone https://x/y .hermes", env["U"]))
    assert c._home_level("/root/.hermes") and c._home_level("/home/bob/.hermes") and c._home_level("/Users/b/.hermes")
    assert not c._home_level("/home/bob/proj/.hermes")


# ------------------------------------------------------------------------------- 11. extraction into the user home
@pytest.mark.parametrize("cmd", ["tar xf /tmp/e.tar", "unzip -o /tmp/e.zip", "bsdtar -xf /tmp/e.tar",
                                 "tar --extract -f /tmp/e.tar"])
def test_extracting_an_archive_in_the_user_home_is_high(env, cmd):
    assert c.RANK[sh(cmd, env["U"])[1]] >= c.RANK[c.HIGH], cmd
    assert c.RANK[sh(f"cd ~ && {cmd}", env["P"])[1]] >= c.RANK[c.HIGH], cmd


def test_extracting_elsewhere_stays_medium(env):
    assert sh("tar xf deps.tar", env["P"])[1] == c.MEDIUM
    assert sh("tar czf ../backup.tgz .", env["P"])[1] == c.MEDIUM
    assert sh("tar tf /tmp/e.tar", env["U"])[1] != c.CAP


def test_cd_to_pwd_relative_targets_is_resolved(env):
    assert sh("cd $PWD/src && make", env["P"])[1] == c.MEDIUM
    assert cap(sh("cd $PWD/../user/.hermes", env["P"]))


def test_cd_through_a_cdpath_set_on_the_line_is_capped(env):
    for cmd in ["CDPATH=~/.hermes cd plugins", "export CDPATH=~/.hermes; cd plugins && tar xf /tmp/e.tar"]:
        assert cap(sh(cmd, env["P"])), cmd


def test_programs_installed_beside_a_source_checkout_of_hermes_stay_ordinary(tmp_path, monkeypatch):
    # The official image: Hermes from its sources in /opt/hermes, its venv (python, pip, npm) on PATH.
    top = tmp_path / "opt" / "hermes"
    (top / "hermes_cli").mkdir(parents=True)
    vbin = top / ".venv" / "bin"
    vbin.mkdir(parents=True)
    for name in ("npm", "npx", "python3", "pip", "hermes"):
        (vbin / name).write_text("#!/bin/sh\n")
        (vbin / name).chmod(0o755)
    low = lambda p: str(p).replace("\\", "/").casefold()
    monkeypatch.setitem(c._TARGETS, "v", ({low(os.path.realpath(vbin / "hermes"))}, [low(top / "hermes_cli"), low(top)], set()))
    monkeypatch.setitem(c._TARGETS, "tops", {low(top)})
    monkeypatch.setenv("PATH", str(vbin))
    proj = tmp_path / "proj"
    proj.mkdir()
    for cmd in ("npm test", "npx jest", "python3 -m pytest"):
        assert c.classify("terminal", {"command": cmd}, cwd=str(proj)).type != "self:hermes", cmd
    for cmd in ("pip install requests", "hermes plugins disable tenure", f"{vbin}/hermes config set a b"):
        assert c.classify("terminal", {"command": cmd}, cwd=str(proj)) .stakes == c.CAP, cmd
    assert c.classify("write_file", {"path": str(top / "agent.py")}, cwd=str(proj)).stakes == c.CAP
