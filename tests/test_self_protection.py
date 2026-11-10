"""Self-protection: an agent can never clear its way to turning clearance off, editing Hermes' configuration or the
plugin's own data, wherever the Hermes home lives. Also the suspension list and execute_code's sensitive floor."""
import os
import sys
import types

import pytest

from clearance import classify as c

PROJ = "/home/u/proj"


def kind(tool, args, cwd=PROJ, **kw):
    a = c.classify(tool, args, cwd=cwd, **kw)
    return a.type, a.stakes


def sh(cmd, cwd=PROJ, **kw):
    return kind("terminal", {"command": cmd}, cwd=cwd, **kw)


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A custom Hermes home outside the default ~/.hermes, as in Docker (/opt/data) or with HERMES_HOME set."""
    h = tmp_path / "custom-data"
    (h / "plugin-data" / "clearance" / "undo" / "x").mkdir(parents=True)
    monkeypatch.setenv("HERMES_HOME", str(h))
    monkeypatch.delitem(sys.modules, "hermes_constants", raising=False)
    return h


# ------------------------------------------------------------------------------------------------- C1: hermes CLI
WRITES = [
    "hermes config set plugins.entries.clearance.settings.enabled false",
    "hermes config set approvals.mode off",
    "hermes config edit",
    "hermes config unset plugins.entries.clearance",
    "hermes config migrate",
    "hermes plugins disable clearance",
    "hermes plugins uninstall clearance",
    "hermes plugins install ./evil",
    "hermes clearance strict off",
    "hermes clearance setup fast",
    "hermes clearance revoke all",
    "hermes clearance flag shell:npm:test",
    "hermes clearance undo 3",
    "hermes clearance cleanup",
    "hermes clearance passport --out x.json",
    "hermes profile create x",
    "hermes profiles list",
    "hermes gateway restart",
    "hermes update",
    "hermes auth add openrouter",
    "hermes setup",
    "hermes model",
    "hermes login",
    "hermes logout",
    "hermes uninstall",
    "hermes install",
    "hermes",
    "hermes -z 'disable clearance'",
    "hermes --yolo status",
    "hermes chat -q hi",
    "hermes some-future-subcommand",
    "hermes config get",                        # malformed: not the read shape
    "hermes config get model --raw",            # prints credentials unmasked
    "hermes config check",
    "hermes status --set x",
    "/usr/local/bin/hermes config set a b",
    "sudo hermes plugins disable clearance",
    "HERMES_HOME=/x hermes config set a b",
    "python -m hermes_cli config set a b",
    "python3 -m hermes_cli.main plugins disable clearance",
    "python3 -m hermes_cli status",
    "uv run hermes config set a b",
    "bash -c 'hermes plugins disable clearance'",
    "echo y | hermes plugins uninstall clearance",
    "find . -name x -exec hermes config set a b \\;",
    "hermes-agent",
]
READS = [
    ("hermes status", "shell:hermes:status"),
    ("hermes status --all", "shell:hermes:status"),
    ("hermes --version", "shell:hermes:version"),
    ("hermes -V", "shell:hermes:version"),
    ("hermes config get approvals.mode", "shell:hermes:config"),
    ("hermes config show", "shell:hermes:config"),
    ("hermes config path", "shell:hermes:config"),
    ("hermes config get model --json", "shell:hermes:config"),
    ("hermes clearance", "shell:hermes:clearance"),
    ("hermes clearance status", "shell:hermes:clearance"),
    ("hermes clearance status --all --model gpt-5", "shell:hermes:clearance"),
    ("hermes clearance models", "shell:hermes:clearance"),
    ("hermes clearance models --type file:write", "shell:hermes:clearance"),
    ("hermes clearance explain", "shell:hermes:clearance"),
    ("hermes clearance verify p.json", "shell:hermes:clearance"),
    ("hermes clearance verify p.json ledger.jsonl", "shell:hermes:clearance"),
    ("hermes clearance anchor", "shell:hermes:clearance"),
]


@pytest.mark.parametrize("cmd", WRITES)
def test_hermes_writes_and_unknown_subcommands_are_capped(cmd):
    assert sh(cmd) == ("self:hermes", c.CAP), cmd


@pytest.mark.parametrize("cmd,typ", READS)
def test_read_only_hermes_invocations_stay_free(cmd, typ):
    assert sh(cmd) == (typ, c.FREE), cmd


def test_clearance_export_is_a_file_write():
    assert sh("hermes clearance export") == ("shell:hermes:clearance:export", c.LOW)
    assert sh("hermes clearance export out.jsonl") == ("shell:hermes:clearance:export", c.LOW)
    assert sh("hermes clearance export /tmp/out.jsonl") == ("shell:hermes:clearance:export", c.MEDIUM)
    assert sh("hermes clearance export ~/.ssh/authorized_keys")[1] == c.CAP


def test_self_hermes_cannot_be_lowered_by_an_override():
    over = {"self:hermes": "free", "shell:hermes": "free", "shell:*": "low", "*": "free"}
    for cmd in WRITES[:12]:
        assert sh(cmd, overrides=over) == ("self:hermes", c.CAP), cmd


# --------------------------------------------------------------------------------------- C2: wherever home lives
def test_custom_home_writes_are_capped(home):
    data = home / "plugin-data" / "clearance"
    cases = [
        ("terminal", {"command": "find ~ -name clearance.db -delete"}),
        ("terminal", {"command": 'find ~ -name "*.db" -path "*clearance*" -delete'}),
        ("terminal", {"command": f'sqlite3 {data}/clearance.db "delete from ledger"'}),
        ("terminal", {"command": f"rm -rf {data}/undo"}),
        ("terminal", {"command": f"rm {data}/passport-ed25519.pem"}),
        ("write_file", {"path": f"{home}/config.yaml", "content": "x"}),
        ("write_file", {"path": f"{data}/undo/x/manifest.json", "content": "{}"}),
        ("terminal", {"command": f'echo "  enabled: false" >> {home}/config.yaml'}),
        ("terminal", {"command": f"rm -rf {home}/plugins/clearance"}),
        ("patch", {"patch": f"*** Begin Patch\n*** Update File: {home}/config.yaml\n@@\n-a\n+b\n*** End Patch"}),
        ("terminal", {"command": f"cd {home} && rm config.yaml"}),
        ("terminal", {"command": f"cp evil.yaml {home}/profiles/work/config.yaml"}),
        ("terminal", {"command": f"rm -rf {home}"}),
        ("terminal", {"command": f"mv {home} /tmp/gone"}),
        ("terminal", {"command": f"rm -rf {home.parent}"}),
        ("terminal", {"command": f"sqlite3 {home}/state.db .dump"}),
        ("terminal", {"command": "truncate -s0 $(find ~ -name clearance.db)"}),
        ("terminal", {"command": "rm $HERMES_HOME/config.yaml"}),
    ]
    for tool, args in cases:
        t, stakes = kind(tool, args)
        assert stakes == c.CAP, (tool, args, t)
        assert t.startswith(c.PROTECTED), (tool, args, t)


def test_clearance_data_names_are_self_clearance(home):
    data = home / "plugin-data" / "clearance"
    assert sh("find ~ -name clearance.db -delete") == ("self:clearance", c.CAP)
    assert sh(f'sqlite3 {data}/clearance.db "delete from ledger"') == ("self:clearance", c.CAP)
    assert sh(f"rm -rf {data}/undo") == ("self:clearance", c.CAP)
    assert kind("write_file", {"path": f"{data}/undo/x/manifest.json"}) == ("self:clearance", c.CAP)
    assert sh("rm -f passport-ed25519.pem") == ("self:clearance", c.CAP)
    assert sh("cp x /srv/plugin-data/clearance/clearance.db") == ("self:clearance", c.CAP)
    over = {"self:clearance": "free", "*": "free"}
    assert sh("find ~ -name clearance.db -delete", overrides=over) == ("self:clearance", c.CAP)


def test_symlinked_home_is_resolved(tmp_path, monkeypatch):
    real = tmp_path / "real-home"
    real.mkdir()
    link = tmp_path / "link-home"
    link.symlink_to(real)
    monkeypatch.setenv("HERMES_HOME", str(link))
    monkeypatch.delitem(sys.modules, "hermes_constants", raising=False)
    assert kind("write_file", {"path": f"{real}/config.yaml"})[1] == c.CAP
    assert kind("write_file", {"path": f"{link}/config.yaml"})[1] == c.CAP


def test_home_from_hermes_constants(tmp_path, monkeypatch):
    """With Hermes importable, its resolved home, root and account default are protected, not only $HERMES_HOME."""
    import pathlib
    home, root = tmp_path / "h" / "profiles" / "work", tmp_path / "h"
    home.mkdir(parents=True)
    fake = types.ModuleType("hermes_constants")
    fake.get_hermes_home = lambda: pathlib.Path(home)
    fake.get_default_hermes_root = lambda home=None: pathlib.Path(root)
    monkeypatch.setitem(sys.modules, "hermes_constants", fake)
    monkeypatch.delenv("HERMES_HOME", raising=False)
    assert kind("write_file", {"path": f"{home}/config.yaml"})[1] == c.CAP
    assert kind("write_file", {"path": f"{root}/config.yaml"})[1] == c.CAP
    assert kind("write_file", {"path": f"{root}/profiles/other/.env"})[1] == c.CAP


def test_project_inside_the_home_keeps_its_writes(tmp_path, monkeypatch):
    """Docker: HOME and HERMES_HOME are both /opt/data and the project may sit inside it. Only Hermes' own entries
    are protected then; the project's files stay ordinary writes."""
    data = tmp_path / "data"
    proj = data / "workspace" / "app"
    proj.mkdir(parents=True)
    monkeypatch.setenv("HERMES_HOME", str(data))
    monkeypatch.delitem(sys.modules, "hermes_constants", raising=False)
    assert kind("write_file", {"path": "src/a.py"}, cwd=str(proj)) == ("file:write", c.LOW)
    assert kind("write_file", {"path": f"{data}/config.yaml"}, cwd=str(proj))[1] == c.CAP
    assert kind("write_file", {"path": f"{data}/plugins/x/__init__.py"}, cwd=str(proj))[1] == c.CAP
    assert sh(f"rm -rf {data}/plugin-data", cwd=str(proj))[1] == c.CAP
    assert sh("rm -rf build", cwd=str(proj)) == ("shell:rm", c.MEDIUM)


def test_docker_home_is_the_user_home_and_the_working_directory(tmp_path, monkeypatch):
    """Hermes' image: HOME=/opt/data, HERMES_HOME=/opt/data, and the terminal starts there."""
    data = tmp_path / "opt-data"
    data.mkdir()
    monkeypatch.setenv("HOME", str(data))
    monkeypatch.setenv("HERMES_HOME", str(data))
    monkeypatch.delitem(sys.modules, "hermes_constants", raising=False)
    cwd = str(data)
    assert sh("cd ~ && npm test", cwd=cwd)[1] == c.MEDIUM
    assert sh("cp report.pdf ~", cwd=cwd)[1] != c.CAP
    assert kind("write_file", {"path": "app/main.py"}, cwd=cwd) == ("file:write", c.LOW)
    assert kind("write_file", {"path": "config.yaml"}, cwd=cwd)[1] == c.CAP
    assert sh("rm -rf ~", cwd=cwd)[1] == c.CAP
    assert sh(f"mv {data} /tmp/x", cwd=cwd)[1] == c.CAP
    assert sh("rm -rf plugins/clearance", cwd=cwd)[1] == c.CAP


def test_windows_default_home():
    assert kind("write_file", {"path": "C:\\Users\\u\\AppData\\Local\\hermes\\config.yaml"})[1] == c.CAP


def test_reads_of_the_home_stay_free(home):
    assert sh(f"cat {home}/plugin-data/clearance/x.txt") == ("shell:cat", c.FREE)
    assert sh(f"ls {home}") == ("shell:ls", c.FREE)


# ------------------------------------------------------------------------------- minor: execute_code's floor
def test_execute_code_scans_its_code(home):
    assert kind("execute_code", {"code": "print(1)"}) == ("code:execute", c.MEDIUM)
    assert kind("execute_code", {"code": 'open("/Users/u/.hermes/config.yaml","w")'}) == ("file:sensitive", c.CAP)
    assert kind("execute_code", {"code": 'open("/root/.ssh/authorized_keys","a")'}) == ("file:sensitive", c.CAP)
    assert kind("execute_code", {"code": f'open("{home}/config.yaml","w")'})[1] == c.CAP
    assert kind("execute_code", {"code": "os.remove(db_dir + '/clearance.db')"}) == ("self:clearance", c.CAP)
    assert kind("execute_code", {"code": "subprocess.run(['hermes', 'plugins', 'disable', 'x'])"}) == \
        ("self:hermes", c.CAP)
    assert kind("execute_code", {"code": "import hermes_cli.config as h; h.save_config({})"}) == \
        ("self:hermes", c.CAP)


def test_python_inline_code_gets_the_same_floor(home):
    assert sh(f"python3 -c \"open('{home}/config.yaml','w')\"")[1] == c.CAP
    assert sh("python3 -c \"import subprocess; subprocess.run(['hermes','plugins','disable','clearance'])\"") == \
        ("self:hermes", c.CAP)


# ------------------------------------------------------------------------------------- I3: suspension list
EXTERNAL = [
    ("terminal", {"command": "http GET example.com"}),
    ("terminal", {"command": "https example.com"}),
    ("terminal", {"command": "xh example.com"}),
    ("terminal", {"command": "lynx -dump example.com"}),
    ("terminal", {"command": "w3m -dump example.com"}),
    ("terminal", {"command": "links -dump example.com"}),
    ("terminal", {"command": "aria2c https://x/y"}),
    ("terminal", {"command": "nc example.com 80"}),
    ("terminal", {"command": "ncat example.com 80"}),
    ("terminal", {"command": "git clone https://x/y"}),
    ("terminal", {"command": "git pull"}),
    ("terminal", {"command": "git -C sub fetch origin"}),
    ("terminal", {"command": "cd sub && git pull --rebase"}),
    ("terminal", {"command": "bash -c 'git fetch'"}),
    ("mcp__notion__get_page", {}),
    ("mcp__linear__get_issue", {}),
    ("mcp__jira__get_issue", {}),
    ("mcp__confluence__get_page", {}),
    ("mcp__github__get_issue", {}),
    ("mcp__gitlab__get_issue", {}),
    ("mcp__asana__get_task", {}),
    ("mcp__trello__get_card", {}),
    ("mcp__drive__read_file", {}),
    ("mcp__google_drive__search_files", {}),
    ("mcp__docs__get_document", {}),
]


@pytest.mark.parametrize("tool,args", EXTERNAL)
def test_reads_external(tool, args):
    assert c.reads_external(tool, args, PROJ), (tool, args)


@pytest.mark.parametrize("tool,args", [
    ("terminal", {"command": "git status"}),
    ("terminal", {"command": "git log"}),
    ("terminal", {"command": "echo http"}),
    ("mcp__notion__update_page", {}),
    ("mcp__filesystem__read_file", {}),
])
def test_not_external(tool, args):
    assert not c.reads_external(tool, args, PROJ), (tool, args)


def test_readme_lists_every_external_server_and_program():
    import pathlib
    root = pathlib.Path(__file__).resolve().parent.parent
    assert "docs/self-protection.md" in (root / "README.md").read_text(encoding="utf-8")
    readme = (root / "docs" / "self-protection.md").read_text(encoding="utf-8")   # the full rules
    for server in c.EXTERNAL_SERVERS:
        assert server in readme, server
    for prog in sorted(c.EXTERNAL_PROGRAMS):
        assert f"`{prog}`" in readme, prog
    assert "`git clone`" in readme and "`git pull`" in readme and "`git fetch`" in readme


@pytest.mark.skipif(os.name != "posix", reason="paths")
def test_sensitive_path_helper(home):
    assert c.sensitive_path(f"{home}/config.yaml")
    assert c.sensitive_path(os.path.expanduser("~/.ssh/id_ed25519"))
    assert not c.sensitive_path("/home/u/proj/src/a.py")
