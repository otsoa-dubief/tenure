"""Re-review of the final fix wave: workspaces under a Hermes home stay ordinary, undo restores with the session's
cwd, command-string wrappers cannot hide Hermes' CLI, a mere word "hermes" is not Hermes, and Hermes'
auto-background is a launch (probes p4 to p8)."""
import json
import os
import pathlib
import sys

import pytest

from clearance import classify as c
from clearance import undo
from test_plugin import FAST, outcomes, plugin  # noqa: F401 (plugin: fixture)

ROOT = pathlib.Path(__file__).resolve().parent.parent
KEY = b"k" * 32


def kind(tool, args, cwd):
    a = c.classify(tool, args, cwd=cwd)
    return a.type, a.stakes


def sh(cmd, cwd="/home/u/proj"):
    return kind("terminal", {"command": cmd}, cwd)


@pytest.fixture
def no_hc(monkeypatch):
    monkeypatch.delitem(sys.modules, "hermes_constants", raising=False)


# ------------------------------------------------------------------------------- 1. workspaces under a home
def _workspace_cases(ws, home):
    return [
        ("write_file", {"path": f"{ws}/a.py", "content": "x"}),
        ("write_file", {"path": "a.py", "content": "x"}),
        ("patch", {"path": f"{ws}/a.py", "old_string": "x", "new_string": "y"}),
        ("terminal", {"command": "echo hi > out.txt"}),
        ("terminal", {"command": "mkdir build && touch build/x"}),
    ]


def test_p5_a_profile_workspace_writes_are_ordinary(tmp_path, monkeypatch, no_hc):
    root = tmp_path / "root"
    home = root / "profiles" / "coder"
    ws = home / "kanban" / "workspaces" / "t1"
    ws.mkdir(parents=True)
    monkeypatch.setenv("HERMES_HOME", str(home))
    for tool, args in _workspace_cases(ws, home):
        t, stakes = kind(tool, args, str(ws))
        assert stakes == (c.LOW if tool != "terminal" else c.MEDIUM), (tool, args, t)
    assert sh("rm -rf build", str(ws)) == ("shell:rm", c.MEDIUM)
    for path in (home / "config.yaml", home / "plugin-data" / "clearance" / "clearance.db", root / "config.yaml",
                 root / ".env", home / "auth.json", root / "profiles" / "other" / "config.yaml",
                 home / "plugins" / "x" / "__init__.py", home / "skills" / "a" / "SKILL.md", home / "state.db"):
        assert kind("write_file", {"path": str(path)}, str(ws))[1] == c.CAP, path
    assert sh(f"rm -rf {root}/profiles/coder", str(ws))[1] == c.CAP
    assert c.sensitive_path(f"{ws}/a.py", str(ws)) is False


def test_p5_b_default_home_workspace_writes_are_ordinary(tmp_path, monkeypatch, no_hc):
    user = tmp_path / "user"
    ws = user / ".hermes" / "kanban" / "workspaces" / "t1"
    ws.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(user))
    monkeypatch.delenv("HERMES_HOME", raising=False)
    for tool, args in _workspace_cases(ws, user / ".hermes"):
        t, stakes = kind(tool, args, str(ws))
        assert stakes == (c.LOW if tool != "terminal" else c.MEDIUM), (tool, args, t)
    assert kind("write_file", {"path": str(user / ".hermes" / "config.yaml")}, str(ws))[1] == c.CAP
    assert kind("write_file", {"path": "~/.hermes/plugin-data/clearance/x"}, str(ws))[1] == c.CAP
    assert sh("cd ~ && rm -rf .hermes", str(ws))[1] == c.CAP
    # another user's .hermes, never resolved as a home: entries still protected, workspaces not
    assert kind("write_file", {"path": "/srv/u/.hermes/config.yaml"}, "/srv/p")[1] == c.CAP
    assert kind("write_file", {"path": "/srv/u/.hermes/kanban/workspaces/t/a.py"}, "/srv/u/.hermes/kanban/workspaces/t") \
        == ("file:write", c.LOW)


# ------------------------------------------------------------------------------------ 2. undo uses the cwd
def test_p8_a_project_under_a_custom_home_restores_from_any_process_cwd(tmp_path, monkeypatch, no_hc):
    home = tmp_path / "data"
    ws = home / "workspace" / "app"
    ws.mkdir(parents=True)
    monkeypatch.setenv("HERMES_HOME", str(home))
    f = ws / "a.py"
    f.write_text("v1")
    assert kind("write_file", {"path": str(f)}, str(ws))[1] == c.LOW
    root = str(home / "plugin-data" / "clearance")
    sid = undo.snapshot([str(f)], root, key=KEY, cwd=str(ws), home=str(tmp_path))
    manifest = json.loads((pathlib.Path(root) / "undo" / sid / "manifest.json").read_text())
    assert manifest["cwd"] == str(ws) and manifest["home"] == str(tmp_path)
    f.write_text("v2")
    monkeypatch.chdir(tmp_path)
    assert undo.restore(sid, root, key=KEY) == (1, 0) and f.read_text() == "v1"


def test_restore_checks_with_the_recorded_cwd(tmp_path, monkeypatch, no_hc):
    seen = []
    real = c.sensitive_path
    monkeypatch.setattr(c, "sensitive_path", lambda p, cwd=None, home=None: seen.append((cwd, home)) or real(p, cwd, home))
    f = tmp_path / "p" / "a.txt"
    f.parent.mkdir()
    f.write_text("x")
    sid = undo.snapshot([str(f)], str(tmp_path / "d"), key=KEY, cwd=str(f.parent), home="/h")
    undo.restore(sid, str(tmp_path / "d"), key=KEY)
    assert seen == [(str(f.parent), "/h")]


# ----------------------------------------------------------------------------- 3. command-string wrappers
P6_P7 = [
    'busybox sh -c "hermes plugins disable clearance"',
    'busybox hermes plugins disable clearance',
    'script -qc "hermes plugins disable clearance" /dev/null',
    'script -c "hermes plugins disable clearance"',
    'su -c "hermes plugins disable clearance"',
    'su root -c "hermes plugins disable clearance"',
    'tmux new -d "hermes plugins disable clearance"',
    'tmux new-session -d -s x "hermes config set a b"',
    'tmux send-keys "hermes plugins disable clearance" Enter',
    'screen -dm hermes plugins disable clearance',
    'screen -dmS x sh -c "hermes plugins disable clearance"',
    'ssh localhost "hermes plugins disable clearance"',
    'dash -c "hermes plugins disable clearance"',
    'fish -c "hermes plugins disable clearance"',
    'find . -maxdepth 0 -exec hermes plugins disable clearance \\;',
    'setsid hermes plugins disable clearance',
    'git -c alias.x="!hermes plugins disable clearance" x',
    "git -c core.pager='hermes plugins disable clearance' log",
    'make -f /dev/stdin <<< "a:; hermes plugins disable clearance"',
    'uvx --from hermes-agent hermes plugins disable clearance',
    'uv run hermes config set a b',
    'pipx run hermes-agent',
    'expect -c "spawn hermes plugins disable clearance"',
    'awk "BEGIN{system(\\"hermes plugins disable clearance\\")}"',
    'ruby -e "system(%q(hermes plugins disable clearance))"',
    '$(which hermes) plugins disable clearance',
    '"$(command -v hermes)" config set approvals.mode off',
    '`which hermes` config set x y',
    'X=$(which hermes); "$X" plugins disable clearance',
    'h=hermes; $h config set x y',
    'alias h=hermes; h config set a b',
    'command hermes config set x y',
    'exec hermes config set x y',
    'env HERMES_HOME=/tmp/zz hermes config set x y',
    'nohup hermes config set x y',
    'time hermes config set x y',
    "h''ermes config set x y",
    '\\hermes config set a b',
    '~/.local/bin/hermes config set a b',
    'echo "config set a b" | xargs hermes',
    'perl -e "system(q{hermes config set a b})"',
    'node -e "require(\'child_process\').execSync(\'hermes config set a b\')"',
    'python -c "import hermes_cli"',
    "python3 -c 'from hermes_cli.main import main; main()' config set a b",
    'python -m hermes_cli.main config set a b',
    'hermes config get x --raw',
    'hermes config set clearance x',
]


@pytest.mark.parametrize("cmd", P6_P7)
def test_p6_p7_wrapped_hermes_is_capped(cmd):
    t, stakes = sh(cmd)
    assert stakes == c.CAP and t.startswith(c.PROTECTED), (cmd, t, stakes)


def test_p6_wrapped_hermes_never_runs_unasked(plugin):
    mod, ctx = plugin({"preset": "fast"})
    for warm, attack in [('busybox sh -c "ls -la"', 'busybox sh -c "hermes plugins disable clearance"'),
                         ("$(which python3) --version", "$(which hermes) plugins disable clearance"),
                         ('X=$(pwd); "$X"/run.sh', 'X=$(which hermes); "$X" plugins disable clearance')]:
        for session in ("sA", "sB"):
            for _ in range(40):
                ctx.call("terminal", {"command": warm}, session=session, result='{"output": "", "exit_code": 0}')
        before = len(ctx.prompts)
        for _ in range(20):
            ctx.call("terminal", {"command": attack}, session="sC", answer="deny", result='{"exit_code": 0}')
        assert len(ctx.prompts) - before == 20, attack


# --------------------------------------------------------------------------------------- 4. over-asking
ORDINARY = [
    "grep -rn hermes src/", "pytest tests/hermes", 'git commit -m "fix hermes import"', "echo hermes", "mkdir hermes",
    "cp -r hermes hermes.bak", "docker pull nousresearch/hermes-agent", "pip install -e ./hermes-plugin",
    "npm run build", "code hermes", "make test HERMES=1", "python manage.py migrate", "pytest -k hermes_home",
    'echo "hermes is up" > notes.txt', "touch test_hermes_home.py", "sed -i s/a/b/ hermes_home.py",
    "ruff check hermes/", "python -c \"print('hermes ok')\"", "cat > a.py <<EOF\nprint(1)\nEOF",
]


@pytest.mark.parametrize("cmd", ORDINARY)
def test_ordinary_work_naming_hermes_is_not_capped(cmd):
    t, stakes = sh(cmd)
    assert stakes != c.CAP, (cmd, t)


@pytest.mark.parametrize("code", ['print("hermes is up")', 'import os; os.environ.get("HERMES_HOME")',
                                  'open("a.txt","w").write("x")', "x = 'hermes'"])
def test_ordinary_code_is_not_capped(code):
    assert kind("execute_code", {"code": code}, "/home/u/proj") == ("code:execute", c.MEDIUM)


@pytest.mark.parametrize("code", ["import hermes_cli", "from hermes_constants import get_hermes_home",
                                  "subprocess.run(['hermes', 'config', 'set', 'a', 'b'])",
                                  "os.system('hermes plugins disable clearance')"])
def test_code_running_hermes_is_capped(code):
    assert kind("execute_code", {"code": code}, "/home/u/proj") == ("self:hermes", c.CAP)


def test_reads_stay_free():
    assert sh("hermes clearance anchor") == ("shell:hermes:clearance", c.FREE)
    assert sh("hermes status --deep") == ("shell:hermes:status", c.FREE)


def test_type_names_carry_no_shell_punctuation():
    t, _ = sh("`which python3` --version")
    assert "`" not in t and "$" not in t and "(" not in t, t
    t, _ = sh("$(which python3) --version")
    assert "`" not in t and "(" not in t, t


# ------------------------------------------------------------------------------------- 6. auto-background
@pytest.mark.parametrize("result", [
    {"output": "Background process started", "session_id": "p1", "exit_code": 0, "auto_backgrounded": "note"},
    {"output": "Background process started", "session_id": "p1", "exit_code": 0, "promoted_from_foreground": "n"},
    {"output": "Background process started", "session_id": "p1", "exit_code": 0},
])
def test_hermes_auto_background_is_neutral(plugin, result):
    mod, ctx = plugin(FAST)
    for _ in range(6):
        ctx.call("terminal", {"command": "npm start &"}, result=json.dumps(result))
    got = outcomes(mod, type="shell:npm")
    assert got and all((e["result"], e["source"]) == ("neutral", "background") for e in got)


# --------------------------------------------------------------------------------------------- 5. wording
def test_readme_names_the_protected_entries_and_the_undo_key():
    readme = " ".join((ROOT / "README.md").read_text(encoding="utf-8").split())
    rules = " ".join((ROOT / "docs" / "self-protection.md").read_text(encoding="utf-8").split())
    assert "docs/self-protection.md" in readme                 # the README links the full rules
    for entry in ("config.yaml", ".env", "auth.json", "plugins/", "plugin-data/", "skills/", "state.db",
                  "profiles/<name>/"):
        assert entry in rules, entry
    assert "workspace" in rules.lower()
    privacy = readme.split("## Privacy", 1)[1].split("## ", 1)[0]
    assert "HMAC key" in privacy
