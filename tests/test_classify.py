"""Action types and stakes: what each Hermes tool call is, so that its record stays in its own type."""
import pytest

from clearance import classify as C

CWD = "/home/me/project"


def k(tool, args=None, **kw):
    a = C.classify(tool, args or {}, cwd=CWD, **kw)
    return a.type, a.stakes


@pytest.mark.parametrize("tool", ["read_file", "search_files", "web_search", "web_extract", "vision_analyze",
                                  "session_search", "skills_list", "skill_view", "clarify", "todo_list",
                                  "kanban_show", "kanban_list"])
def test_reads_are_free(tool):
    assert k(tool)[1] == C.FREE


def test_file_writes_inside_and_outside_the_project():
    assert k("write_file", {"path": "src/app.py"}) == ("file:write", C.LOW)
    assert k("patch", {"path": f"{CWD}/README.md"}) == ("file:write", C.LOW)
    assert k("write_file", {"path": "/tmp/notes.txt"}) == ("file:write-outside", C.MEDIUM)
    assert k("write_file", {"path": "../other/x.py"}) == ("file:write-outside", C.MEDIUM)


@pytest.mark.parametrize("path", ["~/.ssh/config", "/home/me/.hermes/config.yaml", "/etc/hosts", ".env",
                                  "src/.env.production", "/home/me/.aws/credentials"])
def test_sensitive_files_are_capped(path):
    assert k("write_file", {"path": path}) == ("file:sensitive", C.CAP)


@pytest.mark.parametrize("cmd", ["ls -la", "git status", "git log --oneline -5", "cat a.txt | grep x", "pwd",
                                 "rg TODO src", "git diff HEAD~1"])
def test_read_only_shell_commands_are_free(cmd):
    assert k("terminal", {"command": cmd})[1] == C.FREE


def test_shell_commands_are_typed_by_program():
    assert k("terminal", {"command": "pytest -q tests/"}) == ("shell:pytest", C.MEDIUM)
    assert k("terminal", {"command": "FOO=1 sudo /usr/bin/npm install"}) == ("shell:npm", C.MEDIUM)
    assert k("terminal", {"command": "git commit -am 'x'"}) == ("shell:git:commit", C.MEDIUM)
    assert k("terminal", {"command": "echo hi > out.txt"}) == ("shell:echo", C.MEDIUM)


@pytest.mark.parametrize("cmd,typ", [("git push origin main", "shell:git:push"), ("npm publish", "shell:npm:publish"),
                                     ("curl -X POST https://api.example.com -d x=1", "shell:curl:send"),
                                     ("scp f.txt host:/tmp", "shell:scp"), ("ssh host uptime", "shell:ssh"),
                                     ("gh pr create --fill", "shell:gh:pr"), ("docker push img", "shell:docker:push")])
def test_shell_commands_that_reach_the_outside_are_high_stakes(cmd, typ):
    assert k("terminal", {"command": cmd}) == (typ, C.HIGH)


def test_a_chain_takes_its_highest_stakes_part():
    assert k("terminal", {"command": "pytest -q && git push"}) == ("shell:git:push", C.HIGH)
    assert k("terminal", {"command": "ls; npm test"}) == ("shell:npm", C.MEDIUM)


def test_curl_without_a_payload_is_a_read():
    assert k("terminal", {"command": "curl -s https://example.com"})[1] == C.FREE


@pytest.mark.parametrize("tool,typ,stakes", [
    ("execute_code", "code:execute", C.MEDIUM), ("delegate_task", "delegate:task", C.MEDIUM),
    ("process_manage", "process:manage", C.MEDIUM), ("browser_exec", "browser:exec", C.MEDIUM),
    ("computer_use", "computer:use", C.MEDIUM), ("memory", "memory:write", C.LOW),
    ("react_to_message", "message:react", C.LOW), ("kanban_comment", "kanban:comment", C.LOW),
    ("image_generate", "media:generate", C.LOW), ("cronjob_manage", "cron:manage", C.HIGH),
    ("skill_manage", "self:skills", C.CAP), ("manage_catalog", "self:plugins", C.CAP),
    ("browser_vault", "secrets:vault", C.CAP), ("send_message", "message:send", C.HIGH)])
def test_hermes_tools(tool, typ, stakes):
    assert k(tool) == (typ, stakes)


@pytest.mark.parametrize("tool,typ,stakes", [
    ("mcp_hubspot_search_contacts", "mcp:hubspot:search_contacts", C.FREE),
    ("mcp_hubspot_update_contact", "mcp:hubspot:update_contact", C.MEDIUM),
    ("mcp_gmail_send_email", "mcp:gmail:send_email", C.HIGH),
    ("mcp_stripe_create_payment", "mcp:stripe:create_payment", C.HIGH),
    ("mcp_notion_frobnicate", "mcp:notion:frobnicate", C.HIGH)])
def test_mcp_tools_by_verb(tool, typ, stakes):
    assert k(tool) == (typ, stakes)


def test_unknown_tools_are_high_stakes():
    """An action whose effect cannot be read is treated as high stakes (the study's rule)."""
    assert k("some_plugin_tool") == ("tool:some_plugin_tool", C.HIGH)


def test_owner_overrides_win():
    over = {"mcp:notion:*": "medium", "shell:git:push": "cap", "file:write": "free"}
    assert k("mcp_notion_frobnicate", overrides=over) == ("mcp:notion:frobnicate", C.MEDIUM)
    assert k("terminal", {"command": "git push"}, overrides=over) == ("shell:git:push", C.CAP)
    assert k("write_file", {"path": "a.py"}, overrides=over) == ("file:write", C.FREE)


def test_overrides_cannot_free_a_capped_secret():
    """Caps that protect secrets and the agent's own rights are not overridable to free (they can only stay cap)."""
    assert k("browser_vault", overrides={"secrets:*": "free"}) == ("secrets:vault", C.CAP)


def test_summary_for_the_approval_prompt():
    a = C.classify("terminal", {"command": "git push origin main"}, cwd=CWD)
    assert "git push origin main" in a.summary and a.type in a.summary
