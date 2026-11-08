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


# --------------------------------------------------------------------------------------------------------------------
# Commands that hide what they run must not inherit a cleared type's autonomy
# --------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("cmd,typ,stakes", [
    ('bash -c "git push origin main"', "shell:git:push", C.HIGH),
    ("sh -c 'ls -la'", "shell:ls", C.FREE),
    ("zsh -c 'npm test'", "shell:npm", C.MEDIUM),
    ("git -C ../other push", "shell:git:push", C.HIGH),
    ("git -c user.name=x push", "shell:git:push", C.HIGH),
    ("gh -R owner/repo pr create --fill", "shell:gh:pr", C.HIGH),
    ("xargs git push < remotes.txt", "shell:git:push", C.HIGH),
    ("eval \"$CMD\"", "shell:eval", C.HIGH),
    ("$GIT push", "shell:dynamic", C.HIGH),
    ("echo $(cat ~/.ssh/id_rsa)", "shell:echo", C.HIGH),
    ("python3 -c 'import os; os.system(\"git push\")'", "shell:python3:inline", C.HIGH),
    ("node -e 'require(\"child_process\")'", "shell:node:inline", C.HIGH),
    ("python3 scripts/deploy.py", "shell:python3:deploy.py", C.MEDIUM),
    ("python3 -m http.server", "shell:python3:-m:http.server", C.MEDIUM),
    ("npm run build", "shell:npm:run:build", C.MEDIUM),
    ("npm run deploy", "shell:npm:run:deploy", C.MEDIUM),
    ("make release", "shell:make:release", C.MEDIUM),
    ("bash deploy.sh", "shell:bash:deploy.sh", C.MEDIUM),
    ("echo key >> ~/.ssh/authorized_keys", "file:sensitive", C.CAP),
    ("curl --json '{\"a\":1}' https://api.example.com", "shell:curl:send", C.HIGH),
])
def test_commands_that_hide_what_they_run(cmd, typ, stakes):
    assert k("terminal", {"command": cmd}) == (typ, stakes)


@pytest.mark.parametrize("cmd,typ,stakes", [
    ("(cd ../x && git push)", "shell:git:push", C.HIGH),
    ("diff <(ls a) <(ls b)", "shell:diff", C.HIGH),
    ("git commit -m \"$(date)\"", "shell:git", C.HIGH),
])
def test_subshells_and_substitutions(cmd, typ, stakes):
    assert k("terminal", {"command": cmd}) == (typ, stakes)


# --------------------------------------------------------------------------------------------------------------------
# v2: adversarial findings
# --------------------------------------------------------------------------------------------------------------------
def test_multiline_commands_take_their_riskiest_line():
    assert k("terminal", {"command": "pwd\nnpm publish"}) == ("shell:npm:publish", C.HIGH)
    assert k("terminal", {"command": "ls\ngit push origin main"}) == ("shell:git:push", C.HIGH)


def test_v4a_patch_bodies_are_read():
    body = "*** Begin Patch\n*** Add File: /home/me/.ssh/authorized_keys\n+k\n*** End Patch"
    assert k("patch", {"mode": "patch", "patch": body}) == ("file:sensitive", C.CAP)
    body = "*** Begin Patch\n*** Update File: .env\n+k\n*** End Patch"
    assert k("patch", {"mode": "patch", "path": "README.md", "patch": body}) == ("file:sensitive", C.CAP)
    body = "*** Begin Patch\n*** Update File: src/a.py\n+k\n*** End Patch"
    a = C.classify("patch", {"mode": "patch", "patch": body}, cwd=CWD)
    assert (a.type, a.stakes, a.reversible) == ("file:write", C.LOW, True)
    body = "*** Begin Patch\n*** Move File: src/a.py -> /etc/x\n*** End Patch"
    assert k("patch", {"mode": "patch", "patch": body}) == ("file:sensitive", C.CAP)
    body = "*** Begin Patch\n*** Update File: src/a.py\n*** Move to: /tmp/b.py\n*** End Patch"
    assert k("patch", {"mode": "patch", "patch": body}) == ("file:write-outside", C.MEDIUM)


def test_hermes_mcp_names():
    assert k("mcp__notion__search") == ("mcp:notion:search", C.FREE)
    assert k("mcp__gmail__send_email") == ("mcp:gmail:send_email", C.HIGH)
    assert k("mcp_notion_search") == ("mcp:notion:search", C.FREE)


def test_manage_connections_is_capped():
    assert k("manage_connections") == ("self:connections", C.CAP)


def test_cd_is_followed_for_redirects():
    assert k("terminal", {"command": "cd ~/.ssh && echo k >> authorized_keys"}) == ("file:sensitive", C.CAP)
    assert k("terminal", {"command": "cd /etc\necho k > hosts"}) == ("file:sensitive", C.CAP)


def test_only_project_file_writes_are_reversible():
    r = lambda tool, args: C.classify(tool, args, cwd=CWD).reversible
    assert r("write_file", {"path": "src/a.py"}) is True
    assert r("write_file", {"path": "/tmp/x"}) is False
    assert r("terminal", {"command": "rm a.py"}) is False
    assert r("terminal", {"command": "ls"}) is False
    assert r("memory", {}) is False
    assert r("read_file", {"path": "a"}) is False


def test_files_written():
    body = "*** Begin Patch\n*** Update File: src/a.py\n*** Move File: b.py -> c.py\n*** End Patch"
    assert C.files_written("write_file", {"path": "a.py"}, CWD) == [f"{CWD}/a.py"]
    assert C.files_written("patch", {"path": "README.md", "mode": "patch", "patch": body}, CWD) == [
        f"{CWD}/README.md", f"{CWD}/src/a.py", f"{CWD}/b.py", f"{CWD}/c.py"]
    assert C.files_written("terminal", {"command": "ls"}, CWD) == []
    assert C.files_written("read_file", {"path": "a"}, CWD) == []


@pytest.mark.parametrize("tool,args", [
    ("web_extract", {}), ("web_search", {}), ("browser_navigate", {}), ("browser_click", {}),
    ("mcp__gmail__get_message", {}), ("mcp__slack__read_channel", {}),
    ("read_file", {"path": "/etc/hosts"}), ("read_file", {"path": "../other/x"}),
    ("terminal", {"command": "curl -s https://x"}), ("terminal", {"command": "ls && wget https://x"})])
def test_reads_external_true(tool, args):
    assert C.reads_external(tool, args, CWD) is True


@pytest.mark.parametrize("tool,args", [
    ("read_file", {"path": "src/a.py"}), ("terminal", {"command": "ls"}),
    ("mcp__notion__update_page", {}), ("mcp__notion__search", {}), ("mcp__hubspot__get_contact", {}),
    ("write_file", {"path": "a"})])
def test_reads_external_false(tool, args):
    assert C.reads_external(tool, args, CWD) is False


@pytest.mark.parametrize("tool,typ,stakes", [
    ("mcp__gmail__get_message", "mcp:gmail:get_message", C.FREE),
    ("mcp__slack__list_messages", "mcp:slack:list_messages", C.FREE),
    ("mcp__gmail__send_message", "mcp:gmail:send_message", C.HIGH),
    ("mcp__gmail__get_and_send_draft", "mcp:gmail:get_and_send_draft", C.HIGH),
    ("mcp__notion__search_and_update", "mcp:notion:search_and_update", C.MEDIUM)])
def test_read_verb_is_not_raised_by_an_ambiguous_noun(tool, typ, stakes):
    assert k(tool) == (typ, stakes)


def test_reads_external_still_true_for_get_message():
    assert C.reads_external("mcp__gmail__get_message", {}, CWD) is True


# --------------------------------------------------------------------------------------------------------------------
# Fix round 1: adversarial review of the classifier
# --------------------------------------------------------------------------------------------------------------------
HOME = "/home/me"


def kh(tool, args=None):
    a = C.classify(tool, args or {}, cwd=CWD, home=HOME)
    return a.type, a.stakes


def cmd(command):
    return kh("terminal", {"command": command})


@pytest.mark.parametrize("command,typ,stakes", [
    ('git commit -m "a\nb"; git push', "shell:git:push", C.HIGH),
    ('git commit -m "a\nb"&&git push', "shell:git:push", C.HIGH),
    ('git commit -m "title\n\nbody" && git push', "shell:git:push", C.HIGH),
    ('echo "a\nb">~/.ssh/authorized_keys', "file:sensitive", C.CAP),
    ('echo "a\nb" >> ~/.ssh/authorized_keys', "file:sensitive", C.CAP),
    ('echo "\x0c";git push', "shell:git:push", C.HIGH),
    ('echo " ";npm publish', "shell:npm:publish", C.HIGH),
    ("echo k >> \\\n~/.ssh/authorized_keys", "file:sensitive", C.CAP),
    ("git \\\npush origin main", "shell:git:push", C.HIGH),
    ("npm \\\npublish", "shell:npm:publish", C.HIGH),
    ("cat > n.md <<EOF\ndon't push\nEOF\ngit push", "shell:git:push", C.HIGH),
    ("pwd\r\nnpm publish", "shell:npm:publish", C.HIGH),
    ("ls # note\ngit push", "shell:git:push", C.HIGH),
])
def test_quotes_continuations_and_newlines(command, typ, stakes):
    assert cmd(command) == (typ, stakes)


@pytest.mark.parametrize("command,typ", [
    ("ls;(git push)", "shell:git:push"), ("ls&&(git push)", "shell:git:push"),
    ("ls ;(npm publish)", "shell:npm:publish"), ("ls |& npm publish", "shell:npm:publish"),
    ("true;{ git push;}", "shell:git:push"), ("ls||git push", "shell:git:push"),
])
def test_glued_separators(command, typ):
    assert cmd(command) == (typ, C.HIGH)


def test_redirect_operators_are_not_separators():
    assert cmd("ls 2>&1")[1] == C.FREE
    assert cmd("ls >&2")[1] == C.FREE
    assert cmd("echo k >& ~/.ssh/authorized_keys") == ("file:sensitive", C.CAP)
    assert cmd("echo k &> ~/.ssh/authorized_keys") == ("file:sensitive", C.CAP)


@pytest.mark.parametrize("command", [
    "cd $HOME/.ssh && echo k >> authorized_keys",
    'cd "${HOME}/.ssh" && echo k >> authorized_keys',
    "cd ~/.ssh; cd /tmp; cd -; echo k >> authorized_keys",
    "pushd ~/.ssh && echo k >> authorized_keys",
    "builtin cd ~/.ssh && echo k >> authorized_keys",
    "command cd ~/.ssh && echo k >> authorized_keys",
    "cd >/dev/null ~/.ssh && echo k >> authorized_keys",
    "cd ~/.ssh; (cd /tmp) ; echo k >> authorized_keys",
    "cd ~/.ssh; cd /tmp | true; echo k >> authorized_keys",
    "cd ~/.ssh; cd /tmp & echo k >> authorized_keys",
    "cd ~/.ssh; true || cd /tmp; echo k >> authorized_keys",
    "(cd ~/.ssh && echo k >> authorized_keys)",
    "cd ~/.ssh\ncd /tmp\ncd -\necho k >> authorized_keys",
])
def test_cd_cannot_be_dodged(command):
    assert cmd(command) == ("file:sensitive", C.CAP)


@pytest.mark.parametrize("command", [
    "cd $FOO && echo k >> authorized_keys",
    "cd ~/.ssh; popd; echo k >> authorized_keys",
    "cd `pwd`/x && echo k > out.txt",
    "cd ~/.ssh; cd $X; cp a b",
])
def test_unknown_cwd_makes_relative_writes_at_least_high(command):
    assert C.RANK[cmd(command)[1]] >= C.RANK[C.HIGH]


def test_known_cd_keeps_ordinary_writes_ordinary():
    assert cmd("cd src && echo hi > out.txt")[1] == C.MEDIUM
    assert cmd("(cd ../x && git push)") == ("shell:git:push", C.HIGH)


@pytest.mark.parametrize("tool", ["mcp__gmail__get_and_forward_message", "mcp__slack__check_and_respond_to_messages",
                                  "mcp__reports__summarize_and_email", "mcp__gmail__export_to_email",
                                  "mcp__crm__fetch_and_mail_report", "mcp__sms__lookup_and_text_sms",
                                  "mcp__gmail__forward_message", "mcp__gmail__reply_to_thread"])
def test_connector_words_remove_the_noun_exemption(tool):
    assert kh(tool)[1] == C.HIGH


@pytest.mark.parametrize("tool,args", [
    ("mcp__slack__slack_get_channel_history", {}), ("mcp__brave_search__brave_web_search", {}),
    ("mcp__playwright__browser_navigate", {}), ("mcp__fetch__fetch", {}), ("mcp__github__get_issue", {}),
    ("mcp__exa__search", {}), ("mcp__tavily__search", {}), ("mcp__firecrawl__scrape", {}),
    ("terminal", {"command": "VAR=1 curl https://x"}), ("terminal", {"command": "timeout 5 curl https://x"}),
    ("terminal", {"command": "timeout -s KILL 5 curl https://x"}),
    ("terminal", {"command": "bash -c 'curl https://x'"}), ("terminal", {"command": "xargs curl < urls"}),
    ("terminal", {"command": "sudo -u me curl https://x"}), ("terminal", {"command": "env -u A curl https://x"}),
    ("terminal", {"command": "gh issue view 1"}), ("terminal", {"command": "gh pr view 1"}),
    ("terminal", {"command": "gh api repos/a/b/issues"}), ("terminal", {"command": "ls\ncurl https://x"}),
])
def test_reads_external_second_round_true(tool, args):
    assert C.reads_external(tool, args, CWD) is True


@pytest.mark.parametrize("tool,args", [
    ("terminal", {"command": "git clone x"}), ("terminal", {"command": "gh api -X POST repos/a/b"}),
    ("terminal", {"command": "gh api repos/a/b -f x=1"}), ("terminal", {"command": "gh pr create"}),
    ("mcp__github__create_issue", {}), ("mcp__gmail__get_and_forward_message", {}),
    ("mcp__hubspot__get_contact", {}),
])
def test_reads_external_second_round_false(tool, args):
    assert C.reads_external(tool, args, CWD) is False


def test_windows_paths_keep_forward_slashes(monkeypatch):
    import ntpath
    import types
    monkeypatch.setattr(C, "os", types.SimpleNamespace(path=ntpath, getcwd=lambda: "C:\\work"))
    assert C.files_written("write_file", {"path": "a.py"}, CWD) == [f"{CWD}/a.py"]
    assert C.reads_external("read_file", {"path": "src/a.py"}, CWD) is False
    assert C.reads_external("read_file", {"path": "/etc/hosts"}, CWD) is True
    a = C.classify("write_file", {"path": "src/a.py"}, cwd=CWD)
    assert (a.type, a.stakes, a.reversible) == ("file:write", C.LOW, True)
    assert cmd("cd ~/.ssh && echo k >> authorized_keys")[1] == C.CAP


@pytest.mark.parametrize("body", [
    "*** Begin Patch\n*** Frobnicate File: /etc/hosts\n*** End Patch",
    "",
])
def test_unreadable_patch_is_high_and_irreversible(body):
    a = C.classify("patch", {"mode": "patch", "patch": body}, cwd=CWD)
    assert (a.stakes, a.reversible) == (C.HIGH, False)
    a = C.classify("patch", {"mode": "patch", "path": "README.md",
                             "patch": "*** Frobnicate File: /etc/hosts"}, cwd=CWD)
    assert (a.stakes, a.reversible) == (C.HIGH, False)


def test_v4a_edge_headers():
    body = "*** Begin Patch\n***Add File:/etc/hosts\n+x\n*** End Patch"
    assert kh("patch", {"mode": "patch", "patch": body}) == ("file:sensitive", C.CAP)
    body = "*** Begin Patch\n*** Update File: src/a.py\r\n*** Add File: /etc/hosts\r\n+x\r\n*** End Patch"
    assert kh("patch", {"mode": "patch", "patch": body}) == ("file:sensitive", C.CAP)
    body = "*** Begin Patch\n*** Move File: src/a.py -> b -> /etc/x\n*** End Patch"
    assert kh("patch", {"mode": "patch", "patch": body}) == ("file:sensitive", C.CAP)


@pytest.mark.parametrize("command", [
    "echo k | tee -a ~/.ssh/authorized_keys", "cp x ~/.ssh/authorized_keys", "mv x ~/.ssh/config",
    "dd of=~/.ssh/authorized_keys", "ln -sf x ~/.ssh/authorized_keys", "install x ~/.ssh/y",
    "rsync x ~/.ssh/", "sudo tee /etc/hosts", "touch ~/.ssh/x",
])
def test_sensitive_paths_given_to_write_commands_are_capped(command):
    assert cmd(command) == ("file:sensitive", C.CAP)


def test_ordinary_write_commands_stay_ordinary():
    assert cmd("cp a b") == ("shell:cp", C.MEDIUM)
    assert cmd("echo hi | tee out.txt") == ("shell:tee", C.MEDIUM)


def test_symlinks_are_resolved(tmp_path):
    proj = tmp_path / "proj"
    ssh = tmp_path / "home" / ".ssh"
    proj.mkdir()
    ssh.mkdir(parents=True)
    (proj / "ssh").symlink_to(ssh)
    (proj / "plain").mkdir()
    a = C.classify("write_file", {"path": "ssh/authorized_keys"}, cwd=str(proj))
    assert (a.type, a.stakes) == ("file:sensitive", C.CAP)
    a = C.classify("terminal", {"command": "echo k >> ssh/authorized_keys"}, cwd=str(proj))
    assert (a.type, a.stakes) == ("file:sensitive", C.CAP)
    a = C.classify("write_file", {"path": "plain/x.txt"}, cwd=str(proj))
    assert (a.type, a.stakes, a.reversible) == ("file:write", C.LOW, True)
    (proj / "out").symlink_to(tmp_path)
    a = C.classify("write_file", {"path": "out/x.txt"}, cwd=str(proj))
    assert (a.type, a.stakes) == ("file:write-outside", C.MEDIUM)


def test_clamped_mcp_names_are_high():
    name = "mcp__gmail__get_message_" + "a" * 31 + "_deadbeef"
    assert len(name) == 64 and C.CLAMPED.match(name)
    assert C.classify(name, {}, cwd=CWD).stakes == C.HIGH
    assert C.reads_external(name, {}, CWD) is False
