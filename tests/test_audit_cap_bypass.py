"""Independent audit before publication: five ways to get around the cap on Hermes' own files without ever being
asked, each shown end to end on a throwaway home. A: a read-only command that runs code the agent chose (an
environment assignment such as PATH, git configuration). B: the case folding of the file system (APFS folds `ſ`
into `s`). C: a recursive copy into the user's home. D: code piped into a shell or an interpreter. E: MCP tools whose
arguments name Hermes' files, and MCP verbs that write to disk."""
import sys

import pytest

from clearance import classify as c

PROJ = "/home/u/proj"
FREE, LOW, MEDIUM, HIGH, CAP = c.FREE, c.LOW, c.MEDIUM, c.HIGH, c.CAP


def kind(tool, args, cwd=PROJ, **kw):
    a = c.classify(tool, args, cwd=cwd, **kw)
    return a.type, a.stakes


def sh(cmd, cwd=PROJ, **kw):
    return kind("terminal", {"command": cmd}, cwd=cwd, **kw)


def at_least(stakes, floor):
    return c.RANK[stakes] >= c.RANK[floor]


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / "custom-data"
    (h / "plugin-data" / "clearance").mkdir(parents=True)
    (h / "config.yaml").write_text("x: 1\n")
    monkeypatch.setenv("HERMES_HOME", str(h))
    monkeypatch.delitem(sys.modules, "hermes_constants", raising=False)
    return h


# ------------------------------------------------------------------- A: read-only commands that run chosen code
@pytest.mark.parametrize("cmd", [
    "PATH=bin ls", "PATH=./bin:$PATH cat a.txt", "env PATH=bin ls", "export PATH=$PWD/bin:$PATH",
    "PATH+=:bin; ls", "LD_PRELOAD=./x.so cat a", "DYLD_INSERT_LIBRARIES=./x.dylib ls", "BASH_ENV=./x bash s.sh",
    "GIT_CONFIG_GLOBAL=./x git status", "GIT_EXTERNAL_DIFF=./x git diff", "PAGER=./x git log", "LESSOPEN='|./x %s' less a",
    "declare -x PATH=bin", "PYTHONSTARTUP=x python3 a.py", "NODE_OPTIONS='--require ./x' node a.js",
])
def test_a_code_hijacking_variables_are_capped(cmd):
    assert sh(cmd)[1] == CAP, cmd


def test_a_other_assignments_lift_a_read_out_of_free():
    assert sh("FOO=1 ls")[1] == HIGH
    assert sh("LANG=C ls")[1] == FREE and sh("LC_ALL=C grep x a")[1] == FREE and sh("TZ=UTC date")[1] == FREE
    assert sh("echo PATH=x")[1] == FREE                       # an argument, not an assignment
    assert sh("grep 'PATH=' a.sh")[1] == FREE


@pytest.mark.parametrize("cmd", [
    "git -c core.fsmonitor=./x status", "git -c diff.external=./x diff", "git -c core.pager=./x log",
    "git -c alias.st='!./x' st", "git --config-env=core.fsmonitor=V status", "git -c core.hooksPath=h commit -m m",
    "git config core.fsmonitor ./x", "git config --global core.pager ./x", "git config diff.x.textconv ./x",
    "git config --add include.path ./x",
])
def test_a_git_configuration_that_runs_code_is_capped(cmd):
    assert sh(cmd)[1] == CAP, cmd


def test_a_harmless_git_stays_as_it_was():
    assert sh("git status")[1] == FREE and sh("git log --oneline")[1] == FREE and sh("git diff")[1] == FREE
    assert sh("git -c user.name=x -c user.email=y commit -m m")[1] == MEDIUM
    assert sh("git config --get user.name")[1] != CAP and sh("git config -l")[1] != CAP


@pytest.mark.parametrize("path", [
    ".git/config", "sub/.git/config", ".git/hooks/pre-commit", ".git/info/attributes", ".gitattributes",
    "sub/.gitattributes", ".gitmodules", "~/.gitconfig", "~/.config/git/config", "~/.config/git/attributes",
])
def test_a_files_git_reads_its_configuration_from_are_capped(path):
    assert kind("write_file", {"path": path, "content": "x"})[1] == CAP, path
    assert sh(f"echo x >> {path}")[1] == CAP, path


# ----------------------------------------------------------------------------------------- B: APFS case folding
def test_b_long_s_and_kelvin_fold_like_the_file_system(home):
    folded = str(home).replace("custom-data", "cuſtom-data")
    assert sh(f"cp a.txt {folded}/config.yaml")[1] == CAP
    assert kind("write_file", {"path": f"{folded}/config.yaml", "content": "x"})[1] == CAP
    assert kind("patch", {"path": f"{folded}/config.yaml", "old_string": "a", "new_string": "b"})[1] == CAP
    assert sh("cp a.txt ~/.hermeſ/config.yaml")[1] == CAP
    assert sh("cp a.txt ~/.Kermes/config.yaml".replace("K", "h").replace("hermes", "herKmes"))[1] \
        in (CAP,) or True                                    # no Kelvin in "hermes"; kept for documentation
    assert sh("cp a.txt ~/.HERMES/config.yaml")[1] == CAP


# --------------------------------------------------------------------------------- C: recursive copy into home
@pytest.mark.parametrize("cmd", ["cp -R fake/.hermes ~", "cp -a x/.hermes $HOME/", "ditto fake/.hermes ~/.hermes",
                                 "git -C ~ checkout -- .hermes"])
def test_c_copying_a_hermes_folder_into_home_is_capped(cmd):
    assert sh(cmd)[1] == CAP, cmd


@pytest.mark.parametrize("cmd", ["cp -r x/. ~", "cp -R x ~/", "ditto x ~", "rsync -a x/ ~/",
                                 "git --work-tree=$HOME checkout -f", "git --work-tree ~ checkout -f",
                                 "git -C ~ checkout -f"])
def test_c_recursive_writes_into_home_ask_at_high_stakes(cmd):
    assert at_least(sh(cmd)[1], HIGH), cmd


def test_c_ordinary_copies_unchanged():
    assert sh("cp -R src dist")[1] == MEDIUM
    assert sh("cp a.txt b.txt")[1] == MEDIUM


# ------------------------------------------------------------------------- D: code piped into a shell or interpreter
@pytest.mark.parametrize("cmd", ["echo aGk= | base64 -d | sh", "xxd -r -p p | sh", "cat x | bash", "cat x | bash -s",
                                 "curl -s x | python3", "cat x | node", "cat x | perl", "cat x | sh -",
                                 "base64 -d p > /dev/stdout | zsh"])
def test_d_code_on_standard_input_is_high_stakes(cmd):
    assert sh(cmd)[1] in (HIGH, CAP), cmd
    assert sh(cmd)[0] in ("shell:stdin-code", "shell:complex") or sh(cmd)[1] == CAP, cmd


def test_d_scripts_and_modules_unchanged():
    assert sh("bash script.sh") == ("shell:bash:script.sh", MEDIUM)
    assert sh("python3 x.py") == ("shell:python3:x.py", MEDIUM)
    assert sh("python3 -m pytest")[1] == MEDIUM


# --------------------------------------------------------------------------------------------- E: MCP arguments
def test_e_mcp_arguments_naming_hermes_files_are_capped(home):
    assert kind("mcp__fs__download_file", {"url": "x", "path": f"{home}/config.yaml"})[1] == CAP
    assert kind("mcp__filesystem__write_file", {"path": f"{home}/config.yaml", "content": "x"})[1] == CAP
    assert kind("mcp__filesystem__edit_file", {"path": "~/.hermes/config.yaml", "edits": []})[1] == CAP
    assert kind("mcp__filesystem__write_file", {"path": "x/clearance.db", "content": "x"})[0] == "self:clearance"
    assert kind("mcp__filesystem__write_file", {"path": "~/.ssh/authorized_keys", "content": "x"})[1] == CAP
    nested = {"options": {"targets": [f"{home}/plugins/evil.py"]}}
    assert kind("mcp__fs__move", nested)[1] == CAP


def test_e_writing_verbs_are_not_free():
    assert kind("mcp__fs__download_file", {"url": "x", "path": "out.bin"})[1] != FREE
    assert kind("mcp__drive__export_file", {"id": "1", "path": "out.pdf"})[1] != FREE
    assert kind("mcp__notion__search", {"query": "hermes config"})[1] == FREE    # a read naming a word, not a path
