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
    "setup_beat", "gui_tour", "desktop_preview", "drive_preview", "manage_connections",
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


def _file(path: str, cwd: str | None, home: str) -> tuple[str, str, bool]:
    p = os.path.expanduser(path) if path.startswith("~") else path
    base = cwd or os.getcwd()
    full = os.path.normpath(p if os.path.isabs(p) else os.path.join(base, p))
    probe = full.replace("\\", "/")
    if (any(d in probe + "/" for d in SENSITIVE_DIRS) or probe.startswith(SENSITIVE_PREFIXES)
            or SENSITIVE_NAME.match(os.path.basename(probe))):
        return "file:sensitive", CAP, False
    root = os.path.normpath(base).replace("\\", "/").rstrip("/") + "/"
    if (probe + "/").startswith(root):
        return "file:write", LOW, True
    return "file:write-outside", MEDIUM, True


# ---------------------------------------------------------------------------------------------------------- shell
READ_ONLY = {"ls", "cat", "head", "tail", "less", "more", "grep", "rg", "egrep", "fgrep", "wc", "pwd", "echo",
             "printf", "which", "whereis", "whoami", "id", "date", "uname", "printenv", "tree", "du", "df", "stat",
             "file", "sort", "uniq", "cut", "tr", "jq", "yq", "diff", "cmp", "basename", "dirname", "realpath",
             "readlink", "hostname", "uptime", "ps", "true", "false", "test", "[", "awk", "column", "nl", "md5sum",
             "shasum", "sha256sum", "type"}
GIT_READ = {"status", "log", "diff", "show", "rev-parse", "describe", "blame", "ls-files", "grep", "shortlog", "reflog",
            "fetch"}
GH_READ = {"view", "list", "status", "diff", "checks"}
WRAPPERS = {"sudo", "env", "nohup", "time", "nice", "command", "exec", "stdbuf", "doas"}
OUTSIDE = {"scp": "shell:scp", "sftp": "shell:sftp", "ssh": "shell:ssh", "ftp": "shell:ftp", "mail": "shell:mail",
           "sendmail": "shell:mail", "mutt": "shell:mail", "nc": "shell:nc", "ncat": "shell:nc", "telnet": "shell:nc"}
PUBLISH = {("npm", "publish"), ("pnpm", "publish"), ("yarn", "publish"), ("twine", "upload"), ("cargo", "publish"),
           ("gem", "push"), ("docker", "push"), ("podman", "push"), ("docker", "login"), ("git", "push")}
CLOUD = {"aws", "gcloud", "az"}
CLOUD_WRITE = {"create", "delete", "put", "update", "deploy", "rm", "cp", "mv", "sync", "mb", "rb", "set", "add",
               "remove", "attach", "detach", "start", "stop", "terminate", "run", "invoke", "publish", "send"}
KUBE_WRITE = {"apply", "delete", "create", "replace", "patch", "scale", "rollout", "edit", "drain", "cordon", "exec"}
SEPARATORS = {";", "&&", "||", "|", "&", "\n"}


def _segments(command: str) -> list[list[str]]:
    try:
        lex = shlex.shlex(command, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        tokens = list(lex)
    except ValueError:
        tokens = command.split()
    segs, cur = [], []
    for t in tokens:
        if t in SEPARATORS:
            if cur:
                segs.append(cur)
            cur = []
        else:
            cur.append(t)
    if cur:
        segs.append(cur)
    return segs


def _shell_segment(tokens: list[str]) -> tuple[str, str]:
    writes = any(t in (">", ">>", ">|", "&>") or t.startswith((">", "1>", "2>")) for t in tokens)
    toks = [t for t in tokens if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", t)]
    while toks and os.path.basename(toks[0]) in WRAPPERS:
        toks = toks[1:]
        while toks and toks[0].startswith("-"):
            toks = toks[1:]
    if not toks:
        return "shell:unknown", MEDIUM
    prog = os.path.basename(toks[0])
    args = toks[1:]
    sub = next((a for a in args if not a.startswith("-")), "")
    if prog in OUTSIDE:
        return OUTSIDE[prog], HIGH
    if (prog, sub) in PUBLISH:
        return f"shell:{prog}:{sub}", HIGH
    if prog in ("curl", "wget"):
        joined = " ".join(args)
        sends = (re.search(r"(^|\s)(-d|--data\S*|-F|--form|-T|--upload-file|--post-data|--post-file)(\s|=|$)", joined)
                 or re.search(r"(-X|--request|--method)[\s=]*(POST|PUT|PATCH|DELETE)", joined, re.I))
        if sends:
            return f"shell:{prog}:send", HIGH
        return f"shell:{prog}", MEDIUM if writes or "-o" in args or "-O" in args else FREE
    if prog == "rsync":
        return "shell:rsync", HIGH if any(re.match(r"^[^/]*:", a) for a in args if not a.startswith("-")) else MEDIUM
    if prog == "gh":
        if sub in ("pr", "issue", "repo", "release", "run", "workflow"):
            verb = next((a for a in args[args.index(sub) + 1:] if not a.startswith("-")), "")
            if verb in GH_READ:
                return f"shell:gh:{sub}", FREE
        if sub == "api" and not re.search(r"(-X|--method)\s*(POST|PUT|PATCH|DELETE)|-f\s|-F\s|--field|--input", " ".join(args)):
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


def _shell(command: str) -> tuple[str, str, bool]:
    best = ("shell:unknown", MEDIUM)
    first = True
    for seg in _segments(command or ""):
        t, s = _shell_segment(seg)
        if first or RANK[s] > RANK[best[1]]:
            best, first = (t, s), False
    return best[0], best[1], best[1] in (FREE, LOW, MEDIUM)


# ------------------------------------------------------------------------------------------------------------ MCP
MCP = re.compile(r"^mcp_([A-Za-z0-9-]+)_(.+)$")
HIGH_VERBS = {"send", "post", "publish", "email", "mail", "sms", "tweet", "message", "notify", "invite", "share", "pay",
              "payment", "payments", "purchase", "buy", "charge", "transfer", "refund", "order", "checkout", "invoice",
              "payout", "withdraw", "deposit", "broadcast", "reply", "comment", "dm"}
MEDIUM_VERBS = {"create", "update", "add", "set", "put", "patch", "edit", "modify", "upsert", "insert", "save", "write",
                "delete", "remove", "archive", "move", "rename", "upload", "assign", "close", "complete", "merge",
                "approve", "schedule", "cancel", "enable", "disable", "tag", "label", "mark", "append", "clear"}
FREE_VERBS = {"get", "list", "search", "read", "fetch", "find", "query", "lookup", "describe", "show", "view", "count",
              "check", "status", "retrieve", "download", "export", "info", "inspect", "preview", "summarize"}


def _words(name: str) -> set[str]:
    return {w.lower() for w in re.split(r"[_\-.\s]+|(?<=[a-z])(?=[A-Z])", name) if w}


def _mcp(server: str, tool: str) -> tuple[str, str, bool]:
    w = _words(tool)
    stakes = HIGH if w & HIGH_VERBS else MEDIUM if w & MEDIUM_VERBS else FREE if w & FREE_VERBS else HIGH
    return f"mcp:{server}:{tool}", stakes, stakes != HIGH


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
        t, stakes, rev = f"read:{tool_name}", FREE, True
    elif tool_name in ("write_file", "patch"):
        t, stakes, rev = _file(str(args.get("path") or args.get("file_path") or ""), cwd, home)
    elif tool_name == "terminal":
        t, stakes, rev = _shell(str(args.get("command", "")))
    elif tool_name in TOOLS:
        t, stakes, rev = TOOLS[tool_name]
    elif tool_name.startswith("kanban_"):
        t, stakes, rev = f"kanban:{tool_name[len('kanban_'):]}", LOW, True
    elif MCP.match(tool_name):
        m = MCP.match(tool_name)
        t, stakes, rev = _mcp(m.group(1), m.group(2))
    else:
        t, stakes, rev = f"tool:{tool_name}", HIGH, False
    stakes = _override(t, stakes, overrides)
    return Action(type=t, stakes=stakes, reversible=rev, summary=_summary(tool_name, args, t))
