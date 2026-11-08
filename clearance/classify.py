# Copyright 2026 Otsoa Dubief
# SPDX-License-Identifier: Apache-2.0
"""What a tool call is: its action type (the unit whose record is kept) and its stakes.

Grid from the earned-autonomy study: an action is classed by what it does, not by the tool. Reads are free. Writes
inside the project are low stakes and reversible; writes elsewhere, commands, code and delegation are medium;
anything that leaves the machine (messages to others, publications, pushes, uploads) and money are high. Some
actions are capped and always ask: secrets, the agent's own skills, plugins and guardrails, sensitive files. An
action whose effect cannot be read is treated as high stakes.

Types are fine-grained so that a record says something: shell commands are typed by program (and by subcommand
when the subcommand changes the stakes), MCP tools by server and tool. A program that runs other commands (find
-exec, awk system(), sed's e, parallel, watch) takes the stakes of what it runs, typed by it.
"""
from __future__ import annotations

import fnmatch
import itertools
import os
import re
import shlex
import threading
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


_CACHE = threading.local()                       # symlink resolutions, valid for one classify() call


def _real(full: str) -> str:
    """The symlink-resolved path (the part that exists is resolved, the rest is kept)."""
    memo = getattr(_CACHE, "memo", None)
    if memo is not None and full in memo:
        return memo[full]
    try:
        real = _norm(os.path.realpath(full))
        if real.startswith("/System/Volumes/Data/"):         # macOS firmlink: the data volume is the root
            real = real[len("/System/Volumes/Data"):]
    except (OSError, ValueError):
        real = full
    if memo is not None:
        memo[full] = real
    return real


SENSITIVE_FRAGMENTS = ("authorized_keys", "known_hosts", "id_ed25519", "id_ecdsa", ".netrc", ".hermes/")


def _sensitive(probe: str) -> bool:
    low = probe.lower()
    return bool(any(f in low for f in SENSITIVE_FRAGMENTS)
                or any(d.lower() in low + "/" for d in SENSITIVE_DIRS)
                or low.startswith(tuple(x.lower() for x in SENSITIVE_PREFIXES))
                or SENSITIVE_NAME.match(low.rstrip("/").rsplit("/", 1)[-1]))


def _file(path: str, cwd: str | None, home: str) -> tuple[str, str, bool]:
    base = cwd or os.getcwd()
    full = _abs(path, base, home)
    real = _real(full)
    if _sensitive(full) or _sensitive(real):
        return "file:sensitive", CAP, False
    lexroot = _norm(os.path.normpath(base)).rstrip("/") + "/"
    try:
        realroot = _real(_norm(os.path.normpath(base))).rstrip("/") + "/"
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
        split = _mcp_split(tool_name)                    # the tool name is cut: only the server tells
        return _external_server(split[0] if split else tool_name[5:])
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
CONTINUATION = re.compile(r"(\\+)(\r?\n)")


def _join_lines(command: str) -> str:
    """Remove line continuations: only an ODD number of backslashes before a newline joins the lines."""
    return CONTINUATION.sub(lambda m: m.group(1)[:-1] if len(m.group(1)) % 2 else m.group(0), command or "")
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
    sep: str = ""    # the separator before it


FD_PREFIX = re.compile(r"(?<![\w$])\d+(?=[<>])")          # the 2 of 2>file (glued: "timeout 5 >f" keeps its 5)


def _lex(text: str) -> list[str]:
    lex = shlex.shlex(FD_PREFIX.sub(" ", text), posix=True, punctuation_chars=PUNCT)
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
    return PUNCT_RE.sub(lambda m: f" {m.group(0)} ", FD_PREFIX.sub(" ", line)).split()


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
                                prev in ("&&", "||"), prev))
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
        segs.append(Seg(cur, paren or d0 > 0 or prev in PIPES, prev in ("&&", "||"), prev))
    return segs


def _segments(command: str) -> list[list[str]]:
    return [s.tokens for s in _build(_tokens_whole(_join_lines(command)))]


SHELLS = {"bash", "sh", "zsh", "dash", "ksh", "fish", "ash", "mksh"}
INTERPRETERS = {"python", "python2", "python3", "node", "deno", "bun", "perl", "ruby", "php", "osascript", "pwsh",
                "powershell", "Rscript", "lua", "tclsh"}
INLINE_FLAGS = {"-c", "-e", "-r", "-Command", "--command", "--eval", "-p", "--print"}
RUNNERS = {"npm", "pnpm", "yarn", "bun"}
MAKES = {"make", "gmake", "just", "task"}
GIT_VALUE_OPTS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--config-env"}
GH_VALUE_OPTS = {"-R", "--repo", "--hostname"}
# Options whose value comes before the subcommand (kubectl -n ns get, aws --profile p s3, gcloud --project p compute):
# the value is a name of the user's (a namespace, an account), never the subcommand.
SUB_VALUE_OPTS = {"-n", "--namespace", "--profile", "--project", "--context", "--region", "-C", "--kubeconfig"}
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
            t = toks[0]
            takes_value = t in value_opts or (len(t) > 2 and t[1] != "-" and "-" + t[-1] in value_opts)  # -iu root
            toks = toks[2:] if takes_value and len(toks) > 1 else toks[1:]
        if wrapper == "timeout" and toks:
            toks = toks[1:]                                  # the duration
    return toks


def _unwrap(tokens: list[str], wrappers: bool = True) -> list[str]:
    """The program and its arguments: without redirections, leading VAR=x, grouping and wrappers (sudo, env...)."""
    toks: list[str] = []
    skip = False
    for n, t in enumerate(tokens):
        if skip:
            skip = False
        elif t in REDIR_OPS:
            skip = True                                      # the operator and its target
        elif t in ("(", ")", "$", "<(", ">(", "{", "}") or (not toks and ENV_ASSIGN.match(t)):
            continue
        else:
            toks.append(t)
    return _strip_wrappers(toks) if wrappers else toks


def _leading_flags(args: list[str]) -> list[str]:
    out = []
    for a in args:
        if not a.startswith("-"):
            break
        out.append(a)
    return out


def _inline_cluster(args: list[str]) -> bool:
    """An interpreter flag cluster that carries code: python3 -Bc, perl -ne."""
    return any(re.fullmatch(r"-[A-Za-z]{2,}", a) and ("c" in a or "e" in a) for a in _leading_flags(args))


def _positionals(args: list[str]) -> list[str]:
    return [a for a in args if not a.startswith("-")]


def _opt_values(args: list[str], short: str, long: tuple[str, ...]) -> list[str]:
    """Values of an option given as -o x, -ox, -ro x, --output x or --output=x."""
    out = []
    for n, a in enumerate(args):
        nxt = args[n + 1] if n + 1 < len(args) else ""
        if a in long:
            out.append(nxt)
        elif any(a.startswith(f"{l}=") for l in long):
            out.append(a.split("=", 1)[1])
        elif re.match(r"-[A-Za-z]*" + short, a) and not a.startswith("--"):
            rest = a[a.index(short, 1) + 1:]
            out.append(rest or nxt)
    return out


AWKS = {"awk", "gawk", "mawk", "nawk"}
FIND_WRITES = {"-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint", "-fprint0", "-fprintf", "-fls"}

# awk options. Short flags that take no value and neither write nor load code (gawk, mawk, BWK, busybox):
AWK_FLAGS = set("bcCghIkMnNOPrsStV")
# gawk long options (getopt_long also takes an unambiguous abbreviation). "load": code comes from a file, a library
# or the debugger's commands; "write": the call writes a file (profile, variable dump, pretty-print, persistence).
AWK_LONG = {"field-separator": "value", "assign": "value", "source": "code", "lint": "flag",
            "characters-as-bytes": "flag", "traditional": "flag", "copyright": "flag", "gen-pot": "flag",
            "help": "flag", "usage": "flag", "trace": "flag", "csv": "flag", "bignum": "flag",
            "non-decimal-data": "flag", "use-lc-numeric": "flag", "optimize": "flag", "posix": "flag",
            "re-interval": "flag", "no-optimize": "flag", "sandbox": "flag", "lint-old": "flag", "version": "flag",
            "file": "load", "exec": "load", "include": "load", "load": "load", "debug": "load",
            "dump-variables": "write", "pretty-print": "write", "profile": "write", "persist": "write"}
AWK_KEYWORDS = {"BEGIN", "END", "BEGINFILE", "ENDFILE", "function", "func", "if", "else", "while", "for", "do",
                "break", "continue", "next", "nextfile", "exit", "return", "delete", "in", "getline", "print",
                "printf", "switch", "case", "default"}
AWK_HEADERS = {"if", "while", "for"}                    # their parenthesis is followed by a statement
# Keywords followed by an expression in every awk. The others leave a following slash ambiguous: words only gawk
# reserves (case, default, switch, BEGINFILE...) are variables for BWK awk, so their slash may be a division.
AWK_EXPECT = {"print", "printf", "return", "exit", "do", "else"}
AWK_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
AWK_NUMBER = re.compile(r"0[xX][0-9A-Fa-f]+|(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?|\.")
AWK_OP = re.compile(r"\*\*=|\*\*|&&|\|\||\|&|>>|>=|<=|==|!=|!~|\+\+|--|[-+*/%^]=|[-+*/%^!<>|?:~=,;{}()\[\]$]")
AWK_CONTINUATION = re.compile(r"\\[ \t]*\r?\n")
AWK_CLASS = re.compile(r"\[:[A-Za-z]+:\]")


def _awk_regex_end(prog: str, i: int) -> int | None:
    """The index after the regex literal that opens at prog[i], or None when awks could disagree on where it ends:
    a slash, backslash or nested bracket inside a bracket expression (gawk reads on, other awks stop), a newline."""
    j, n = i + 1, len(prog)
    while j < n:
        c = prog[j]
        if c == "\\":
            j += 2
        elif c == "\n":
            return None
        elif c == "/":
            return j + 1
        elif c == "[":
            j += 1
            j += prog.startswith("^", j)
            j += prog.startswith("]", j)                 # []...] and [^]...]: a leading ] is a character
            while j < n and prog[j] != "]":
                m = AWK_CLASS.match(prog, j)
                if m:
                    j = m.end()
                elif prog[j] in "[\\/\n":
                    return None
                else:
                    j += 1
            if j >= n:
                return None
            j += 1
        else:
            j += 1
    return None


def _awk_tokens(prog: str) -> list[tuple[str, str]] | None:
    """The tokens of an awk program, (kind, text) with kind str, re, word, num, op or nl; None when it cannot be read
    with certainty: a stray character or an @-form (gawk directives, indirect calls), an ambiguous slash, unbalanced
    brackets, a regex whose end awks disagree on, a broken string, continuation or comment."""
    out: list[tuple[str, str]] = []
    i, n = 0, len(prog)
    state = "expect"            # what a slash is: "expect" a regex, "after" an operand (division), or "ambiguous"
    parens: list[bool] = []     # open parentheses: True for an if/while/for/switch header
    braces = 0
    header = False              # the last word opens a header
    while i < n:
        c = prog[i]
        if c in " \t\r":
            i += 1
            continue
        if c == "\\":                                   # a line continuation, nothing else
            m = AWK_CONTINUATION.match(prog, i)
            if not m:
                return None
            i = m.end()
            continue
        if c == "#":                                    # a comment ends at the end of the line
            end = prog.find("\n", i)
            end = n if end < 0 else end
            if prog[i:end].rstrip(" \t\r").endswith("\\"):
                return None
            i = end
            continue
        if c == "\n":
            out.append(("nl", c))
            state, header = "expect", False
            i += 1
            continue
        if c == '"':
            j = i + 1
            while j < n and prog[j] != '"':
                if prog[j] == "\n":
                    return None
                j += 2 if prog[j] == "\\" else 1
            if j >= n:
                return None
            out.append(("str", prog[i + 1:j]))
            i, state, header = j + 1, "after", False
            continue
        if c == "/" and state != "after":
            j = None if state == "ambiguous" else _awk_regex_end(prog, i)
            if j is None:
                return None
            out.append(("re", prog[i:j]))
            i, state, header = j, "after", False
            continue
        m = AWK_WORD.match(prog, i)
        if m:
            w, i = m.group(0), m.end()
            out.append(("word", w))
            header = w in AWK_HEADERS
            state = ("expect" if w in AWK_EXPECT else
                     "ambiguous" if w in AWK_KEYWORDS or w == "length" else "after")
            continue
        m = AWK_NUMBER.match(prog, i) or AWK_OP.match(prog, i)
        if not m:
            return None                                 # @ (gawk directives, indirect calls) or a stray character
        op, i = m.group(0), m.end()
        number = op[0] in "0123456789."
        out.append(("num" if number else "op", op))
        if op == "(":
            parens.append(header)
            state = "expect"
        elif op == ")":
            if not parens:
                return None
            state = "expect" if parens.pop() else "after"
        elif op == "]" or number:
            state = "after"
        elif op in ("++", "--", "$"):
            state = "ambiguous"
        else:
            state = "expect"
        if op in ("{", "}"):
            braces += 1 if op == "{" else -1
            if braces < 0:
                return None
        header = False
    return None if parens or braces else out


AWK_BEFORE_PIPE = {";", "{", "}", "(", "=", ",", "&&", "||", "!"}   # what may precede `"cmd" | getline`


def _awk_string(text: str) -> str | None:
    """The value of an awk string literal, or None for an escape awks read differently (octal, hex, unknown)."""
    out, i = [], 0
    while i < len(text):
        if text[i] == "\\":
            e = text[i + 1:i + 2]
            if e not in ('"', "\\", "/", "n", "t"):
                return None
            out.append({"n": "\n", "t": "\t"}.get(e, e))
            i += 2
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def _awk_read(prog: str) -> tuple[bool, list[str] | None]:
    """(writes, commands) of an awk program. It writes or runs something only through: print/printf redirected
    (`>` outside parentheses, `>>`, `|`), a command pipe (`|`, `|&`: `"cmd" | getline` too), `system`,
    `getline < file`, or gawk's @-forms (@include, @load, indirect calls); comparisons are not writes. A command is
    read when it is one string literal: `system("cmd")`, `print | "cmd"`, `"cmd" | getline`; anything else (a
    variable, a concatenation, an @-form) makes the commands unreadable (None). A program that cannot be read with
    certainty writes, and runs something unreadable when its text holds `system`, `|` or `@`."""
    toks = _awk_tokens(prog)
    if toks is None:
        return True, (None if re.search(r"system|[|@]", prog) else [])
    writes, cmds = False, []
    depth = 0                   # parenthesis depth
    print_depth = None          # parenthesis depth of the print/printf statement being read
    getline = False             # a getline in the current statement
    none = ("nl", "")
    for k, (kind, val) in enumerate(toks):
        nxt = toks[k + 1] if k + 1 < len(toks) else none
        if kind == "nl":
            getline = False
        elif kind == "word" and val == "system":
            call = toks[k + 1:k + 4]
            if [t[0] for t in call] != ["op", "str", "op"] or call[0][1] != "(" or call[2][1] != ")":
                return True, None
            cmds.append(_awk_string(call[1][1]))
        elif kind == "word" and val in ("print", "printf"):
            print_depth = depth
        elif kind == "word" and val == "getline":
            getline = True
        elif kind == "op" and val in ("|", "|&"):
            if nxt == ("word", "getline"):              # "cmd" | getline: the command is the string before
                before = toks[k - 2] if k >= 2 else none
                if k < 1 or toks[k - 1][0] != "str" or not (before[0] == "nl" or before[1] in AWK_BEFORE_PIPE):
                    return True, None
                cmds.append(_awk_string(toks[k - 1][1]))
            elif print_depth is not None:               # print | "cmd": the command is the string after
                after = toks[k + 2] if k + 2 < len(toks) else none
                if nxt[0] != "str" or not (after[0] == "nl" or after[1] in (";", "}")):
                    return True, None
                cmds.append(_awk_string(nxt[1]))
            else:
                return True, None
        elif kind == "op":
            if val == ">>" or (val == ">" and print_depth is not None and depth <= print_depth):
                writes = True
            elif val == "<" and getline:
                writes = True
            depth += 1 if val == "(" else -1 if val == ")" else 0
            if val in (";", "}"):
                print_depth = None
            if val in (";", "{", "}"):
                getline = False
    if None in cmds:
        return True, None
    return writes or bool(cmds), cmds


def _awk_program_writes(prog: str) -> bool:
    """An awk program writes or runs something (see _awk_read)."""
    return _awk_read(prog)[0]


def _awk_call(args: list[str]) -> tuple[bool, list[str] | None, list[str]]:
    """(writes, commands, program texts) of an awk call. writes: it may write a file or run a command. commands: the
    literal commands it runs, or None when what it runs cannot be read: a program or extension read from a file, an
    option we do not know, an option after the program, a computed command. The texts read are the program and
    every value an awk could take for one: gawk's -e/--source, and the value of an option BWK awk (macOS) ignores
    (`--assign x`, `-nF x`): it runs the next word as the program."""
    texts: list[str] = []
    writes = False
    n = 0
    while n < len(args):
        a = args[n]
        if a == "--":
            n += 1
            break
        if a == "-" or not a.startswith("-"):
            break
        if a.startswith("--"):
            name, eq, val = a[2:].partition("=")
            kinds = [AWK_LONG[name]] if name in AWK_LONG else [v for k, v in AWK_LONG.items() if k.startswith(name)]
            if len(kinds) != 1 or kinds[0] == "load":
                return True, None, texts
            if kinds[0] == "write":
                writes = True                           # the file is attached (=file) or a default name
            elif kinds[0] != "flag" and not eq:
                if n + 1 >= len(args):
                    return True, None, texts
                n += 1
                texts.append(args[n])
            elif kinds[0] == "code":
                texts.append(val)
        else:
            for j, ch in enumerate(a[1:], 1):
                if ch in AWK_FLAGS:
                    continue
                if ch == "L":                           # gawk's lint level, attached
                    break
                if ch in "opd":                         # gawk's pretty-print, profile, variable dump: the file is
                    writes = True                       # the rest of the word or a default name
                    break
                if ch not in "Fve":
                    return True, None, texts            # -f -E -i -l -D -W, or an option we do not know
                if j + 1 == len(a):                     # the value is the next word
                    if n + 1 >= len(args):
                        return True, None, texts
                    n += 1
                    if ch == "e" or a not in ("-F", "-v"):
                        texts.append(args[n])
                elif ch == "e":
                    texts.append(a[j + 1:])
                break
        n += 1
    if n < len(args):
        texts.append(args[n])
        if any(x.startswith("-") and x != "-" for x in args[n + 1:]):
            return True, None, texts                    # an option after the program: some awks still read it
    cmds: list[str] = []
    for t in texts:
        w, c = _awk_read(t)
        if c is None:
            return True, None, texts
        writes, cmds = writes or w, cmds + c
    return writes, cmds, texts


def _ro_writes(prog: str, args: list[str]) -> bool:
    """A normally read-only program that writes, deletes or runs something through an option of this call."""
    if prog == "sort":
        return bool(_opt_values(args, "o", ("--output",))) or any(
            a.startswith("--compress-program") for a in args) or any(
            re.match(r"-[A-Za-z]*o", a) and not a.startswith("--") for a in args)
    if prog == "yq":
        return any(a == "--inplace" or re.fullmatch(r"-[A-Za-z]*i[A-Za-z]*", a) for a in args)
    if prog in AWKS:
        return _awk_call(args)[0]
    if prog in FINDS:
        return bool(FIND_WRITES & set(args))
    if prog == "git":
        return any(a == "--output" or a.startswith("--output=") for a in args)
    if prog == "uniq":
        return len(_positionals(args)) >= 2
    if prog == "tree":
        return bool(_opt_values(args, "o", ()))
    if prog == "less":
        return bool(_opt_values(args, "o", ("--log-file",)) or _opt_values(args, "O", ("--LOG-FILE",)))
    if prog == "date":
        return any(a in ("-s", "--set") or a.startswith(("--set=", "-s")) for a in args)
    if prog == "hostname":
        return bool(_positionals(args)) or "-F" in args
    if prog == "file":
        return any(re.fullmatch(r"-[A-Za-z]*C[A-Za-z]*", a) for a in args)
    if prog in ("rg", "grep", "egrep", "fgrep"):
        return any(a.startswith(("--pre", "--hostname-bin")) for a in args)
    if prog in SEDS:
        writes, risky, _ = _sed_call(args)
        return writes or risky
    return False


SED_LONG = {"expression": "e", "file": "f", "in-place": "i", "line-length": "l", "quiet": "", "silent": "",
            "debug": "", "follow-symlinks": "", "posix": "", "regexp-extended": "", "separate": "", "sandbox": "",
            "unbuffered": "", "null-data": "", "zero-terminated": "", "binary": "", "help": "", "version": ""}


def _sed_reading(args: list[str], gnu: bool) -> tuple[list[str], bool, bool] | None:
    """How one sed reads its arguments: (scripts, a script file, in place), or None when it rejects an option. GNU
    sed takes options anywhere (and long ones, abbreviated too) and -i's suffix attached only; BSD sed stops at the
    first operand and takes the value of -i and -I from the next word when it is not attached."""
    flags, values = ("nrEsuzb", "efl") if gnu else ("EHalnru", "efiI")
    scripts: list[str] = []
    operands: list[str] = []
    from_file = inplace = False
    n = 0
    while n < len(args):
        a = args[n]
        if a == "--" or (not gnu and (a == "-" or not a.startswith("-"))):
            operands += args[n + (a == "--"):]
            break
        if a == "-" or not a.startswith("-"):
            operands.append(a)
        elif a.startswith("--"):
            name, eq, val = a[2:].partition("=")
            keys = [k for k in SED_LONG if k == name] or [k for k in SED_LONG if k.startswith(name)]
            if not gnu or len(keys) != 1:
                return None
            kind = SED_LONG[keys[0]]
            if kind in ("e", "f", "l") and not eq:
                if n + 1 >= len(args):
                    return None
                n, val = n + 1, args[n + 1]
            scripts += [val] if kind == "e" else []
            from_file, inplace = from_file or kind == "f", inplace or kind == "i"
        else:
            for j, ch in enumerate(a[1:], 1):
                if ch in flags:
                    continue
                if gnu and ch == "i":                   # the rest of the word is the backup suffix
                    inplace = True
                    break
                if ch not in values:
                    return None
                val = a[j + 1:]
                if not val:
                    if n + 1 >= len(args):
                        return None
                    n, val = n + 1, args[n + 1]
                scripts += [val] if ch == "e" else []
                from_file, inplace = from_file or ch == "f", inplace or ch in "iI"
                break
        n += 1
    if not scripts and not from_file and operands:
        scripts.append(operands[0])
    return scripts, from_file, inplace


def _sed_bracket_end(text: str, i: int) -> int | None:
    """The index after the bracket expression that opens at text[i] (a leading ] or ^] is a character, [:class:],
    [=c=] and [.c.] hold their own ]), or None when it does not close on this line."""
    j, n = i + 1, len(text)
    j += text.startswith("^", j)
    j += text.startswith("]", j)
    while j < n and text[j] not in "]\n":
        if text[j] == "[" and text[j + 1:j + 2] in (".", ":", "="):
            end = text.find(text[j + 1] + "]", j + 2)
            if end < 0:
                return None
            j = end + 2
        else:
            j += 1
    return j + 1 if j < n and text[j] == "]" else None


def _sed_script(text: str, brackets: bool) -> tuple[bool, bool] | None:
    """(writes, executes) of a sed script read one way, or None when that reading cannot parse it. brackets: a
    delimiter inside a bracket expression is a character (BSD, POSIX) rather than the end of the regex. Executes:
    GNU's e command or s///e flag; writes: the w/W command or the w flag (file names run to the end of the line)."""
    i, n, depth = 0, len(text), 0
    writes = executes = False

    def part(i: int, delim: str, regex: bool) -> int | None:      # the index after the delimiter that closes it
        while i < n:
            if text[i] == "\\":
                i += 2
            elif text[i] == "\n":
                return None
            elif text[i] == delim:
                return i + 1
            elif text[i] == "[" and regex and brackets:
                i = _sed_bracket_end(text, i)
                if i is None:
                    return None
            else:
                i += 1
        return None

    def address(i: int) -> int | None:                            # the index after an address (i when none)
        if i < n and text[i].isdigit():
            while i < n and (text[i].isdigit() or text[i] == "~"):
                i += 1
            return i
        if i < n and text[i] == "$":
            return i + 1
        if i < n and text[i] in "/\\":
            if text[i] == "\\" and (i + 1 >= n or text[i + 1] in "\n\\"):
                return None
            delim, i = ("/", i + 1) if text[i] == "/" else (text[i + 1], i + 2)
            i = part(i, delim, True)
            while i is not None and i < n and text[i] in "IM":
                i += 1
        return i

    def eol(i: int, continued: bool = False) -> int:              # the end of the line
        while i < n and text[i] != "\n":
            i += 2 if continued and text[i] == "\\" else 1
        return i

    while True:
        while i < n and text[i] in " \t\r\n;":
            i += 1
        if i >= n:
            break
        if text[i] == "#":
            i = eol(i)
            continue
        start = i
        i = address(i)
        if i is not None and i > start and i < n and text[i] == ",":
            i += 1
            while i < n and text[i] in " \t":
                i += 1
            first = i
            i = i + 1 if i < n and text[i] in "+~" else i
            i = address(i)
            if i is not None and i == first:
                return None
        if i is None:
            return None
        while i < n and text[i] in " \t":
            i += 1
        if i < n and text[i] == "!":
            i += 1
            while i < n and text[i] in " \t":
                i += 1
        if i >= n:
            return None                                 # an address without a command
        c, i = text[i], i + 1
        if c == "{":
            depth += 1
            continue
        if c == "}":
            depth -= 1
            if depth < 0:
                return None
        elif c in "lLqQ":
            while i < n and (text[i] in " \t" or text[i].isdigit()):
                i += 1
        elif c in ":btTv":                              # a label: up to ;, } or the end of the line
            while i < n and text[i] not in ";}\n":
                i += 1
        elif c in "aic":                                # text up to the end of the line; \ continues it
            i = eol(i, True)
            continue
        elif c in "rRwWe":                              # a file name or a command up to the end of the line
            end = eol(i)
            if c in "rRwW" and not text[i:end].strip():
                return None
            writes, executes, i = writes or c in "wW", executes or c == "e", end
            continue
        elif c in "sy":
            if i >= n or text[i] in "\n\\":
                return None
            delim = text[i]
            i = part(i + 1, delim, c == "s")
            i = None if i is None else part(i, delim, False)
            if i is None:
                return None
            while c == "s" and i < n and text[i] in "gpiImMe0123456789w":
                if text[i] == "w":
                    writes, i = True, eol(i + 1)
                    break
                executes, i = executes or text[i] == "e", i + 1
        elif c not in "=dDgGhHnNpPxzF":
            return None
        while i < n and text[i] in " \t\r":
            i += 1
        if i < n and text[i] not in ";\n}#":
            return None
    return None if depth else (writes, executes)


def _sed_call(args: list[str]) -> tuple[bool, bool, list[str]]:
    """(writes, risky, scripts) of a sed call over every way a sed may read it: GNU or BSD options; a delimiter in a
    bracket expression literal (BSD) or not (GNU may be either). risky: a reading executes something (GNU's e
    command or s///e flag) or takes its script from a file, or no reading parses at all. writes: in place, or the
    w/W command or flag. A reading that the sed itself would reject runs nothing."""
    writes = risky = valid = False
    scripts: list[str] = []
    for gnu in (True, False):
        reading = _sed_reading(args, gnu)
        if reading is None:
            continue
        texts, from_file, inplace = reading
        scripts += texts
        if from_file:
            risky = valid = True
            continue
        parses = [[r for r in (_sed_script(t, True), _sed_script(t, False) if gnu else None) if r] for t in texts]
        if all(parses):
            valid = True
            writes = writes or inplace or any(r[0] for p in parses for r in p)
            risky = risky or any(r[1] for p in parses for r in p)
    return writes, risky or not valid, scripts


def _write_args(prog: str, args: list[str]) -> list[str]:
    """Paths a write-capable command is given."""
    if prog == "sort":
        return _opt_values(args, "o", ("--output",))
    if prog == "yq" and _ro_writes(prog, args):
        return _positionals(args)[1:]
    if prog == "uniq" and _ro_writes(prog, args):
        return _positionals(args)[1:2]
    if prog == "tree":
        return _opt_values(args, "o", ())
    if prog == "less":
        return _opt_values(args, "o", ("--log-file",)) + _opt_values(args, "O", ("--LOG-FILE",))
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


# ------------------------------------------------------------------------------------- command runners (R22)
COMPLEX = ("shell:complex", HIGH)
FINDS = {"find", "gfind", "bfs"}
FIND_EXEC = {"-exec", "-execdir", "-ok", "-okdir"}
SEDS = {"sed", "gsed"}
RUNS = {"xargs", "parallel", "watch"} | FINDS            # programs whose arguments are a command
MAX_VARIANTS = 32                                        # beyond, what runs is not read: shell:complex
MAX_COMMAND = 64 * 1024                                  # a longer command is not lexed (quadratic cost): complex


def _top(results: list[tuple[str, str]]) -> tuple[str, str]:
    """The riskiest result; a fail-safe type wins a tie."""
    best = results[0]
    for r in results[1:]:
        if RANK[r[1]] > RANK[best[1]] or (RANK[r[1]] == RANK[best[1]] and r[0] in FLOORS and best[0] not in FLOORS):
            best = r
    return best


def _lit(result: tuple[str, str]) -> tuple[str, str]:
    """An inner command whose program is a variable is not a literal: shell:complex, which no override lowers."""
    return COMPLEX if result[0] == "shell:dynamic" else result


def _runner(own: tuple[str, str], inners: list[tuple[str, str]]) -> tuple[str, str]:
    """A program that runs commands takes the riskiest of them, and at least medium stakes. It is typed by that
    command when it reaches medium stakes, else by the runner itself (a chain takes its riskiest part)."""
    if not inners:
        return own
    top = _top(inners)
    if RANK[top[1]] >= RANK[MEDIUM]:
        return top
    return own[0], own[1] if RANK[own[1]] > RANK[MEDIUM] else MEDIUM


def _computed(word: str) -> bool:
    """A word the shell computes: a variable, a substitution, a glob, a brace expansion, `~user`."""
    return any(c in word for c in UNRESOLVED) or (word.startswith("~") and word != "~" and not word.startswith("~/"))


FOUND = "clr_found"                                     # a benign stand-in for the {} placeholder (a found path)


def _find_clauses(expr: list[str]) -> list[list[str]]:
    """The commands of a find expression's -exec/-execdir/-ok/-okdir clauses: the command and its arguments up to
    `;`, up to `{} +`, or up to the end of the expression."""
    out, n = [], 0
    while n < len(expr):
        if expr[n] in FIND_EXEC:
            j = n + 1
            while j < len(expr) and expr[j] != ";" and not (expr[j] == "+" and j > n + 1 and expr[j - 1] == "{}"):
                j += 1
            if j > n + 1:
                out.append(expr[n + 1:j])
            n = j
        n += 1
    return out


def _found_code(prog: str, args: list[str]) -> bool:
    """A found path ({}) would be read as code, not data: a shell's -c script, an interpreter's inline code, script
    or module, an awk program, a sed script, or anything given to a program that itself runs commands."""
    base = re.sub(r"\d+(\.\d+)*$", "", prog)
    if prog in SHELLS:
        i = next((n for n, a in enumerate(args) if re.fullmatch(r"-[A-Za-z]*c[A-Za-z]*", a)), None)
        texts = args if i is None else args[i + 1:i + 2]
    elif prog in INTERPRETERS or base in INTERPRETERS:
        inline = INLINE_FLAGS & set(args) or _inline_cluster(args)
        texts = args[args.index("-m") + 1:args.index("-m") + 2] if "-m" in args and not inline else args
    elif prog in AWKS:
        texts = _awk_call(args)[2]
    elif prog in SEDS:
        texts = _sed_call(args)[2]
    else:
        texts = args if prog in RUNS else []
    return any("{}" in t for t in texts)


def _find_inner(inner: list[str], cwd, home: str, depth: int) -> tuple[str, str] | None:
    """One command a find clause runs (None when there is none). The {} placeholder is a plain argument, a found
    path; but when it is spliced into a larger word, stands as the program, or lands where a found name would be
    read as code (a shell -c script, an interpreter's code, an awk program, a sed script, a nested runner), what
    runs is not a literal: shell:complex, which no override lowers."""
    toks = _unwrap(inner)
    if not toks:
        return None
    if (any("{}" in t and t != "{}" for t in inner) or "{}" in toks[0]
            or _found_code(os.path.basename(toks[0]), toks[1:])):
        return COMPLEX
    clause = [FOUND if t == "{}" else t for t in inner]
    r = _lit(_shell_segment(clause, cwd, home, depth + 1))
    return (f"shell:{os.path.basename(toks[0])}", r[1]) if FOUND in r[0] else r   # the stand-in is not a type


def _find(toks: list[str], cwd, home: str, depth: int, writes: bool) -> tuple[str, str]:
    """find runs a command per -exec/-execdir/-ok/-okdir clause, taking the riskiest. A segment that starts with an
    option or a comma is the rest of a find expression that an escaped `;` cut off."""
    prog, args = os.path.basename(toks[0]), toks[1:]
    if prog in FINDS:
        free = prog == "find" and not writes and not _ro_writes(prog, args)
        own, expr = (f"shell:{prog}", FREE if free else MEDIUM), args
    else:
        own, expr = ("shell:find", MEDIUM), toks
    inners = [r for inner in _find_clauses(expr) if (r := _find_inner(inner, cwd, home, depth)) is not None]
    return _runner(own, inners)


def _glue_find(segs: list[Seg]) -> list[Seg]:
    """An escaped `;` that ends a find clause reads as a separator: a segment after `;` that starts with an option
    or `,` is glued back to the find command before it, so that its clauses keep the starting points."""
    out: list[Seg] = []
    for s in segs:
        head = s.tokens[0] if s.tokens else ""
        prev = _unwrap(out[-1].tokens) if out else []
        if s.sep == ";" and (head.startswith("-") or head == ",") and prev and os.path.basename(prev[0]) in FINDS:
            out[-1] = Seg(out[-1].tokens + [";"] + s.tokens, out[-1].sub, out[-1].cond, out[-1].sep)
        else:
            out.append(s)
    return out


# GNU parallel's options known to be harmless: they neither run nor load anything, write nothing, reach no other
# host and change no replacement string. Any other option makes the call unreadable.
PARALLEL_FLAGS = {"0", "k", "v", "t", "q", "r", "u", "g", "m", "X", "null", "keep-order", "verbose", "quote",
                  "no-run-if-empty", "ungroup", "group", "xargs", "bar", "eta", "progress", "dry-run", "dryrun",
                  "line-buffer", "lb", "tag", "will-cite", "no-notice", "shuf", "xapply", "link", "noswap"}
PARALLEL_VALUES = {"j", "P", "n", "N", "L", "s", "d", "C", "E", "a", "jobs", "max-procs", "max-args", "max-lines",
                   "max-chars", "delimiter", "colsep", "halt", "timeout", "delay", "retries", "nice", "memfree",
                   "load", "block", "block-size", "tagstring", "header", "trim", "arg-file"}
PARALLEL_SEPS = {":::", ":::+", "::::", "::::+"}
PARALLEL_RS = re.compile(r"\{(\d*)(\.|//|/\.|/|#|%)?\}")     # {} {.} {/} {//} {/.} {#} {%}, {n} and {n.}...
WATCH_FLAGS = set("dtbegcCxpwr") | {"differences", "no-title", "beep", "errexit", "chgexit", "color", "no-color",
                                    "exec", "precise", "no-wrap", "no-rerun"}
WATCH_VALUES = {"n", "q", "interval", "equexit"}


def _options(args: list[str], flags: set[str], values: set[str]) -> tuple[int, list[str]] | None:
    """Where the operands of a call start, and the names of the options given (short ones by letter); None for an
    option outside `flags` and `values` (options that take a value)."""
    n, names = 0, []
    while n < len(args) and args[n].startswith("-") and args[n] not in PARALLEL_SEPS:
        a = args[n]
        if a == "--":
            return n + 1, names
        if a.startswith("--"):
            name = a[2:].split("=", 1)[0]
            if name not in flags | values:
                return None
            n += name in values and "=" not in a
            names.append(name)
        else:
            for j, ch in enumerate(a[1:], 1):
                if ch not in flags | values:
                    return None
                names.append(ch)
                if ch in values:
                    n += j + 1 == len(a)                 # the value is the next word unless attached
                    break
        n += 1
    return n, names


def _parallel_value(m: re.Match, combo: tuple[str, ...]) -> str:
    pos, op = m.group(1), m.group(2) or ""
    if op in ("#", "%"):
        return "1"                                       # the job or slot number
    if pos and not 0 < int(pos) <= len(combo):
        return m.group(0)
    out = []
    for v in [combo[int(pos) - 1]] if pos else combo:
        if op in ("/", "/."):
            v = v.rsplit("/", 1)[-1]                     # the base name
        elif op == "//":
            v = v.rsplit("/", 1)[0] if "/" in v else "."  # the directory
        if op in (".", "/."):
            v = re.sub(r"\.[^./]*$", "", v)              # without the extension
        out.append(v)
    return " ".join(out)


def _parallel(args: list[str], cwd, home: str, depth: int) -> tuple[str, str]:
    """GNU parallel runs its command through a shell once per combination of the ::: arguments, put in place of
    {}, {1}, {.}... or appended; without a command, the arguments are the commands. Arguments read from a file or
    stdin, a computed argument, a perl replacement string, or an option outside the harmless ones (other hosts,
    profiles, custom replacement strings, filters...) make what runs unreadable."""
    opts = _options(args, PARALLEL_FLAGS, PARALLEL_VALUES)
    if opts is None:
        return COMPLEX
    n, names = opts
    rest = args[n:]
    k = next((i for i, a in enumerate(rest) if a in PARALLEL_SEPS), len(rest))
    cmd, groups = rest[:k], []
    for a in rest[k:]:
        if a in PARALLEL_SEPS:
            groups.append((a, []))
        else:
            groups[-1][1].append(a)
    if (not groups or {"a", "arg-file"} & set(names) or any(s.startswith("::::") for s, _ in groups)
            or any(_computed(a) for _, g in groups for a in g) or "{=" in " ".join(cmd)):
        return COMPLEX
    if not cmd:
        if len(groups) > 1:
            return COMPLEX                               # the arguments of each group are joined into commands
        inners = [_lit(_shell(t, cwd, home, depth + 1)[:2]) for t in dict.fromkeys(groups[0][1])]
        return _runner(("shell:parallel", MEDIUM), inners)
    combos = list(itertools.islice(itertools.product(*(g for _, g in groups)), MAX_VARIANTS + 1))
    if len(combos) > MAX_VARIANTS:
        return COMPLEX
    rs = any(PARALLEL_RS.search(t) for t in cmd)
    inners = []
    for c in combos:
        # token by token, so a quoted argument (sh -c 'git push') keeps its quoting
        toks = ([PARALLEL_RS.sub(lambda m, c=c: _parallel_value(m, c), t) for t in cmd] if rs else [*cmd, *c])
        inners.append(_lit(_shell_segment(toks, cwd, home, depth + 1)))
        if any(re.search(r"[\s;&|<>()$`'\"\\*?]", t) for t in toks):   # the shell also reads the joined line
            inners.append(_lit(_shell(" ".join(toks), cwd, home, depth + 1)[:2]))
    return _runner(("shell:parallel", MEDIUM), inners)


def _watch(args: list[str], cwd, home: str, depth: int) -> tuple[str, str]:
    """watch runs its command through `sh -c`, the arguments joined by spaces (or directly with -x)."""
    opts = _options(args, WATCH_FLAGS, WATCH_VALUES)
    if opts is None:
        return COMPLEX
    rest = args[opts[0]:]
    if not rest:
        return "shell:watch", MEDIUM
    inners = [_shell(" ".join(rest), cwd, home, depth + 1)[:2], _shell_segment(rest, cwd, home, depth + 1)]
    return _runner(("shell:watch", MEDIUM), [_lit(r) for r in inners])


UNRESOLVED = "$`?*[{"


def _shell_segment(tokens: list[str], cwd, home, depth: int = 0) -> tuple[str, str]:
    """One command. A sensitive path it writes (redirect or argument) caps it; a write target that cannot be
    resolved (variable, glob, brace, or a relative path while the working directory is unknown) is file:unknown."""
    unresolved = False
    base = "/" if cwd == UNKNOWN else cwd
    targets = _redirects(tokens)
    toks = _unwrap(tokens)
    if toks:
        targets += _write_args(os.path.basename(toks[0]), toks[1:])
    for target in targets:
        target = _expand(target, home)
        if any(c in target for c in UNRESOLVED) or (cwd == UNKNOWN and not os.path.isabs(target)):
            unresolved = True
        elif _file(target, base, home)[1] == CAP:
            return "file:sensitive", CAP
    if unresolved:
        return "file:unknown", HIGH
    return _core(tokens, cwd, home, depth)


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
        i = next((n for n, a in enumerate(args) if re.fullmatch(r"-[A-Za-z]*c[A-Za-z]*", a)), None)
        if i is not None:
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
        if INLINE_FLAGS & set(args) or _inline_cluster(args):
            return f"shell:{prog}:inline", HIGH
        if "-m" in args:
            i = args.index("-m")
            mod = args[i + 1] if i + 1 < len(args) else ""
            return f"shell:{prog}:-m:{mod}", MEDIUM
        script = next((a for a in args if not a.startswith("-")), "")
        return (f"shell:{prog}:{os.path.basename(script)}" if script else f"shell:{prog}"), MEDIUM
    if prog in AWKS:
        w, cmds, _ = _awk_call(args)
        if cmds is None:
            return COMPLEX
        own = (f"shell:{prog}", FREE if prog in READ_ONLY and not writes and not w else MEDIUM)
        return _runner(own, [_lit(_shell(c, cwd, home, depth + 1)[:2]) for c in dict.fromkeys(cmds)])
    if prog in SEDS:
        w, risky, _ = _sed_call(args)
        if risky:
            return COMPLEX                               # GNU sed runs the pattern space as a command
        return f"shell:{prog}", FREE if prog == "sed" and not writes and not w else MEDIUM
    if prog in FINDS or prog.startswith("-") or prog == ",":
        return _find(toks, cwd, home, depth, writes)
    if prog == "parallel":
        return _parallel(args, cwd, home, depth)
    if prog == "watch":
        return _watch(args, cwd, home, depth)
    plain = _strip(args, SUB_VALUE_OPTS)
    sub = plain[0] if plain else ""
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
        if not writes and not _ro_writes("git", args) and (sub in GIT_READ or (sub in ("branch", "tag", "remote") and len(args) <= 2
                                                and not any(a in ("-d", "-D", "--delete", "add", "remove", "rm",
                                                                  "set-url", "rename") for a in args))):
            return f"shell:git:{sub}", FREE
        return f"shell:git:{sub or 'unknown'}", MEDIUM
    if prog in READ_ONLY and not writes and not _ro_writes(prog, args):
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
        if (first or RANK[top[1]] > RANK[best[1]]
                or (RANK[top[1]] == RANK[best[1]] and top[0] in FLOORS and best[0] not in FLOORS)):
            best, first = top, False
        cd = _cd_kind(seg.tokens)
        if cd:
            moved = [_move(st, cd[0], cd[1], home) for st in states]
            states = list(dict.fromkeys(states + moved if seg.sub or seg.cond else moved))
            if len(states) > 32:
                states = [(UNKNOWN, None)]
    return best


# ------------------------------------------------------------------------------------- fail-safe floors (R16)
KEYWORDS = {"if", "then", "elif", "else", "fi", "case", "esac", "for", "while", "until", "do", "done", "select",
            "function", "!"}
HEREDOC = re.compile(r"<<(-?)\s*([\"']?)([A-Za-z_][A-Za-z0-9_]*)\2")


def _strip_heredocs(command: str) -> str:
    """The command without the bodies of simple heredocs (their text is data, not grammar)."""
    out, pending = [], []
    for line in command.split("\n"):
        if pending:
            strip, delim = pending[0]
            if (line.lstrip("\t") if strip else line).rstrip("\r") == delim:
                pending.pop(0)
            continue
        out.append(line)
        pending += [(m.group(1) == "-", m.group(3)) for m in HEREDOC.finditer(line.replace("<<<", "   "))]
    return "\n".join(out)


def _frag(word: str) -> bool:
    for cand in {word, word.split("=", 1)[-1], word.lstrip("@")}:
        low = cand.lower().replace("\\", "/")
        if (any(f in low for f in SENSITIVE_FRAGMENTS) or any(d.lower() in "/" + low + "/" for d in SENSITIVE_DIRS)
                or low.startswith(tuple(x.lower() for x in SENSITIVE_PREFIXES))
                or SENSITIVE_NAME.match(low.rstrip("/").rsplit("/", 1)[-1])):
            return True
    return False


def _sensitive_floor(command: str) -> bool:
    """A write target, or any argument of a command that is not purely read-only, names a sensitive file."""
    for tokens in (_tokens_lines(command), _tokens_whole(command)):
        pure, words = True, []
        for seg in _build(tokens):
            toks = _unwrap(seg.tokens)
            prog = os.path.basename(toks[0]) if toks else ""
            if (prog not in READ_ONLY or _redirects(seg.tokens) or "<(" in seg.tokens or ">(" in seg.tokens
                    or _ro_writes(prog, toks[1:])):
                pure = False
            ws = list(seg.tokens)
            if toks and toks[0] in ws:
                ws.remove(toks[0])
            words += ws
        if not pure and any(_frag(w) for w in words):
            return True
    return False


def _seg_complex(tokens: list[str]) -> bool:
    raw = _unwrap(tokens, wrappers=False)
    if raw and (raw[0] in KEYWORDS or (raw[0] == "exec" and len(raw) > 1)):
        return True
    for n in range(len(tokens) - 2):                         # name() { ...; }
        if tokens[n + 1] == "(" and tokens[n + 2] == ")" and tokens[n] not in ("$", "(", ")"):
            return True
    toks = _strip_wrappers(list(raw))
    if not toks:
        return False
    prog, args = os.path.basename(toks[0]), toks[1:]
    if prog in ("eval", "source", "."):
        return True
    if prog in SHELLS:
        return any(re.fullmatch(r"-[A-Za-z]{2,}", a) and "c" in a for a in args)
    base = re.sub(r"\d+(\.\d+)*$", "", prog)
    return (prog in INTERPRETERS or base in INTERPRETERS) and _inline_cluster(args)


def _complex_floor(command: str) -> bool:
    """Constructs outside the supported grammar: control flow, functions, ANSI-C quoting, unbalanced quotes or
    parentheses, process substitution, here-strings, eval/source/exec, shell or interpreter flag clusters."""
    text = _strip_heredocs(command)
    if "$'" in text:
        return True
    try:
        tokens = _decompose(_lex(text))
    except ValueError:
        return True
    if any(t in ("<<<", "<(", ">(") for t in tokens):
        return True
    depth = 0
    for t in tokens:
        depth += 1 if t == "(" else -1 if t == ")" else 0
        if depth < 0:
            return True
    return depth != 0 or any(_seg_complex(seg.tokens) for seg in _build(tokens))


def _shell(command: str, cwd=None, home=None, depth: int = 0) -> tuple[str, str, bool]:
    """The precise reading (typed twice, the riskier wins: by lines, then the whole command tokenised) may lower
    stakes only for commands it fully understands. Two floors are checked independently of it: a sensitive name
    (cap) and constructs outside the grammar (shell:complex, high). A command over MAX_COMMAND is not read at all."""
    if len(command or "") > MAX_COMMAND:
        return "shell:complex", HIGH, False
    home = _norm(home or os.path.expanduser("~"))
    command = _join_lines(command)
    start = cwd or os.getcwd()
    by_lines = _run(_glue_find(_build(_tokens_lines(command))), start, home, depth)
    whole = _run(_glue_find(_build(_tokens_whole(command))), start, home, depth)
    best = whole if RANK[whole[1]] >= RANK[by_lines[1]] else by_lines
    if best[1] == CAP:
        return best[0], best[1], False
    if _sensitive_floor(command):
        return "file:sensitive", CAP, False
    if _complex_floor(command):
        low = command.lower()          # quotes cannot be trusted here: look at the raw text
        if any(f in low for f in SENSITIVE_FRAGMENTS) or any(d.lower() in low for d in SENSITIVE_DIRS):
            return "file:sensitive", CAP, False
        return "shell:complex", HIGH, False
    return best[0], best[1], False                  # a command is never reversible by Clearance


def _seg_reads_external(tokens: list[str], depth: int) -> bool:
    if depth > MAX_DEPTH:
        return False
    for n, t in enumerate(tokens):                      # <(curl x), $(curl x), "$(curl x)", `curl x`
        if t in ("<(", ">(", "(") and n + 1 < len(tokens) and os.path.basename(tokens[n + 1]) in ("curl", "wget"):
            return True
        for inner in re.findall(r"\$\(([^()]*)\)", t):
            if _cmd_reads_external(inner, depth + 1):
                return True
    for inner in re.findall(r"`([^`]*)`", " ".join(tokens)):
        if _cmd_reads_external(inner, depth + 1):
            return True
    toks = _unwrap(tokens)
    if not toks:
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
            return _gh_api_reads(args)
        return len(plain) > 1 and plain[0] in ("issue", "pr") and plain[1] == "view"
    return False


def _gh_api_reads(args: list[str]) -> bool:
    method, fields, endpoint = "", False, ""
    skip = False
    for n, a in enumerate(args):
        if skip:
            skip = False
            continue
        if a in ("-X", "--method"):
            method, skip = args[n + 1].upper() if n + 1 < len(args) else "?", True
        elif a.startswith("--method="):
            method = a.split("=", 1)[1].upper()
        elif a.startswith("-X") and len(a) > 2:
            method = a[2:].upper()
        elif a in ("-f", "-F", "--field", "--raw-field", "--input"):
            fields, skip = True, True                       # these take a value
        elif a.startswith(("--field=", "--raw-field=", "--input=", "-f", "-F")):
            fields = True
        elif not a.startswith("-") and a != "api" and not endpoint:
            endpoint = a
    if method and method != "GET":
        return False
    return not fields or method == "GET" or endpoint == "graphql"


def _cmd_reads_external(command: str, depth: int) -> bool:
    command = _join_lines(command)
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
FLOORS = {"file:unknown", "shell:complex", "file:unreadable", "shell:nested"}   # fail-safe: an override only raises


def _override(t: str, stakes: str, overrides: dict | None) -> str:
    if not overrides or (stakes == CAP and t.startswith(PROTECTED)):
        return stakes
    new = stakes
    if t in overrides:
        new = _valid(overrides[t], stakes)
    else:
        for pat, val in overrides.items():
            if fnmatch.fnmatchcase(t, pat):
                new = _valid(val, stakes)
                break
    return stakes if t in FLOORS and RANK[new] < RANK[stakes] else new   # a floor can be raised, never lowered


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
    _CACHE.memo = {}
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
