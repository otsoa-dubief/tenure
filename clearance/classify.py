# Copyright 2026 Otsoa Dubief
# SPDX-License-Identifier: Apache-2.0
"""What a tool call is: its action type (the unit whose record is kept) and its stakes.

Grid from the earned-autonomy study: an action is classed by what it does, not by the tool. Reads are free. Writes
inside the project are low stakes and reversible; writes elsewhere, commands, code and delegation are medium;
anything that leaves the machine (messages to others, publications, pushes, uploads) and money are high. Some
actions are capped and always ask: secrets, the agent's own skills, plugins and guardrails, sensitive files. An
action whose effect cannot be read is treated as high stakes.

Types are fine-grained so that a record says something: shell commands are typed by program (and by subcommand
when the subcommand changes the stakes), MCP tools by server and tool.
"""
from __future__ import annotations

import fnmatch
import os
import re
import shlex
from dataclasses import dataclass

FREE, LOW, MEDIUM, HIGH, CAP = "free", "low", "medium", "high", "cap"
RANK = {FREE: 0, LOW: 1, MEDIUM: 2, HIGH: 3, CAP: 4}
PROTECTED = ("secrets:", "self:", "file:sensitive")     # caps an owner override can never lower


@dataclass(frozen=True)
class Action:
    type: str
    stakes: str
    reversible: bool
    summary: str


# --------------------------------------------------------------------------------------------------------- Hermes
FREE_TOOLS = {
    "read_file", "search_files", "web_search", "web_extract", "vision_analyze", "video_analyze", "session_search",
    "skills_list", "skill_view", "clarify", "todo_list", "kanban_show", "kanban_list", "kanban_attachments",
    "kanban_heartbeat", "x_search", "read_terminal", "read_window_below", "close_terminal", "feishu_doc_read",
    "feishu_drive_list_comments", "feishu_drive_list_comment_replies", "yb_query_group_info",
    "yb_query_group_members", "yb_search_sticker", "focus_pane", "show_tip", "set_theme", "annotate_preview",
    "setup_beat", "gui_tour", "desktop_preview", "drive_preview",
}
TOOLS = {
    "process_manage": ("process:manage", MEDIUM, True),
    "execute_code": ("code:execute", MEDIUM, False),
    "delegate_task": ("delegate:task", MEDIUM, False),
    "browser_exec": ("browser:exec", MEDIUM, False),
    "browser_cdp": ("browser:cdp", MEDIUM, False),
    "browser_dialog": ("browser:dialog", LOW, False),
    "computer_use": ("computer:use", MEDIUM, False),
    "memory": ("memory:write", LOW, True),
    "react_to_message": ("message:react", LOW, True),
    "image_generate": ("media:generate", LOW, True),
    "video_generate": ("media:generate", LOW, True),
    "text_to_speech": ("media:generate", LOW, True),
    "xai_video_edit": ("media:generate", LOW, True),
    "xai_video_extend": ("media:generate", LOW, True),
    "cronjob_manage": ("cron:manage", HIGH, True),
    "skill_manage": ("self:skills", CAP, True),
    "manage_catalog": ("self:plugins", CAP, True),
    "manage_connections": ("self:connections", CAP, False),
    "browser_vault": ("secrets:vault", CAP, False),
    "send_message": ("message:send", HIGH, False),
    "yb_send_dm": ("message:send", HIGH, False),
    "yb_send_sticker": ("message:send", HIGH, False),
    "discord_admin": ("discord:admin", HIGH, False),
    "feishu_drive_reply_comment": ("feishu:comment", MEDIUM, False),
    "feishu_drive_add_comment": ("feishu:comment", MEDIUM, False),
}

# ---------------------------------------------------------------------------------------------------------- files
SENSITIVE_DIRS = ("/.ssh/", "/.gnupg/", "/.aws/", "/.azure/", "/.config/gcloud/", "/.kube/", "/.docker/",
                  "/.hermes/", "/.netrc", "/.git-credentials", "/.npmrc", "/.pypirc")
SENSITIVE_PREFIXES = ("/etc/", "/usr/", "/bin/", "/sbin/", "/System/", "/Library/", "/private/etc/")
SENSITIVE_NAME = re.compile(r"^(\.env(\..*)?|id_[a-z0-9]+|.*\.pem|.*\.key|credentials(\.json)?|secrets?\.(ya?ml|json))$",
                            re.I)


UNKNOWN = "\0unknown-cwd"                         # a virtual cwd that could not be worked out


def _norm(p: str) -> str:
    return p.replace("\\", "/")


def _expand(path: str, home: str) -> str:
    """`~`, `$HOME` and `${HOME}` at the start of a path."""
    for pre in ("${HOME}", "$HOME"):
        if path == pre or path.startswith(pre + "/"):
            return home + path[len(pre):]
    if path == "~" or path.startswith("~/") or path.startswith("~\\"):
        return home + path[1:]
    return path


def _abs(path: str, cwd: str | None, home: str | None = None) -> str:
    p = _expand(path, home or os.path.expanduser("~"))
    return _norm(os.path.normpath(p if os.path.isabs(p) else os.path.join(cwd or os.getcwd(), p)))


def _real(full: str) -> str:
    """The symlink-resolved path, when the path or its parent exists (otherwise the path as written)."""
    try:
        if os.path.exists(full) or os.path.islink(full) or os.path.isdir(os.path.dirname(full)):
            return _norm(os.path.realpath(full))
    except (OSError, ValueError):
        pass
    return full


def _sensitive(probe: str) -> bool:
    return bool(any(d in probe + "/" for d in SENSITIVE_DIRS) or probe.startswith(SENSITIVE_PREFIXES)
                or SENSITIVE_NAME.match(os.path.basename(probe)))


def _file(path: str, cwd: str | None, home: str) -> tuple[str, str, bool]:
    base = cwd or os.getcwd()
    full = _abs(path, base, home)
    real = _real(full)
    if _sensitive(full) or _sensitive(real):
        return "file:sensitive", CAP, False
    lexroot = _norm(os.path.normpath(base)).rstrip("/") + "/"
    try:
        realroot = _norm(os.path.realpath(base)).rstrip("/") + "/" if os.path.isdir(base) else lexroot
    except (OSError, ValueError):
        realroot = lexroot
    if (real + "/").startswith(realroot) or (full == real and (full + "/").startswith(lexroot)):
        return "file:write", LOW, True
    return "file:write-outside", MEDIUM, True


_V4A_FILE = re.compile(r"^\*\*\*\s*(\w+)\s+File:\s*(.*?)\s*$", re.M)
_V4A_MOVE_TO = re.compile(r"^\*\*\*\s*Move\s+to:\s*(.*?)\s*$", re.M)
_V4A_VERBS = {"Add", "Update", "Delete", "Move"}


def _v4a_paths(patch: str) -> list[str]:
    """Every path a V4A patch body names: Add/Update/Delete headers, `Move to:` and Hermes' `Move File: a -> b`."""
    found: list[tuple[int, str]] = []
    for m in _V4A_FILE.finditer(patch or ""):
        if m.group(1) in _V4A_VERBS:
            found += [(m.start(), p) for p in re.split(r"\s*->\s*", m.group(2))]
    found += [(m.start(), m.group(1)) for m in _V4A_MOVE_TO.finditer(patch or "")]
    return [p for _, p in sorted(found) if p.strip()]


def _v4a_unreadable(patch: str) -> bool:
    """A `*** <Verb> File:` header whose verb we do not know: what it touches cannot be read."""
    return any(m.group(1) not in _V4A_VERBS for m in _V4A_FILE.finditer(patch or ""))


def files_written(tool_name: str, args: dict, cwd: str | None, home: str | None = None) -> list[str]:
    """Absolute paths a write_file or patch call touches (the `path` argument and every V4A header); else []."""
    if tool_name not in ("write_file", "patch") or not isinstance(args, dict):
        return []
    raw = [str(args.get("path") or args.get("file_path") or "")]
    if tool_name == "patch":
        raw += _v4a_paths(str(args.get("patch") or ""))
    out: list[str] = []
    for r in raw:
        if r.strip() and _abs(r.strip(), cwd, home) not in out:
            out.append(_abs(r.strip(), cwd, home))
    return out


def _files(tool_name: str, args: dict, cwd: str | None, home: str) -> tuple[str, str, bool]:
    paths = files_written(tool_name, args, cwd, home)
    if not paths or (tool_name == "patch" and _v4a_unreadable(str(args.get("patch") or ""))):
        return "file:unreadable", HIGH, False           # what it writes cannot be read
    return max((_file(p, cwd, home) for p in paths), key=lambda r: RANK[r[1]])


def reads_external(tool_name: str, args: dict, cwd: str | None) -> bool:
    """True when the call brings in content written by someone else: the web, a browser, a mailbox or chat server
    (MCP), a file outside the project, a curl or wget, a GitHub issue."""
    args = args if isinstance(args, dict) else {}
    if tool_name in ("web_extract", "web_search") or tool_name.startswith("browser_"):
        return True
    if tool_name == "read_file":
        path = str(args.get("path") or args.get("file_path") or "")
        if not path:
            return False
        root = _norm(os.path.normpath(cwd or os.getcwd())).rstrip("/") + "/"
        return not (_abs(path, cwd) + "/").startswith(root)
    if tool_name.startswith("mcp__") and _clamped(tool_name):
        return False
    split = _mcp_split(tool_name)
    if split:
        return _read_only_verbs(split[1]) and _external_server(split[0])
    if tool_name == "terminal":
        return _cmd_reads_external(str(args.get("command", "")), 0)
    return False


# ---------------------------------------------------------------------------------------------------------- shell
READ_ONLY = {"ls", "cat", "head", "tail", "less", "more", "grep", "rg", "egrep", "fgrep", "wc", "pwd", "echo",
             "printf", "which", "whereis", "whoami", "id", "date", "uname", "printenv", "tree", "du", "df", "stat",
             "file", "sort", "uniq", "cut", "tr", "jq", "yq", "diff", "cmp", "basename", "dirname", "realpath",
             "readlink", "hostname", "uptime", "ps", "true", "false", "test", "[", "awk", "column", "nl", "md5sum",
             "shasum", "sha256sum", "type"}
GIT_READ = {"status", "log", "diff", "show", "rev-parse", "describe", "blame", "ls-files", "grep", "shortlog", "reflog",
            "fetch"}
GH_READ = {"view", "list", "status", "diff", "checks"}
WRAPPERS = {"sudo", "env", "nohup", "time", "nice", "command", "exec", "stdbuf", "doas", "builtin"}
OUTSIDE = {"scp": "shell:scp", "sftp": "shell:sftp", "ssh": "shell:ssh", "ftp": "shell:ftp", "mail": "shell:mail",
           "sendmail": "shell:mail", "mutt": "shell:mail", "nc": "shell:nc", "ncat": "shell:nc", "telnet": "shell:nc"}
PUBLISH = {("npm", "publish"), ("pnpm", "publish"), ("yarn", "publish"), ("twine", "upload"), ("cargo", "publish"),
           ("gem", "push"), ("docker", "push"), ("podman", "push"), ("docker", "login"), ("git", "push")}
CLOUD = {"aws", "gcloud", "az"}
CLOUD_WRITE = {"create", "delete", "put", "update", "deploy", "rm", "cp", "mv", "sync", "mb", "rb", "set", "add",
               "remove", "attach", "detach", "start", "stop", "terminate", "run", "invoke", "publish", "send"}
KUBE_WRITE = {"apply", "delete", "create", "replace", "patch", "scale", "rollout", "edit", "drain", "cordon", "exec"}
SEPS = {";", ";;", ";&", ";;&", "&", "&&", "|", "||", "|&", "\n"}
PIPES = {"|", "|&"}
PUNCT = ";()<>|&\n"
PUNCT_RE = re.compile(r";;&|;;|;&|\|&|\|\||&&|&>>|&>|>&|<&|<<<|<<-|<<|<\(|>\(|>>|>\||<>|[;&|\n()<>]")
CONTINUATION = re.compile(r"\\\r?\n")
ENV_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
OUT_OPS = {">", ">>", ">|", "&>", "&>>", ">&", "<>"}
REDIR_OPS = OUT_OPS | {"<", "<<", "<<-", "<<<", "<&"}
WRITERS = {"tee", "cp", "mv", "install", "ln", "rsync", "touch", "truncate", "rm", "chmod", "chown", "shred",
           "mkdir", "rmdir"}
WRAPPER_VALUE_OPTS = {
    "sudo": {"-u", "-g", "-h", "-p", "-C", "-D", "-R", "-T", "-U", "--user", "--group", "--host", "--prompt"},
    "doas": {"-u", "-C"}, "env": {"-u", "-C", "-S", "--unset", "--chdir"}, "nice": {"-n", "--adjustment"},
    "timeout": {"-s", "-k", "--signal", "--kill-after"}, "stdbuf": {"-i", "-o", "-e"},
}


@dataclass(frozen=True)
class Seg:
    tokens: list
    sub: bool        # may run in a subshell (parentheses, pipe, background): a `cd` here may not stick
    cond: bool       # may not run at all (after && or ||)


def _lex(text: str) -> list[str]:
    lex = shlex.shlex(text, posix=True, punctuation_chars=PUNCT)
    lex.whitespace_split = True
    lex.whitespace = " \t\r"                         # an unquoted newline is a separator, not a blank
    lex.commenters = ""                              # a comment is read as code: the safe side
    return list(lex)


def _decompose(tokens: list[str]) -> list[str]:
    out: list[str] = []
    for t in tokens:
        if t and all(c in PUNCT for c in t):
            out.extend(PUNCT_RE.findall(t))
        else:
            out.append(t)
    return out


def _crude(line: str) -> list[str]:
    return PUNCT_RE.sub(lambda m: f" {m.group(0)} ", line).split()


def _tokens_lines(command: str) -> list[str]:
    """Tokens of a command read line by line (a broken quote only spoils its own line)."""
    out: list[str] = []
    for i, line in enumerate(command.split("\n")):
        if i:
            out.append("\n")
        try:
            out.extend(_decompose(_lex(line)))
        except ValueError:
            out.extend(_crude(line))
    return out


def _tokens_whole(command: str) -> list[str]:
    """Tokens of the whole command: a newline inside quotes stays in its word, an unquoted one is a separator."""
    try:
        return _decompose(_lex(command))
    except ValueError:
        return _tokens_lines(command)


def _build(tokens: list[str]) -> list[Seg]:
    segs: list[Seg] = []
    cur: list[str] = []
    depth = d0 = 0
    paren, prev = False, ""
    for t in tokens:
        if t in SEPS:
            if cur:
                segs.append(Seg(cur, paren or d0 > 0 or prev in PIPES or t in PIPES or t == "&",
                                prev in ("&&", "||")))
            cur, paren, prev = [], False, t
            continue
        if not cur:
            d0 = depth
        if t == "(":
            depth, paren = depth + 1, True
        elif t == ")":
            depth, paren = max(0, depth - 1), True
        cur.append(t)
    if cur:
        segs.append(Seg(cur, paren or d0 > 0 or prev in PIPES, prev in ("&&", "||")))
    return segs


def _segments(command: str) -> list[list[str]]:
    return [s.tokens for s in _build(_tokens_whole(CONTINUATION.sub("", command or "")))]


SHELLS = {"bash", "sh", "zsh", "dash", "ksh", "fish", "ash", "mksh"}
INTERPRETERS = {"python", "python2", "python3", "node", "deno", "bun", "perl", "ruby", "php", "osascript", "pwsh",
                "powershell", "Rscript", "lua", "tclsh"}
INLINE_FLAGS = {"-c", "-e", "-r", "-Command", "--command", "--eval", "-p", "--print"}
RUNNERS = {"npm", "pnpm", "yarn", "bun"}
MAKES = {"make", "gmake", "just", "task"}
GIT_VALUE_OPTS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--config-env"}
GH_VALUE_OPTS = {"-R", "--repo", "--hostname"}
MAX_DEPTH = 3


def _strip(tokens: list[str], value_opts: set[str]) -> list[str]:
    """Arguments without options, skipping the value of options that take one ("-C dir", "--repo x")."""
    out, skip = [], False
    for t in tokens:
        if skip:
            skip = False
            continue
        if t in value_opts:
            skip = True
            continue
        if t.startswith("-"):
            continue
        out.append(t)
    return out


def _redirects(tokens: list[str]) -> list[str]:
    """Targets of output redirections (not /dev/null, not a file descriptor)."""
    out = []
    for n, t in enumerate(tokens):
        if t in OUT_OPS:
            target = tokens[n + 1] if n + 1 < len(tokens) else ""
            if (target in ("/dev/null", "/dev/stdout", "/dev/stderr", "", "(", ">(", "<(", "$") or
                    target.startswith("&") or (t == ">&" and re.fullmatch(r"\d+|-", target))):
                continue
            out.append(target)
    return out


def _strip_wrappers(toks: list[str]) -> list[str]:
    while toks and os.path.basename(toks[0]) in WRAPPERS | {"timeout"}:
        wrapper = os.path.basename(toks[0])
        toks = toks[1:]
        value_opts = WRAPPER_VALUE_OPTS.get(wrapper, set())
        while toks and (toks[0].startswith("-") or ENV_ASSIGN.match(toks[0])):
            toks = toks[2:] if toks[0] in value_opts and len(toks) > 1 else toks[1:]
        if wrapper == "timeout" and toks:
            toks = toks[1:]                                  # the duration
    return toks


def _unwrap(tokens: list[str]) -> list[str]:
    """The program and its arguments: without redirections, leading VAR=x, grouping and wrappers (sudo, env...)."""
    toks: list[str] = []
    skip = False
    for n, t in enumerate(tokens):
        if skip:
            skip = False
        elif t in REDIR_OPS:
            skip = True                                      # the operator and its target
        elif t.isdigit() and n + 1 < len(tokens) and tokens[n + 1] in REDIR_OPS:
            continue                                         # a file descriptor: 2>file
        elif t in ("(", ")", "$", "<(", ">(", "{", "}") or (not toks and ENV_ASSIGN.match(t)):
            continue
        else:
            toks.append(t)
    return _strip_wrappers(toks)


def _write_args(prog: str, args: list[str]) -> list[str]:
    """Paths a write-capable command is given."""
    if prog == "dd":
        return [a[3:] for a in args if a.startswith("of=")]
    if prog in WRITERS:
        return [a for a in args if not a.startswith("-")]
    return []


def _xargs_rest(args: list[str]) -> list[str]:
    skip = False
    for n, a in enumerate(args):
        if skip:
            skip = False
            continue
        if a in ("-I", "-n", "-P", "-L", "-s", "-d", "-E", "-a"):
            skip = True
            continue
        if a.startswith("-"):
            continue
        return args[n:]
    return []


def _shell_segment(tokens: list[str], cwd, home, depth: int = 0) -> tuple[str, str]:
    """One command. A sensitive path it writes (redirect or argument) caps it; when the working directory is unknown
    a relative write is at least high stakes."""
    forced = False
    base = "/" if cwd == UNKNOWN else cwd
    targets = _redirects(tokens)
    toks = _unwrap(tokens)
    if toks:
        targets += _write_args(os.path.basename(toks[0]), toks[1:])
    for target in targets:
        target = _expand(target, home)
        if "$" in target or "`" in target:
            forced = True
        elif cwd == UNKNOWN and not os.path.isabs(target):
            forced = True
        elif _file(target, base, home)[1] == CAP:
            return "file:sensitive", CAP
    t, s = _core(tokens, cwd, home, depth)
    return t, (HIGH if forced and RANK[s] < RANK[HIGH] else s)


def _core(tokens: list[str], cwd, home, depth: int = 0) -> tuple[str, str]:
    if depth > MAX_DEPTH:
        return "shell:nested", HIGH
    writes = bool(_redirects(tokens))
    # command or process substitution ($( ), ` `, <( ), >( )): what runs is computed, so the call is illegible
    substitution = any("`" in t or "$(" in t or t in ("<(", ">(")
                       or (t in ("$", "<", ">") and n + 1 < len(tokens) and tokens[n + 1] == "(")
                       for n, t in enumerate(tokens))
    toks = _unwrap(tokens)
    if not toks:
        return "shell:unknown", MEDIUM
    if toks[0].startswith("$"):
        return "shell:dynamic", HIGH                         # the program is computed: illegible
    prog = os.path.basename(toks[0])
    args = toks[1:]
    if substitution:
        return f"shell:{prog}", HIGH
    if prog in ("eval", "source", "."):
        return "shell:eval", HIGH
    if prog in SHELLS:
        if "-c" in args:
            i = args.index("-c")
            inner = args[i + 1] if i + 1 < len(args) else ""
            t, st, _ = _shell(inner, cwd, home, depth + 1)
            return t, st
        script = next((a for a in args if not a.startswith("-")), "")
        return (f"shell:{prog}:{os.path.basename(script)}" if script else f"shell:{prog}"), MEDIUM
    if prog == "xargs":
        rest = _xargs_rest(args)
        return _shell_segment(rest, cwd, home, depth + 1) if rest else ("shell:xargs", MEDIUM)
    base = re.sub(r"\d+(\.\d+)*$", "", prog)
    if prog in INTERPRETERS or base in INTERPRETERS:
        if INLINE_FLAGS & set(args):
            return f"shell:{prog}:inline", HIGH
        if "-m" in args:
            i = args.index("-m")
            mod = args[i + 1] if i + 1 < len(args) else ""
            return f"shell:{prog}:-m:{mod}", MEDIUM
        script = next((a for a in args if not a.startswith("-")), "")
        return (f"shell:{prog}:{os.path.basename(script)}" if script else f"shell:{prog}"), MEDIUM
    sub = next((a for a in args if not a.startswith("-")), "")
    if prog in OUTSIDE:
        return OUTSIDE[prog], HIGH
    if prog == "git":
        plain = _strip(args, GIT_VALUE_OPTS)
        sub = plain[0] if plain else ""
        if "push" in plain:
            return "shell:git:push", HIGH
    if prog == "gh":
        plain = _strip(args, GH_VALUE_OPTS)
        sub = plain[0] if plain else ""
    if (prog, sub) in PUBLISH:
        return f"shell:{prog}:{sub}", HIGH
    if prog in RUNNERS and sub == "run":
        plain = [a for a in args if not a.startswith("-")]
        script = plain[1] if len(plain) > 1 else ""
        return f"shell:{prog}:run:{script}", MEDIUM
    if prog == "npx":
        return f"shell:npx:{sub}", MEDIUM
    if prog in MAKES:
        plain = _strip(args, {"-C", "-f", "-j", "--directory", "--file", "--jobs"})
        return f"shell:{prog}:{plain[0] if plain else 'default'}", MEDIUM
    if prog in ("curl", "wget"):
        joined = " ".join(args)
        sends = (re.search(r"(^|\s)(-d|--data\S*|--json|-F|--form\S*|-T|--upload-file|--post-data|--post-file)"
                           r"(\s|=|$)", joined)
                 or re.search(r"(-X|--request|--method)[\s=]*(POST|PUT|PATCH|DELETE)", joined, re.I))
        if sends:
            return f"shell:{prog}:send", HIGH
        return f"shell:{prog}", MEDIUM if writes or "-o" in args or "-O" in args else FREE
    if prog == "rsync":
        return "shell:rsync", HIGH if any(re.match(r"^[^/]*:", a) for a in args if not a.startswith("-")) else MEDIUM
    if prog == "gh":
        if sub in ("pr", "issue", "repo", "release", "run", "workflow"):
            plain = _strip(args, GH_VALUE_OPTS)
            verb = plain[1] if len(plain) > 1 else ""
            if verb in GH_READ:
                return f"shell:gh:{sub}", FREE
        if sub == "api" and not re.search(r"(-X|--method)\s*(POST|PUT|PATCH|DELETE)|-f\s|-F\s|--field|--input",
                                          " ".join(args)):
            return "shell:gh:api", FREE
        return f"shell:gh:{sub or 'unknown'}", HIGH
    if prog == "kubectl":
        return f"shell:kubectl:{sub}", HIGH if sub in KUBE_WRITE else FREE
    if prog == "terraform":
        return f"shell:terraform:{sub}", HIGH if sub in ("apply", "destroy", "import") else MEDIUM
    if prog in CLOUD:
        return f"shell:{prog}:{sub}", HIGH if CLOUD_WRITE & set(args) else FREE
    if prog == "git":
        if not writes and (sub in GIT_READ or (sub in ("branch", "tag", "remote") and len(args) <= 2
                                                and not any(a in ("-d", "-D", "--delete", "add", "remove", "rm",
                                                                  "set-url", "rename") for a in args))):
            return f"shell:git:{sub}", FREE
        return f"shell:git:{sub or 'unknown'}", MEDIUM
    if prog == "find" and not writes and not ({"-delete", "-exec", "-execdir", "-ok", "-fprint"} & set(args)):
        return "shell:find", FREE
    if prog == "sed" and not writes and not any(a.startswith("-i") or a == "--in-place" for a in args):
        return "shell:sed", FREE
    if prog in READ_ONLY and not writes:
        return f"shell:{prog}", FREE
    return f"shell:{prog}", MEDIUM


def _cd_kind(tokens: list[str]):
    toks = _unwrap(tokens)
    if toks and os.path.basename(toks[0]) in ("cd", "pushd", "popd"):
        return os.path.basename(toks[0]), [a for a in toks[1:] if a == "-" or not a.startswith("-")]
    return None


def _move(state: tuple, kind: str, args: list[str], home: str) -> tuple:
    """The (cwd, previous cwd) after a cd. A directory that cannot be worked out becomes UNKNOWN."""
    cwd, old = state
    if kind == "popd":
        return UNKNOWN, cwd
    if not args:
        return (UNKNOWN, cwd) if kind == "pushd" else (_norm(home), cwd)
    d = args[0]
    if d == "-":
        return (old if old is not None else UNKNOWN), cwd
    d = _expand(d, home)
    if d.startswith("~") or any(c in d for c in "$`*?[{"):
        return UNKNOWN, cwd
    if cwd == UNKNOWN and not os.path.isabs(d):
        return UNKNOWN, cwd
    return _abs(d, cwd, home), cwd


def _run(segs: list[Seg], start: str, home: str, depth: int) -> tuple[str, str]:
    best, first = ("shell:unknown", MEDIUM), True
    states = [(start, None)]       # every (cwd, previous cwd) the shell may be in: a cd that may not stick adds one
    for seg in segs:
        top = None
        for cwd, _ in states:
            r = _shell_segment(seg.tokens, cwd, home, depth)
            if top is None or RANK[r[1]] > RANK[top[1]]:
                top = r
        if first or RANK[top[1]] > RANK[best[1]]:
            best, first = top, False
        cd = _cd_kind(seg.tokens)
        if cd:
            moved = [_move(st, cd[0], cd[1], home) for st in states]
            states = list(dict.fromkeys(states + moved if seg.sub or seg.cond else moved))
            if len(states) > 32:
                states = [(UNKNOWN, None)]
    return best


def _shell(command: str, cwd=None, home=None, depth: int = 0) -> tuple[str, str, bool]:
    """Typed twice, and the riskier reading wins: by lines, then with the whole command tokenised (quotes may span
    lines). Never `splitlines()`: bash does not split on \\x0c or U+2028."""
    home = _norm(home or os.path.expanduser("~"))
    command = CONTINUATION.sub("", command or "")
    start = cwd or os.getcwd()
    by_lines = _run(_build(_tokens_lines(command)), start, home, depth)
    whole = _run(_build(_tokens_whole(command)), start, home, depth)
    best = whole if RANK[whole[1]] >= RANK[by_lines[1]] else by_lines
    return best[0], best[1], False                  # a command is never reversible by Clearance


def _seg_reads_external(tokens: list[str], depth: int) -> bool:
    toks = _unwrap(tokens)
    if not toks or depth > MAX_DEPTH:
        return False
    prog, args = os.path.basename(toks[0]), toks[1:]
    if prog in ("curl", "wget"):
        return True
    if prog in SHELLS and "-c" in args:
        i = args.index("-c")
        return _cmd_reads_external(args[i + 1] if i + 1 < len(args) else "", depth + 1)
    if prog == "xargs":
        rest = _xargs_rest(args)
        return bool(rest) and _seg_reads_external(rest, depth + 1)
    if prog == "gh":
        plain = _strip(args, GH_VALUE_OPTS)
        if plain[:1] == ["api"]:
            return not any(a in ("-X", "--method", "-f", "-F", "--field", "--raw-field", "--input")
                           or a.startswith(("--method=", "-X", "--field=", "--raw-field=", "--input="))
                           for a in args)
        return len(plain) > 1 and plain[0] in ("issue", "pr") and plain[1] == "view"
    return False


def _cmd_reads_external(command: str, depth: int) -> bool:
    command = CONTINUATION.sub("", command or "")
    return any(_seg_reads_external(seg.tokens, depth)
               for tokens in (_tokens_lines(command), _tokens_whole(command)) for seg in _build(tokens))


# ------------------------------------------------------------------------------------------------------------ MCP
MCP = re.compile(r"^mcp__(.+?)__(.+)$")                   # Hermes >= 0.23: mcp__<server>__<tool>
MCP_LEGACY = re.compile(r"^mcp_([A-Za-z0-9-]+)_(.+)$")
# Servers that bring in text written by other people: reading them is reading untrusted content.
EXTERNAL_SERVERS = ("mail", "gmail", "outlook", "imap", "slack", "discord", "telegram", "whatsapp", "web", "fetch",
                    "browser", "rss", "reddit", "twitter", "x", "brave", "search", "exa", "tavily", "serp",
                    "playwright", "puppeteer", "firecrawl", "crawl", "scrape", "github")
WHOLE_WORD_SERVERS = {"x", "exa"}                       # too short to match inside another name
HIGH_VERBS = {"send", "post", "publish", "email", "mail", "sms", "tweet", "message", "notify", "invite", "share", "pay",
              "payment", "payments", "purchase", "buy", "charge", "transfer", "refund", "order", "checkout", "invoice",
              "payout", "withdraw", "deposit", "broadcast", "reply", "comment", "dm", "forward", "respond", "text"}
MEDIUM_VERBS = {"create", "update", "add", "set", "put", "patch", "edit", "modify", "upsert", "insert", "save", "write",
                "delete", "remove", "archive", "move", "rename", "upload", "assign", "close", "complete", "merge",
                "approve", "schedule", "cancel", "enable", "disable", "tag", "label", "mark", "append", "clear"}
FREE_VERBS = {"get", "list", "search", "read", "fetch", "find", "query", "lookup", "describe", "show", "view", "count",
              "check", "status", "retrieve", "download", "export", "info", "inspect", "preview", "summarize"}


BROWSE_VERBS = {"navigate", "scrape", "crawl", "browse", "snapshot", "screenshot"}   # reads, for reads_external only
CONNECTORS = {"and", "or", "then", "to", "via", "plus", "with"}
CLAMPED = re.compile(r"^.{55}_[0-9a-f]{8}$")            # a 64-character name Hermes shortened with a hash
NOUN_WORDS = {"message", "messages", "email", "emails", "mail", "sms", "notification", "notifications"}


def _words(name: str) -> set[str]:
    return {w.lower() for w in re.split(r"[_\-.\s]+|(?<=[a-z])(?=[A-Z])", name) if w}


def _read_only_verbs(tool: str) -> bool:
    """A free verb somewhere, and no high or medium verb (an ambiguous noun does not count, unless the name joins
    actions with a connector word: "get_and_forward_message")."""
    w = _words(tool)
    nouns = set() if w & CONNECTORS else NOUN_WORDS
    return bool(w & (FREE_VERBS | BROWSE_VERBS)) and not ((HIGH_VERBS | MEDIUM_VERBS) & (w - nouns))


def _mcp(server: str, tool: str) -> tuple[str, str, bool]:
    w = _words(tool)
    lead = re.split(r"[_\-.\s]+|(?<=[a-z])(?=[A-Z])", tool)[0].lower()
    if lead in FREE_VERBS and not (w & CONNECTORS) and not ((HIGH_VERBS | MEDIUM_VERBS) & (w - NOUN_WORDS)):
        return f"mcp:{server}:{tool}", FREE, False        # "get_message": the noun is not an action
    stakes = HIGH if w & HIGH_VERBS else MEDIUM if w & MEDIUM_VERBS else FREE if w & FREE_VERBS else HIGH
    return f"mcp:{server}:{tool}", stakes, False


def _clamped(name: str) -> bool:
    return bool(CLAMPED.match(name))


def _mcp_split(tool_name: str) -> tuple[str, str] | None:
    m = MCP.match(tool_name) or MCP_LEGACY.match(tool_name)
    return (m.group(1), m.group(2)) if m else None


def _external_server(server: str) -> bool:
    s = server.lower()
    words = {w for w in re.split(r"[^a-z0-9]+", s) if w}
    return any((k in words) if k in WHOLE_WORD_SERVERS else (k in s) for k in EXTERNAL_SERVERS)


# ----------------------------------------------------------------------------------------------------------- main
def _override(t: str, stakes: str, overrides: dict | None) -> str:
    if not overrides or (stakes == CAP and t.startswith(PROTECTED)):
        return stakes
    if t in overrides:
        return _valid(overrides[t], stakes)
    for pat, val in overrides.items():
        if fnmatch.fnmatchcase(t, pat):
            return _valid(val, stakes)
    return stakes


def _valid(val, default):
    v = str(val).strip().lower()
    return v if v in RANK else default


def _summary(tool: str, args: dict, t: str) -> str:
    if tool == "terminal":
        what = str(args.get("command", ""))
    elif "path" in args:
        what = str(args.get("path"))
    else:
        keys = [f"{k}={str(v)[:40]}" for k, v in list(args.items())[:3]]
        what = f"{tool}({', '.join(keys)})"
    what = " ".join(what.split())
    return f"{t}: {what[:200]}"


def classify(tool_name: str, args: dict | None, *, cwd: str | None = None, overrides: dict | None = None,
             home: str | None = None) -> Action:
    args = args if isinstance(args, dict) else {}
    home = home or os.path.expanduser("~")
    if tool_name in FREE_TOOLS:
        t, stakes, rev = f"read:{tool_name}", FREE, False
    elif tool_name in ("write_file", "patch"):
        t, stakes, rev = _files(tool_name, args, cwd, home)
    elif tool_name == "terminal":
        t, stakes, rev = _shell(str(args.get("command", "")), cwd, home)
    elif tool_name in TOOLS:
        t, stakes, rev = TOOLS[tool_name]
    elif tool_name.startswith("kanban_"):
        t, stakes, rev = f"kanban:{tool_name[len('kanban_'):]}", LOW, False
    elif tool_name.startswith("mcp__") and _clamped(tool_name):
        t, stakes, rev = f"tool:{tool_name}", HIGH, False   # shortened by Hermes: the tool name is cut
    elif _mcp_split(tool_name):
        t, stakes, rev = _mcp(*_mcp_split(tool_name))
    else:
        t, stakes, rev = f"tool:{tool_name}", HIGH, False
    stakes = _override(t, stakes, overrides)
    rev = rev and t == "file:write"                 # only a write inside the project can be undone
    return Action(type=t, stakes=stakes, reversible=rev, summary=_summary(tool_name, args, t))
