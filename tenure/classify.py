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
import functools
import itertools
import os
import re
import shlex
import stat as _stat
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
    "message_agent": ("bot:message", MEDIUM, False),     # Bot Mode: to another of the owner's Bots, inside the install
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
                  "/.netrc", "/.git-credentials", "/.npmrc", "/.pypirc")   # Hermes homes: _self_hit, by entry
SENSITIVE_PREFIXES = ("/etc/", "/usr/", "/bin/", "/sbin/", "/System/", "/Library/", "/private/etc/")
SENSITIVE_NAME = re.compile(r"^(\.env(\..*)?|id_[a-z0-9]+|.*\.pem|.*\.key|credentials(\.json)?|secrets?\.(ya?ml|json))$",
                            re.I)


UNKNOWN = "\0unknown-cwd"                         # a virtual cwd that could not be worked out


def _norm(p: str) -> str:
    return p.replace("\\", "/")


def _expand(path: str, home: str) -> str:
    """`~`, `$HOME` and `${HOME}` at the start of a path; `$HERMES_HOME` and `${HERMES_HOME}` too (Hermes' home)."""
    for pre in ("${HOME}", "$HOME"):
        if path == pre or path.startswith(pre + "/"):
            return home + path[len(pre):]
    for pre in ("${HERMES_HOME}", "$HERMES_HOME"):
        if path == pre or path.startswith(pre + "/"):
            return _norm(_hermes_home_value(home)).rstrip("/") + path[len(pre):]
    if path == "~" or path.startswith("~/") or path.startswith("~\\"):
        return home + path[1:]
    return path


_CACHE = threading.local()                       # symlink resolutions, valid for one classify() call


def _abs(path: str, cwd: str | None, home: str | None = None, physical: bool = True) -> str:
    """The absolute path a program reaches. The system resolves the links of each component before it applies a
    `..` (`ws/../config.yaml`, where ws is a link, is the file next to the link's target, not next to the link), so
    a path that holds `..` is walked that way (``_physical``). The spelling normalised without looking at the disk,
    which a program that normalises by itself reaches, is kept beside it (``_lexical``) and judged too."""
    p = _expand(path, home or os.path.expanduser("~"))
    joined = p if os.path.isabs(p) else os.path.join(cwd or os.getcwd(), p)
    lexical = _norm(os.path.normpath(joined))
    if not physical or ".." not in joined:
        return lexical
    full = _physical(joined, lexical)
    memo = getattr(_CACHE, "memo", None)
    if memo is not None and full != lexical:
        memo[("lexical", full)] = lexical
    return full


def _physical(joined: str, lexical: str) -> str:
    """``joined`` (absolute, not normalised) with each `..` applied to the resolved folder before it, when that
    folder is reached through a link; ``lexical`` when no link changes where a `..` leads."""
    if not joined.startswith("/") or "\0" in joined:
        return lexical
    cur, changed = "/", False
    for comp in joined.split("/"):
        if comp in ("", "."):
            continue
        if comp != "..":
            cur = cur.rstrip("/") + "/" + comp
            continue
        parent = os.path.dirname(cur) or "/"
        if cur != "/":
            real = _resolved(cur)
            if real != cur:
                up = os.path.dirname(real.rstrip("/")) or "/"
                if up != _resolved(parent):                 # the link leads elsewhere: `..` is its target's parent
                    parent, changed = up, True
        cur = parent
    return _norm(cur) if changed else lexical


def _lexical(full: str) -> str:
    """The spelling of ``full`` normalised without resolving links, when ``_abs`` found another one."""
    memo = getattr(_CACHE, "memo", None)
    return memo.get(("lexical", full), full) if memo is not None else full


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


SENSITIVE_FRAGMENTS = ("authorized_keys", "known_hosts", "id_ed25519", "id_ecdsa", ".netrc")

# ------------------------------------------------------------------------------------ the agent's own guardrails
# tenure's own data: the database, its data folder (undo snapshots), the passport signing key. Whatever names
# them, wherever the Hermes home is, is self:tenure (capped; no override lowers it).
TENURE_NAMES = re.compile(r"tenure\.db|plugin-data/tenure(?![\w.-])|passport-ed25519\.pem"
                             r"|api/plugins/tenure(?![\w.-])")      # the dashboard's settings, revoke and undo API
# What Hermes keeps at the top of each home level (a home, a root, and each profiles/<name> under them). Only these are
# protected: a project or a workspace under a home (kanban/workspaces/..., workspace/, home/) is ordinary.
HERMES_ENTRIES = frozenset({
    "config.yaml", ".env", "auth.json", "auth.lock", "soul.md", "profile.yaml", "plugins", "plugin-data", "skills",
    "optional-skills", "hooks", "cron", "memories", "sessions", "logs", "plans", "skins", "pairing", "platforms",
    "bin", "mcp", "secrets", "vault", "backups", "state-snapshots", ".deleted", "gateway.sock", "gateway.pid",
    "gateway.lock", "hermes-agent",
    # Read in Hermes' source (v0.23) and changing what it does. Each name: where it is read, and why it counts.
    # -- which Hermes runs, and how it starts
    "active_profile",            # hermes_cli/profiles.py: the profile every later start uses
    ".container-mode",           # hermes_cli/config.py: `hermes` re-executes in the container this file names
    ".install_method",           # hermes_cli/config.py: how `hermes update` installs
    "gateway.json",              # gateway/config_loader.py: the gateway's base configuration
    "gateway_state.json",        # hermes_cli/container_boot.py: desired_state starts the gateway at boot, argv restarts it
    "processes.json",            # tools/process_registry_checkpoint.py: adopts the listed PIDs, stops the listed units
    "relay-plugins.toml",        # agent/relay_runtime.py: where trajectories and telemetry are sent
    # -- code Hermes runs from its home
    "scripts",                   # tools/cronjob_job_args.py: cron jobs run scripts/<file>
    "checkpoints",               # tools/checkpoint_manager.py: a git store whose own config and hooks git reads
    "mcp-installs",              # hermes_cli/mcp_catalog.py: cloned MCP servers, started as commands
    "desktop-plugins",           # hermes_cli/desktop_plugin_install.py: plugin.js loaded by the desktop app
    "tools", "installs", "environments",   # pm/: downloaded tools, interpreters and virtual environments it executes
    "runtimes",                  # hermes_cli/local_runtime: binaries and server arguments of the local model server
    "node", "node_modules",      # hermes_cli/gateway.py: their bin folders are on the gateway service's PATH
    "lib",                       # hermes_state_fts.py: a native SQLite extension loaded from here
    "lsp",                       # agent/lsp: language servers spawned from lsp/bin and lsp/node_modules
    "gateway-service",           # hermes_cli/gateway_windows.py: the wrapper a scheduled task runs at logon
    ".hermes-runtime",           # the managed runtime tree
    "photon",                    # plugins/platforms/photon: a Node sidecar run from here
    "npmrc",                     # hermes_cli/source_build.py: npm's user configuration for source builds
    # -- what is put in the prompt, replayed as the user's words, or waits for an approval
    "agents.md", "hermes.md", ".hermes.md", "claude.md", ".cursorrules", ".cursor",   # agent/prompt_builder.py: project
    #                              context loaded when the session runs in the home (the gateway service's default)
    "prefill.json",              # hermes_cli/cli_config_load.py: messages injected into every prompt
    "skill-bundles",             # agent/skill_bundles.py: slash commands and their instructions
    ".skills_prompt_snapshot.json",   # agent/prompt_builder.py: the cached skills index of the system prompt
    "pending",                   # tools/write_approval.py: memory and skill writes waiting for the user's approval
    "pending_messages",          # gateway/shutdown_flush.py: replayed into session transcripts at start-up
    "tui-pending-inputs",        # ui-tui pendingInputs.ts: resubmitted as user messages on resume
    ".update_response",          # hermes_cli/update_cmd.py: the answer to an interactive `hermes update` prompt
    "response_store.db",         # gateway/platforms/api_server_response_store.py: history replayed like state.db
    "byterover",                 # plugins/memory/byterover: a memory store recalled into the prompt
    "dashboard-themes",          # hermes_cli/web_server_dashboard.py: CSS injected as is into the dashboard
    # -- who Hermes talks to, and who may talk to it
    "kanban.db",                 # hermes_cli/kanban_db_dispatch.py: the dispatcher starts worker agents from its rows
    "webhook_subscriptions.json",   # hermes_cli/webhook.py: routes, their prompt, their secret
    "channel_directory.json", "channel_aliases.json",   # gateway/channel_directory.py: where send_message delivers
    "feishu_comment_rules.json", "feishu_comment_pairing.json",   # the Feishu access policy and approved pairings
    # -- credentials
    "auth", "honcho.json", ".op.env", ".anthropic_oauth.json", "google_token.json", "google_client_secret.json",
    "slack_tokens.json", "mcp-tokens", "google_chat_user_tokens", "shared", "browser-profile", "proxy", "desktop-ssh",
    "bot-desktop", "mem0.json", ".copilot_jwt.json", "bws_cache.json", "bws_cache.enc.json", "op_cache.json",
    "photon-sidecar.json"})
# Left ordinary on purpose, after reading the same source: they are output, display or regenerable caches that do
# not decide what Hermes does (cache/ as a whole: cache/documents is the documented output mount; runtime/, state/,
# telemetry/, images/, pastes/, sandboxes/, locks/, projects.db, provider_models_cache.json,
# context_length_cache.yaml, gateway_voice_mode.json, the .update_* and .restart_notify.json notices), and the
# folders the agent works in (workspace/, home/, kanban/workspaces/).
# Below a folder that is otherwise ordinary, the paths that do decide something:
HERMES_SUBENTRIES = (
    "kanban/boards",                 # hermes_cli/kanban_db.py: each board's kanban.db, read like the main one
    "kanban/current",                # the board the dispatcher works on
    "cache/project_skill_scans",     # tools/skills_guard: a forged verdict skips the quarantine of a project skill
    "cache/plugin-catalog.json",     # hermes_cli/plugin_catalog.py: decides what `plugins install <name>` fetches
    "cache/plugin_host")             # cached plugin provider profiles
HERMES_ENTRY_PREFIXES = ("state.db", "config.yaml", ".env", "auth.", "soul.md", "kanban.db")
PATH_START = " \t'\"`=(:,;[{<>"                             # what may come just before a path in text
PATH_END = re.compile(r"[\s'\"`;,)\]}<>|&]")
# Hermes homes named in text without being resolved: any `.hermes` folder, Windows' AppData/Local/hermes, and the
# $HERMES_HOME variable (a path segment, never a file name such as test_hermes_home.py).
HOME_MARKERS = re.compile(r"(?:^|(?<=[/\s'\"`=(:,;\[{<>]))"
                          r"(?:\.hermes|appdata/local/hermes|\$hermes_home|\$\{hermes_home\})"
                          r"(?=$|/|[\s'\"`;,)\]}<>|&])")
_NO_HERMES = []                                          # set once hermes_constants is known not to import


def _hermes_constants():
    import sys
    mod = sys.modules.get("hermes_constants")
    if mod is not None or _NO_HERMES:
        return mod
    try:
        import hermes_constants as mod                   # public Hermes import
        return mod
    except Exception:
        _NO_HERMES.append(True)
        return None


def _hermes_home_value(home: str) -> str:
    """What `$HERMES_HOME` holds in the terminal: Hermes' resolved home, else the variable, else ~/.hermes."""
    hc = _hermes_constants()
    fn = getattr(hc, "get_hermes_home", None) if hc is not None else None
    if callable(fn):
        try:
            return str(fn())
        except Exception:
            pass
    env = getattr(os, "environ", {}).get("HERMES_HOME", "").strip()
    if env:
        return os.path.expanduser(os.path.expandvars(env))
    return os.path.join(home, ".hermes")


def hermes_homes() -> list[str]:
    """Every Hermes home this process can name: Hermes' resolved home, its root (which holds profiles/) and the
    account's default home when ``hermes_constants`` imports, $HERMES_HOME (and the root above a profiles/<name>
    home), and the platform default ~/.hermes."""
    out: list[str] = []
    hc = _hermes_constants()
    for name in ("get_hermes_home", "get_default_hermes_root", "account_default_hermes_home"):
        fn = getattr(hc, name, None) if hc is not None else None
        if callable(fn):
            try:
                out.append(str(fn()))
            except Exception:
                pass
    env = getattr(os, "environ", {}).get("HERMES_HOME", "").strip()
    if env:
        env = os.path.expanduser(os.path.expandvars(env))
        out.append(env)
        parent = os.path.dirname(os.path.normpath(env))
        if os.path.basename(parent) == "profiles":
            out.append(os.path.dirname(parent))
    out.append(os.path.join(os.path.expanduser("~"), ".hermes"))
    return out


def _roots() -> list[str]:
    """Each Hermes home, lexical and symlink-resolved, lower case, never the file system root."""
    cached = getattr(_CACHE, "roots", None)
    if cached is not None:
        return cached
    found: dict[str, None] = {}
    for h in hermes_homes():
        try:
            lex = _norm(os.path.normpath(os.path.abspath(h)))
        except (OSError, ValueError):
            continue
        for p in (lex, _real(lex)):
            low = p.rstrip("/").casefold()
            if low and "/" in low:
                found[low] = None
    _CACHE.roots = list(found)
    return _CACHE.roots


def _entry(rest: str) -> bool:
    """``rest``, a path below a home level, is one of Hermes' own entries (or a profile, or what a profile holds)."""
    parts = [x for x in rest.split("/") if x]
    while parts:
        first = parts[0]
        if first == "profiles":
            if len(parts) <= 2:
                return True                              # profiles/ or a whole profile
            parts = parts[2:]                            # profiles/<name>/...: the same entries, one level down
            continue
        return (first in HERMES_ENTRIES or first.startswith(HERMES_ENTRY_PREFIXES)
                or "/".join(parts[:2]) in HERMES_SUBENTRIES)
    return False


def _root_spans(text: str):
    """Where ``text`` (lower case) names a resolved Hermes home as a whole path component: (root, what follows)."""
    for root in _roots():
        i = text.find(root)
        while i >= 0:
            after = text[i + len(root):]
            if (i == 0 or text[i - 1] in PATH_START) and (not after or after[0] == "/" or PATH_END.match(after)):
                yield root, after
            i = text.find(root, i + 1)


def _marker_at_home(text: str, at: int) -> bool:
    """The `.hermes` written at ``text[at]`` is the folder at the top of a home (the user's, /root, /home/<x>,
    /Users/<x>), judged from what is written before it: an absolute path, `~`, `$HOME`, or a relative path against
    the session's working directory. A `.hermes` folder inside a project is not one. What cannot be worked out (a
    variable, a glob, `~user`, an unknown working directory) counts as one."""
    j = at
    while j > 0 and text[j - 1] not in PATH_START and not text[j - 1].isspace():
        j -= 1
    prefix = text[j:at]
    for pre in ("${home}/", "$home/", "~/"):
        if prefix.startswith(pre):
            prefix = _user_home() + "/" + prefix[len(pre):]
            break
    if re.search(r"[$`*?\[\]{}\\]", prefix) or prefix.startswith("~"):
        return True
    base = getattr(_CACHE, "cwd", None) or os.getcwd()
    if base == UNKNOWN:
        return True
    base = _norm(os.path.normpath(base)).rstrip("/")
    if not prefix.startswith("/"):
        prefix = base.casefold() + "/" + prefix
    cand = _norm(os.path.normpath(prefix + ".hermes"))
    if _dot_hermes(cand):
        return True
    # Inside the project (the working directory or below) or below the user's home: a project's own folder.
    # Anywhere else (`/srv/u/.hermes`), it may be the home of an account nobody listed: it counts.
    parent = os.path.dirname(cand)
    inside = {base.casefold(), _resolved(base).rstrip("/").casefold()}
    return not (any(parent == d or parent.startswith(d.rstrip("/") + "/") for d in inside)
                or any(parent.startswith(h + "/") for h in _user_homes()))


def _self_hit(text: str, anywhere: bool = False) -> bool:
    """``text`` (lower case: a path, a word or a code string) names one of Hermes' own entries in a home: a resolved
    home of this process, or the `.hermes` folder at the top of a home. A `.hermes` folder inside a project is
    ordinary (``_marker_at_home``); with ``anywhere``, for text whose working directory is not the session's (code
    that changes directory, another program's own arguments), every `.hermes` folder counts."""
    def below(after: str) -> bool:
        return _entry(PATH_END.split(after[1:] if after.startswith("/") else "", 1)[0])
    if any(below(after) for _, after in _root_spans(text)):
        return True
    for m in HOME_MARKERS.finditer(text):
        if below(text[m.end():]) and (anywhere or m.group(0) != ".hermes" or _marker_at_home(text, m.start())):
            return True
    return False


# Hermes named in plain words by text that is not read word by word (the part of a command or of a piece of code
# beyond what is lexed): its CLI run or looked up, its modules, a home level, one of its entries, tenure's data.
def _plain_hermes(text: str) -> tuple[str, str] | None:
    low = text.casefold().replace("\\", "/")
    if TENURE_NAMES.search(low):
        return "self:tenure", CAP
    if HERMES_RUN.search(text) or HERMES_ALIAS.search(text) or HERMES_CODE.search(text):
        return SELF_HERMES
    if _self_hit(low, anywhere=True):
        return "file:sensitive", CAP
    if HOME_MARKERS.search(low) or any(True for _ in _root_spans(low)):
        return "self:tenure", CAP                         # a home level, whatever is done to it
    return None


# ------------------------------------------------------------------------------------------- R35: fail-safe principle
# 1. Whatever names the Hermes program under another name is Hermes: a path to its bin/hermes, a file whose realpath
#    is Hermes' executable or lies in its installed package, a hard link to it, a link or copy of it (an executable
#    whose first 4 KB name hermes_cli), or code that looks it up. 2. A command that writes is capped when an argument
#    resolves (or a glob may resolve) to a Hermes home level (a home, the root, the ~/.hermes of a home, a
#    profiles/<name>) or entry, or when it runs inside one. Workspaces below a home level are not home levels. 3. R36:
#    a `cd` (pushd, env -C) to a level, an entry or a target that cannot be resolved is capped even alone.
HERMES_BIN = re.compile(r"(?:^|/)bin/hermes(?:-agent|-acp)?$")
HERMES_VAR = re.compile(r"\$(?:HERMES_HOME|\{HERMES_HOME\})(?:/+\.?)*/*")   # `$HERMES_HOME` alone: a level
GLOB = re.compile(r"[*?\[]")
USER_HOMES = re.compile(r"/(?:home|users)/[^/]+|/root|/var/root")
_TARGETS: dict = {}                                      # per process: Hermes' executables and package folders


def reset_hermes_targets() -> None:
    _TARGETS.clear()


def _distribution() -> tuple[set, list]:
    """(files, folders) of the installed hermes-agent distribution, as its own record lists them: every module it
    ships (hermes_cli, agent, tools, gateway...), its console scripts and its metadata. A folder is taken whole when
    the distribution puts Python modules in it, so a file added there later is covered too."""
    files, dirs = set(), []
    try:
        from importlib import metadata
        dist = metadata.distribution("hermes-agent")
        listed = list(dist.files or [])[:50000]
    except Exception:
        return files, dirs
    tops: dict[str, None] = {}
    for f in listed:
        parts = getattr(f, "parts", ())
        try:
            files.add(_norm(os.path.realpath(str(dist.locate_file(f)))).casefold())
        except (OSError, ValueError):
            continue
        if len(parts) > 1 and parts[0] not in ("..", ".", "bin", "__pycache__") and (
                str(f).endswith(".py") or parts[0].endswith((".dist-info", ".egg-info"))):
            tops[parts[0]] = None
    for top in tops:
        try:
            d = _norm(os.path.realpath(str(dist.locate_file(top)))).casefold()
        except (OSError, ValueError):
            continue
        if os.path.basename(d) not in ("site-packages", "dist-packages") and "/" in d.strip("/"):
            dirs.append(d)
    return files, dirs


def _hermes_targets() -> tuple[set, list, set]:
    """(realpaths of Hermes' executables, folders of its installed package, files of its distribution), lower case,
    found once per process. Without a distribution record, the folder of hermes_cli stands for the package."""
    if "v" in _TARGETS:
        return _TARGETS["v"]
    import shutil
    import sys
    exes, dirs = set(), []
    files, dist_dirs = _distribution()
    dirs += dist_dirs
    for name in sorted(HERMES_PROGS):
        for cand in (shutil.which(name), os.path.join(os.path.dirname(sys.executable or "/"), name)):
            if cand and os.path.isfile(cand):
                exes.add(_norm(os.path.realpath(cand)).casefold())
    try:
        import importlib.util
        spec = importlib.util.find_spec("hermes_cli")
        locs = list(spec.submodule_search_locations or []) if spec else []
    except Exception:
        locs = []
    for loc in locs:
        pkg = _norm(os.path.realpath(loc)).casefold()
        dirs.append(pkg)
        top = os.path.dirname(pkg)
        if os.path.basename(top) not in ("site-packages", "dist-packages"):
            dirs.append(top)                             # a source checkout: the whole install
    _TARGETS["v"] = (exes, list(dict.fromkeys(dirs)), files)
    return _TARGETS["v"]


def _in_package(real: str) -> bool:
    """``real`` is one of Hermes' executables, a file of its distribution, or lies in one of its package folders
    (it need not exist yet: a module added to the package is loaded like the others)."""
    low = real.rstrip("/").casefold()
    found = _hermes_targets()
    exes, dirs, files = found[0], found[1], found[2] if len(found) > 2 else ()
    return low in exes or low in files or any(low == d or low.startswith(d + "/") for d in dirs)


def _holds_hermes(full: str) -> bool:
    """``full`` is a folder that holds the Hermes program or its installed package (its bin, its site-packages, the
    environment above them): removing or moving it takes Hermes away with it."""
    found = _hermes_targets()
    cached = _TARGETS.get("holders")
    if cached is None or cached[0] is not found:
        exes, dirs, files = found[0], found[1], found[2] if len(found) > 2 else ()
        holders: set = set()
        for t in itertools.chain(exes, dirs, {os.path.dirname(f) + "/x" for f in files}):
            d = os.path.dirname(t.rstrip("/"))
            while d and d != "/" and d not in holders:
                holders.add(d)
                d = os.path.dirname(d)
        cached = (found, holders)
        _TARGETS["holders"] = cached
    return any(p.rstrip("/").casefold() in cached[1] for p in dict.fromkeys((full, _resolved(full), _lexical(full))))


def _loads_hermes(path: str) -> bool:
    """A small regular file whose first 4 KB name hermes_cli (a console script, a copy of one)."""
    try:
        if not os.path.isfile(path) or os.path.getsize(path) > 256 * 1024:
            return False
        with open(path, "rb") as fh:
            return b"hermes_cli" in fh.read(4096)
    except (OSError, ValueError):
        return False


def _same_inode(path: str) -> bool:
    """``path`` is a hard link to one of Hermes' executables."""
    try:
        st = os.stat(path)
    except (OSError, ValueError):
        return False
    for exe in _hermes_targets()[0]:
        try:
            other = os.stat(exe)
        except (OSError, ValueError):
            continue
        if (st.st_dev, st.st_ino) == (other.st_dev, other.st_ino):
            return True
    return False


def _is_hermes_file(real: str, executable: bool) -> bool:
    low = real.casefold()
    if _in_package(real):
        return True
    if os.path.basename(low) in HERMES_PROGS and os.path.isfile(real):
        return True
    return executable and (_same_inode(real) or _loads_hermes(real))


def _hermes_path(word: str, base: str, home: str) -> bool:
    """An argument that names the Hermes program: a path to a bin/hermes, or a file that resolves to Hermes."""
    w = _norm(_expand(word, home))
    if _computed(w) or not w or w.startswith("-"):
        return False
    if HERMES_BIN.search(w.rstrip("/")):
        return True
    try:
        real = _real(_abs(w, base, home))
    except (OSError, ValueError):
        return False
    memo = getattr(_CACHE, "memo", None)
    key = ("hermes-path", real)
    if memo is not None and key in memo:
        return memo[key]
    found = _in_package(real)
    if not found:
        try:
            import stat
            st = os.stat(real)
            found = _is_hermes_file(real, stat.S_ISREG(st.st_mode) and bool(st.st_mode & 0o111))
        except (OSError, ValueError, AttributeError):
            found = False
    if memo is not None:
        memo[key] = found
    return found


def _hermes_program(token: str, cwd, home: str) -> bool:
    """The program a command runs is Hermes under another name: a path or a PATH lookup that resolves to Hermes."""
    if not token or _computed(token):
        return False
    if "/" in token:
        if cwd == UNKNOWN and not os.path.isabs(_expand(token, home)):
            return False
        return _is_hermes_file(_real(_abs(token, cwd, home)), True)
    return _hermes_on_path(token, getattr(os, "environ", {}).get("PATH", ""))


def _hermes_on_path(name: str, path_value: str) -> bool:
    """The file PATH runs for ``name`` (its first executable match) is Hermes: a link to Hermes' executable or to a
    file named like it, a hard link to it, or a copy or script whose first 4 KB name hermes_cli. Looked up at every
    classify call, for the name invoked: a link made out of band since the last call is seen."""
    memo = getattr(_CACHE, "memo", None)
    key = ("which", name, path_value)
    if memo is not None and key in memo:
        return memo[key]
    found = False
    for d in [x for x in path_value.split(getattr(os, "pathsep", ":")) if x][:64]:
        p = os.path.join(d, name)
        try:
            if not os.path.isfile(p) or not os.access(p, os.X_OK):
                continue
        except (OSError, ValueError):
            continue
        found = name in HERMES_PROGS or _is_hermes_file(_real(_norm(p)), True)
        break
    if memo is not None:
        memo[key] = found
    return found


def _user_home() -> str:
    return _norm(os.path.normpath(getattr(_CACHE, "home", None) or os.path.expanduser("~"))).rstrip("/").casefold()


def _dot_hermes(p: str) -> bool:
    """``p`` (lower case) is a `.hermes` folder at the top of a home: the user's, /root, /home/<x>, /Users/<x>."""
    if os.path.basename(p) != ".hermes":
        return False
    parent = os.path.dirname(p)
    return parent == _user_home() or bool(USER_HOMES.fullmatch(parent))


def _home_level(path: str) -> bool:
    """``path`` is a Hermes home level: a resolved home or root ($HERMES_HOME among them), the `.hermes` folder at the
    top of a home (~, /root, /home/<x>, /Users/<x>), or a profiles/<name> folder of one of these. Never the user's home
    itself (Docker: HOME is the Hermes home), never a `.hermes` folder inside a project."""
    p = _norm(path).rstrip("/").casefold()
    if not p or p == _user_home():
        return False
    roots = _roots()
    if p in roots or _dot_hermes(p):
        return True
    parent = os.path.dirname(p)
    top = os.path.dirname(parent)
    return os.path.basename(parent) == "profiles" and (top in roots or _dot_hermes(top))


def _protected_dir(path: str) -> bool:
    """A working directory that is a home level, or lies in one of Hermes' entries (or tenure's data)."""
    full = _norm(os.path.normpath(path))
    for p in (full, _resolved(full)):
        low = p.casefold()
        if _home_level(p) or _self_hit(low) or TENURE_NAMES.search(low + "/"):
            return True
    return False


def _entry_inodes() -> set:
    """(device, inode) of the files Hermes keeps at the top of each home and profile, and of tenure's own data:
    a hard link to one of them is the same file under another name. Listed once per classify call."""
    memo = getattr(_CACHE, "memo", None)
    if memo is not None and "inodes" in memo:
        return memo["inodes"]
    found: set = set()
    folders: list[str] = []
    for h in dict.fromkeys(hermes_homes()):
        folders += [h, os.path.join(h, "plugin-data", "tenure")]
        try:
            folders += [os.path.join(h, "profiles", n) for n in sorted(os.listdir(os.path.join(h, "profiles")))[:64]]
        except (OSError, ValueError, AttributeError):
            pass
    for d in folders:
        own = d.replace("\\", "/").endswith("plugin-data/tenure")
        try:
            names = sorted(os.listdir(d))[:512]
        except (OSError, ValueError, AttributeError):
            continue
        for n in names:
            if not own and not _entry(n.casefold()):
                continue
            try:
                st = os.stat(os.path.join(d, n))
            except (OSError, ValueError, AttributeError):
                continue
            if _stat.S_ISREG(st.st_mode) and st.st_nlink > 1:
                found.add((st.st_dev, st.st_ino))
    if memo is not None:
        memo["inodes"] = found
    return found


def _linked_entry(real: str) -> bool:
    """``real`` is a hard link to one of Hermes' own files or to tenure's data."""
    try:
        st = os.stat(real)
    except (OSError, ValueError, AttributeError):
        return False
    return (_stat.S_ISREG(st.st_mode) and st.st_nlink > 1 and (st.st_dev, st.st_ino) in _entry_inodes())


def _user_homes() -> set:
    user = _user_home()
    return {user, _real(user).rstrip("/").casefold()}


def _path_hit(full: str, home: str, above: bool = True) -> tuple[str, str] | None:
    """The one check on a path (absolute and normalised; its links are resolved here): it is tenure's own data, a
    Hermes home level, one of Hermes' entries, a hard link to one, the Hermes program or a file of its package, or
    (``above``) a folder above a Hermes home, the user's own home excepted. Whoever names it, whatever the spelling
    was: `/./`, `..`, a relative path, a link."""
    memo = getattr(_CACHE, "memo", None)
    key = ("path-hit", full, above)
    if memo is not None and key in memo:
        return memo[key]
    hit = None
    real = _resolved(full)
    for p in dict.fromkeys((full, _lexical(full), real)):
        low = p.rstrip("/").casefold()
        if TENURE_NAMES.search(low + "/") or _home_level(p):
            hit = ("self:tenure", CAP)
        elif _self_hit(low):
            hit = ("file:sensitive", CAP)
        elif above and _above_home(p) and low not in _user_homes():
            hit = ("file:sensitive", CAP)
        if hit:
            break
    if hit is None and _dir_exists(full):
        if _linked_entry(real):
            hit = ("file:sensitive", CAP)
        elif _hermes_path(full, "/", home):
            hit = SELF_HERMES
    if hit is None and HERMES_BIN.search(full.rstrip("/")):
        hit = SELF_HERMES
    if memo is not None:
        memo[key] = hit
    return hit


def _arg_paths(word: str) -> list[str]:
    """The paths an argument may name: itself, its parts around `:`, `=` and `,` (-v a:b, --volume=a:b, --mount
    type=bind,src=a), and the value glued to a short option (-Cdir, -d~/x). The parts keep their quoting."""
    out, start = [word], 0
    for m in re.finditer(r"[:=,]", _view(word)):
        out.append(_cut(word, start, m.start()))
        start = m.end()
    if start:
        out.append(_cut(word, start))
    if re.match(r"-[A-Za-z][^-]", word):
        # A value glued to the last letter of a group of short options (`-xCdir`, `-cffile`, `-odDIR`, `-rtDIR`):
        # which letter takes it depends on the program, so what follows each leading letter is a candidate.
        letters = re.match(r"-[A-Za-z]+", _view(word)).end()
        out += [_cut(word, k) for k in range(2, min(letters, 16) + 1)]
    seen = []
    for x in out:
        if x and not x.startswith("-") and (x is word or x != word) and x not in seen:
            seen.append(x)
    return seen


def _dir_exists(path: str) -> bool:
    """The folder holding ``path`` exists (one lstat per folder per classify call): a path in a missing folder has no
    symlink to resolve, and resolving it can be slow (an automount such as macOS's /home)."""
    d = os.path.dirname(path.rstrip("/")) or "/"
    memo = getattr(_CACHE, "memo", None)
    key = ("dir", d)
    if memo is not None and key in memo:
        return memo[key]
    try:
        found = os.path.lexists(d)
    except (OSError, ValueError):
        found = False
    if memo is not None:
        memo[key] = found
    return found


def _resolved(full: str) -> str:
    return _real(full) if _dir_exists(full) else full


def _part_may(name: str, part: str) -> bool:
    """A glob part may match the name (a hidden name only with a part that starts with a dot, as the shell does)."""
    if name.startswith(".") and not part.startswith("."):
        return False
    return fnmatch.fnmatchcase(name, part)


def _glob_may_reach(pattern: str) -> bool:
    """A glob (absolute, lower case) may name a home level or an entry: matched part by part against each home
    level, then Hermes' entries and profiles below it."""
    parts = [x for x in pattern.split("/") if x]
    levels = list(_roots()) + [_user_home() + "/.hermes"]
    for level in levels:
        lp = [x for x in level.split("/") if x]
        if len(parts) < len(lp) or not all(_part_may(n, q) for n, q in zip(lp, parts)):
            continue
        rest = parts[len(lp):]
        while rest:
            if _part_may("profiles", rest[0]) and len(rest) <= 2:
                return True                                  # profiles/ or a profile: a level
            if any(_part_may(e, rest[0]) for e in HERMES_ENTRIES) or rest[0].startswith(HERMES_ENTRY_PREFIXES):
                return True
            if _part_may("profiles", rest[0]):
                rest = rest[2:]                              # an entry of a profile
                continue
            break
        else:
            return True                                      # the level itself
    return False


GLOB_RUNS = re.compile(r"\*|\?|\[[^\]]*\]?")


def _hermes_hint(text: str) -> bool:
    """A literal run of ``text`` (between glob characters) holds three letters in a row of `hermes`."""
    for run in GLOB_RUNS.split(text.casefold()):
        if any(run[i:i + 3] in "hermes" for i in range(len(run) - 2)):
            return True
    return False


def _glob_named(word: str) -> bool:
    """R37: a glob is looked at only when its literal part names Hermes (`herm?s`, `her*`) or one of its entries
    (`bin/*`, `profiles/c*`); any other glob follows the ordinary rules."""
    if _hermes_hint(word):
        return True
    parts = [x.casefold() for x in _norm(word).split("/") if x and not GLOB.search(x)]
    return any(x in HERMES_ENTRIES or x == "profiles" or x.startswith(HERMES_ENTRY_PREFIXES) for x in parts)


def _glob_above(pattern: str) -> bool:
    """A glob (absolute, lower case) may name a folder above a Hermes home (the user's own home excepted)."""
    parts = [x for x in pattern.split("/") if x]
    users = _user_homes()
    for level in _roots():
        lp = [x for x in level.split("/") if x]
        if (parts and len(parts) < len(lp) and all(_part_may(n, q) for n, q in zip(lp, parts))
                and "/" + "/".join(lp[:len(parts)]) not in users):
            return True
    return False


def _glob_hit(pattern: str, home: str, word: str | None = None, named: bool = True,
              above: bool = True) -> tuple[str, str] | None:
    """A glob that may match a home level, an entry, or the Hermes program: what exists is expanded on disk (256
    names at most, two wildcard parts at most), and the pattern itself is matched against the levels and entries,
    as written and with the links of its literal folder resolved. With ``named`` (a `cd` target), only a glob whose
    literal part names Hermes or an entry (``word``, as written) is looked at (R37); for the arguments of a command
    that is not a pure read, every glob is, and a folder above a home counts."""
    import glob
    if named and not _glob_named(word if word is not None else pattern):
        return None
    names = []
    if len([x for x in pattern.split("/") if GLOB.search(x)]) <= 2 and "**" not in pattern:
        try:
            names = list(itertools.islice(glob.iglob(pattern), 256))
        except (OSError, ValueError, re.error):
            names = []
    for name in names:
        name = _norm(name)
        if not named:
            hit = _path_hit(_norm(os.path.normpath(name)), home, above)
            if hit:
                return hit
            continue
        if _protected_dir(name):
            return "self:tenure", CAP
        if _hermes_path(name, "/", home):
            return SELF_HERMES
    patterns = [pattern]
    if not named:
        first = GLOB.search(pattern)
        cut = pattern.rfind("/", 0, first.start()) if first else -1
        if cut > 0:
            folder = _resolved(pattern[:cut])
            if folder != pattern[:cut]:
                patterns.append(folder + pattern[cut:])
        star = pattern.find("/**")
        if star > 0 and not GLOB.search(pattern[:star]):     # a recursive glob: everything below its folder
            top = pattern[:star]
            if _protected_dir(top) or (above and any(
                    _above_home(q) and q.rstrip("/").casefold() not in _user_homes() for q in (top, _resolved(top)))):
                return "self:tenure", CAP
    for pat in patterns:
        if _glob_may_reach(pat.casefold()) or (not named and above and _glob_above(pat.casefold())):
            return "self:tenure", CAP
    head, base = os.path.split(pattern.rstrip("/"))
    if (_hermes_hint(base) and any(_part_may(p, base) for p in HERMES_PROGS)
            and _part_may("bin", os.path.basename(head))):
        return SELF_HERMES
    return None


VAR_REF = re.compile(r"\$(?:[A-Za-z_{(]|\d|[@*#?!$-])|`")
BRACE_LIST = re.compile(r"\{[^{}\s\"':]*,[^{}\s\"':]*\}")
HERMES_PART = re.compile(r"(?:^|(?<=[/=:,{(\s'\"`]))(?:\.hermes|hermes)(?=$|[/,})\s'\"`:])")


def _unresolved(word: str) -> bool:
    """R37: a word the shell computes in a way that is not read here: a variable or substitution, a brace list, `~user`
    or the {} of xargs or find (a glob is judged apart). Words with blanks are text, unless they hold a substitution;
    a word written between single quotes is literal text."""
    word = _view(word)
    if not word:
        return False
    if any(ch.isspace() for ch in word) and "$(" not in word and "`" not in word:
        return False
    return bool(VAR_REF.search(word) or BRACE_LIST.search(word) or "{}" in word or re.match(r"~[A-Za-z_]", word))


def _braces(word: str, limit: int = 32) -> list[str]:
    """The words a brace list expands to (at most ``limit``)."""
    out, todo = [], [word]
    while todo and len(out) < limit:
        w = todo.pop()
        m = BRACE_LIST.search(w)
        if not m:
            out.append(w)
            continue
        for alt in m.group(0)[1:-1].split(","):
            todo.append(w[:m.start()] + alt + w[m.end():])
    return out or [word]


def _names_hermes(word: str, cwd, home: str) -> bool:
    """The literal part of an unresolved word names a Hermes level, an entry, `.hermes`, `hermes` or $HERMES_HOME."""
    low = word.casefold()
    if "$hermes_home" in low or "${hermes_home" in low:
        return True
    for alt in _braces(word):
        e = _expand(alt, home)
        low = _norm(e).casefold()
        if HERMES_PART.search(low) or _self_hit(low, anywhere=True) or TENURE_NAMES.search(low):
            return True
        if not _unresolved(e) and not GLOB.search(e) and (cwd != UNKNOWN or os.path.isabs(e)):
            if _protected_dir(_abs(e, "/" if cwd == UNKNOWN else cwd, home)):
                return True
    return False


PATH_OPTS = {"-C", "-d", "-t", "-o", "--directory", "--target-directory", "--one-top-level", "--output", "--mount",
             "-v", "--volume", "--chdir"}
PATH_PROGS = {"unzip", "7z", "7za", "7zz", "unrar", "dd"}         # with WRITERS and ARCHIVERS


def _path_words(tokens: list[str]) -> list[str]:
    """The words of a command that name where it writes: redirection targets, the values of -C, -d, -t, -o,
    --directory, --mount, -v..., and the arguments of the programs that write files (cp, mv, ln, rm, mkdir, touch,
    chmod, tar, unzip...). Other option values (a commit message, a header, a version) are not paths."""
    toks = _unwrap(tokens)
    out = list(_redirects(tokens))
    if not toks:
        return out
    prog, args = os.path.basename(toks[0]), toks[1:]
    for n, a in enumerate(args):
        if a in PATH_OPTS and n + 1 < len(args):
            out.append(args[n + 1])
        elif a.startswith("--") and a.split("=", 1)[0] in PATH_OPTS and "=" in a:
            out.append(_cut(a, a.index("=") + 1))
        elif re.fullmatch(r"-[Cdto].+", a):
            out.append(_cut(a, 2))
        else:                                                # glued to a group: -xC$DIR, -cf$FILE, -rt$DIR
            m = re.fullmatch(r"-([A-Za-z]{2,})([^A-Za-z].*)", _view(a))
            if m and (m.group(1)[-1] in "Cdto" or prog in PATH_PROGS or prog in WRITERS or prog in ARCHIVERS):
                out.append(_cut(a, m.start(2)))
    if prog in PATH_PROGS or prog in WRITERS or prog in ARCHIVERS:
        out += [a for a in args if not a.startswith("-")]
    return out


def _unresolved_floor(tokens: list[str], cwd, home: str) -> tuple[str, str] | None:
    """R37, for a command that writes: a path it writes to that cannot be resolved is at least high stakes; capped
    when its literal part names Hermes."""
    toks = _unwrap(tokens)
    if toks and (os.path.basename(toks[0]) in FINDS or os.path.basename(toks[0]) == "parallel"):
        return None                                      # their {} is read where it runs (_find_inner, _parallel)
    found = False
    for word in _path_words(tokens):
        for cand in dict.fromkeys([word] + _arg_paths(word)):
            if _unresolved(cand):
                if _names_hermes(cand, cwd, home):
                    program = re.search(r"(?<![.\w-])hermes(?:-agent|-acp)?(?![\w.-])", cand.casefold())
                    dotted = any(".hermes" in alt.casefold() for alt in _braces(cand))
                    return SELF_HERMES if program and not dotted else ("self:tenure", CAP)
                found = True
    return ("file:unknown", HIGH) if found else None


def _absolute_members(toks: list[str]) -> bool:
    """R37: an archive unpacked with its absolute member names kept (tar -P, --absolute-names; unzip -:)."""
    if not toks:
        return False
    prog, args = os.path.basename(toks[0]), toks[1:]
    if prog in ARCHIVERS:
        first = args[:1] if args and not args[0].startswith("-") else []
        return any(a == "--absolute-names" or re.fullmatch(r"-[A-Za-z]*P[A-Za-z]*", a) for a in args) or any(
            "P" in a for a in first)
    return prog == "unzip" and "-:" in args


def _pwd(d: str, cwd) -> str:
    """`$PWD` at the start of a cd target is the working directory, when it is known."""
    if cwd == UNKNOWN or not d.startswith(("$PWD", "${PWD}")):
        return d
    return re.sub(r"^\$(?:PWD|\{PWD\})(?=/|$)", lambda m: cwd.rstrip("/") or "/", d)


def _chdir_hit(d: str, cwd, home: str) -> tuple[str, str] | None:
    """A `cd` (pushd, env -C) target that is a home level or an entry, or that cannot be resolved (a variable, a
    substitution), or a glob that may reach one: capped, even when nothing follows (R36)."""
    if d == "-" or not d:
        return None
    if HERMES_VAR.fullmatch(d):
        return "self:tenure", CAP
    d = _pwd(d, cwd)
    e = _expand(d, home)
    if _unresolved(e) or "$" in e:
        return ("self:tenure", CAP) if _names_hermes(e, cwd, home) else ("file:unknown", HIGH)
    if e.startswith("~") or "{" in e or (cwd == UNKNOWN and not os.path.isabs(e)):
        return None
    full = _abs(e, "/" if cwd == UNKNOWN else cwd, home)
    if GLOB.search(e):
        return _glob_hit(full, home, d)
    # `cd link/..` stays next to the link (the shell normalises the text), `cd -P link/..` goes next to its target
    return ("self:tenure", CAP) if _protected_dir(full) or _protected_dir(_lexical(full)) else None


def _r35(tokens: list[str], cwd, home: str, reads: bool = False) -> tuple[str, str] | None:
    """The fail-safe principle for one command that writes: a Hermes home level or entry as an argument (a glob that
    may reach one included) or as the working directory (self:tenure), the Hermes program named as an argument
    (self:hermes)."""
    toks = _unwrap(tokens)
    if not toks or _seg_pure(tokens) or _cd_kind(tokens) or _hermes_read(tokens):
        return None
    if cwd != UNKNOWN and _protected_dir(cwd):
        return "self:tenure", CAP
    if cwd != UNKNOWN and _extracts(toks):                   # an archive unpacked above a home lands in it
        here = _norm(os.path.normpath(cwd))
        if any(_above_home(p) and p.rstrip("/").casefold() not in _user_homes() for p in (here, _resolved(here))):
            return "file:sensitive", CAP
    base = "/" if cwd == UNKNOWN else cwd
    text_tool = os.path.basename(toks[0]) in SEPARATOR_PROGS | READ_ONLY | AWKS
    # Where a relative `.hermes/...` leads is not the session's folder when the folder is unknown, when the command
    # is told to work elsewhere (-C, --directory, --work-tree...) or runs its words somewhere else (ssh, su, docker).
    raw = _unwrap(tokens, wrappers=False)
    elsewhere = (cwd == UNKNOWN or os.path.basename(toks[0]) in ELSEWHERE_PROGS
                 or any(a.startswith(ELSEWHERE_OPTS) for a in raw[1:])
                 or (os.path.basename(raw[0]) in ("sudo", "doas") and bool(
                     {"-i", "--login", "-D"} & set(raw[1:len(raw) - len(toks) + 1]))))
    for word in toks[1:] + _redirects(tokens):
        hit = _word_hit(word, base, cwd, home, text_tool, reads)
        if hit:
            return hit
        if elsewhere and _self_hit(_norm(_expand(word, home)).casefold(), anywhere=True):
            return "file:sensitive", CAP
    return None


ELSEWHERE_PROGS = {"script", "su", "tmux", "screen", "expect", "ssh", "docker", "podman", "kubectl", "chroot", "nsenter"}
ELSEWHERE_OPTS = ("-C", "--directory", "--chdir", "--cwd", "--work-tree", "--git-dir", "--prefix", "--root")


# Programs that take a separator as an argument (`cut -d /`, `tr / _`, `paste -d/`): a lone `/` is not a folder.
SEPARATOR_PROGS = {"paste", "join", "xargs", "split", "csplit", "column", "sed", "gsed", "perl", "ruby", "python",
                   "python3", "node", "jq", "yq", "expand", "unexpand", "fold", "fmt", "comm", "numfmt", "rev"}
ENV_LOOKUP = re.compile(r"(?:ENV|ENVIRON|environ|env|getenv)\W{1,3}HERMES_HOME\b")    # $ENV{..}, ENV[".."], process.env..
STRING_PIECES = re.compile(r"[\s'\"`;,()=<>|\[\]]+")


def _word_cands(word: str) -> list[tuple[str, bool]]:
    """The paths a word may hold, each with whether a folder above a home counts for it: the word, the value glued
    to an option (`--target=dir`, `-odir`), the sides of `a:b` and `a,b` for a word that starts like a local path,
    and, for a quoted string with blanks (a command, a statement given to another program), each piece that looks
    like a path."""
    if any(ch.isspace() for ch in word):
        out = []
        for piece in STRING_PIECES.split(str(word)):
            for sub in dict.fromkeys((piece, piece.split(":", 1)[-1])):
                if sub and ("/" in sub or sub.startswith(("~", "..")) or sub == "$HERMES_HOME"):
                    out.append((sub, sub.startswith(("/", "~/")) and len(sub) > 2))
                elif sub and len(sub) < 256 and sub == piece and not _computed(sub):
                    out.append((sub, False))                 # a bare name: a link in the working directory?
        return out[:96]
    local = word.startswith(("/", "~", ".", "-", "$"))
    out = []
    for n, cand in enumerate(_arg_paths(word)):
        whole = n == 0
        sided = not whole and (":" in _view(word) or "," in _view(word))
        out.append((cand, whole or local or not sided))
    return out


def _computed_hit(cand: str, base: str, home: str, above: bool = True) -> tuple[str, str] | None:
    """A path whose end is computed (`~/.hermes/$X`, `dir/$(cmd)`): what comes before the computed part is resolved.
    Below a home level, inside an entry, or below a folder above a home (the user's own home excepted), what it
    computes may be Hermes' own: capped."""
    m = re.search(r"[$`]", cand)
    cut = cand.rfind("/", 0, m.start()) if m else -1
    if cut <= 0 or _computed(cand[:cut]):
        return None
    full = _abs(cand[:cut], base, home)
    if _protected_dir(full):
        return "self:tenure", CAP
    if above and any(_above_home(p) and p.rstrip("/").casefold() not in _user_homes()
                     for p in (full, _resolved(full))):
        return "file:sensitive", CAP                     # computed below a folder that holds a home
    return None


def _word_hit(word: str, base: str, cwd, home: str, text_tool: bool = False,
              reads: bool = False) -> tuple[str, str] | None:
    """One argument of a command that is not a pure read: each path it may hold is normalised, then resolved (the
    working directory, `~`, links, each alternative of a brace list, a glob expanded on disk), and judged by
    ``_path_hit``. For a command that only reads (``reads``: `find / -name x`, `git -C .. status`), a folder above
    a home is not a target."""
    if ENV_LOOKUP.search(word):
        return "self:tenure", CAP                         # Hermes' home read from the environment by a program
    for cand, above in _word_cands(word):
        above = above and not reads
        if HERMES_VAR.fullmatch(cand):
            return "self:tenure", CAP
        view = _view(cand)
        alts = [cand]
        if BRACE_LIST.search(view) and not re.search(r"[$`]", view):
            alts = _braces(str(cand))
        for alt in alts:
            alt = _expand(alt, home)
            if not alt or (cwd == UNKNOWN and not os.path.isabs(alt)):
                continue
            if re.search(r"[$`]", alt) or (alt.startswith("~") and alt != "~" and not alt.startswith("~/")):
                hit = _computed_hit(alt, base, home, above)
            elif "{" in alt and BRACE_LIST.search(alt):
                continue                                     # more alternatives than are read
            elif GLOB.search(alt):
                hit = _glob_hit(_abs(alt, base, home), home, named=False, above=above)
            else:
                full = _abs(alt, base, home)
                root = full == "/"
                hit = _path_hit(full, home, above and not (root and (text_tool or cand is not word)))
            if hit:
                return hit
    return None


ARCHIVERS = {"tar", "gtar", "bsdtar"}
UNPACKERS = {"unzip", "unrar", "7z", "7za", "7zz", "unar", "cpio", "pax", "jar"}


def _extracts(toks: list[str]) -> bool:
    """The command unpacks an archive (tar x, unzip, 7z x, python -m zipfile -e...)."""
    if not toks:
        return False
    prog, args = os.path.basename(toks[0]), toks[1:]
    if prog in ARCHIVERS:
        if args and not args[0].startswith("-") and "x" in args[0]:
            return True                                      # tar xf
        return any(a in ("--extract", "--get") or re.fullmatch(r"-[A-Za-z]*x[A-Za-z]*", a) for a in args)
    if prog == "unzip":
        return not any(a in ("-l", "-t", "-v", "-Z", "-p", "-z") for a in args)
    if prog in ("unrar", "7z", "7za", "7zz", "jar"):
        return bool(args) and args[0].lstrip("-")[:1] in ("x", "e")
    if prog == "cpio":
        return any(re.fullmatch(r"-[A-Za-z]*i[A-Za-z]*", a) or a == "--extract" for a in args)
    if prog in ("unar", "pax"):
        return prog == "unar" or "-r" in args
    base = re.sub(r"\d+(\.\d+)*$", "", prog)
    if base in ("python", "python2", "python3") and "-m" in args:
        i = args.index("-m")
        return args[i + 1:i + 2] in (["zipfile"], ["tarfile"]) and bool({"-e", "--extract"} & set(args))
    return False


def _into_user_home(tokens: list[str], cwd, home: str) -> bool:
    """An archive is unpacked into the user's home: run there, or given it as a destination (R36: high stakes)."""
    toks = _unwrap(tokens)
    if not _extracts(toks):
        return False
    user = _norm(os.path.normpath(home)).rstrip("/").casefold()
    users = {user, _real(user).rstrip("/").casefold()}
    if cwd != UNKNOWN and {_norm(os.path.normpath(cwd)).rstrip("/").casefold(),
                           _resolved(_norm(os.path.normpath(cwd))).rstrip("/").casefold()} & users:
        return True
    base = "/" if cwd == UNKNOWN else cwd
    for word in toks[1:]:
        for cand in _arg_paths(word):
            cand = _expand(cand, home)
            if _computed(cand) or (cwd == UNKNOWN and not os.path.isabs(cand)):
                continue
            if _abs(cand, base, home).rstrip("/").casefold() in users:
                return True
    return False


TREE_COPIERS = {"cp", "gcp", "ditto", "rsync", "install"}
GIT_TREE_WRITES = {"checkout", "reset", "restore", "switch", "stash", "merge", "pull", "clone", "apply", "am",
                   "cherry-pick", "rebase", "revert", "read-tree", "checkout-index", "worktree", "init"}


def _tree_above_home(tokens: list[str], cwd, home: str) -> tuple[str, str] | None:
    """A recursive copy (cp -r/-R/-a, ditto, rsync) or a git work tree (`--work-tree`, `-C`) that writes into the
    user's home or into a folder above a Hermes home: whole folders land there, Hermes' own included (audit 10/11).
    High stakes; capped when a word names a `.hermes` folder."""
    toks = _unwrap(tokens)
    if not toks:
        return None
    prog, args = os.path.basename(toks[0]), toks[1:]
    dests: list[str] = []
    if prog in TREE_COPIERS:
        recursive = prog in ("ditto", "rsync") or any(
            a in ("--recursive", "--archive") or re.fullmatch(r"-[A-Za-z]*[rRa][A-Za-z]*", a)
            for a in args if not a.startswith("--") or a in ("--recursive", "--archive"))
        words = [a for a in args if not a.startswith("-")]
        if not recursive or not words:
            return None
        dests = [words[-1]]
        for n, a in enumerate(args):                         # cp -t DIR / --target-directory=DIR
            if a in ("-t", "--target-directory") and n + 1 < len(args):
                dests.append(args[n + 1])
            elif a.startswith("--target-directory="):
                dests.append(a.split("=", 1)[1])
    elif prog == "git":
        plain = _strip(args, GIT_VALUE_OPTS)
        if not plain or plain[0] not in GIT_TREE_WRITES:
            return None
        for n, a in enumerate(args):
            if a in ("-C", "--work-tree", "--git-dir") and n + 1 < len(args):
                dests.append(args[n + 1])
            elif a.startswith(("--work-tree=", "--git-dir=")):
                dests.append(a.split("=", 1)[1])
            elif a.startswith("-C") and len(a) > 2:
                dests.append(a[2:])
        if not dests and plain[0] in ("clone", "worktree", "init") and len(plain) > 1:
            dests.append([w for w in plain[1:] if not w.startswith("-")][-1] if any(
                not w.startswith("-") for w in plain[1:]) else "")
    else:
        return None
    base = "/" if cwd == UNKNOWN else cwd
    user = _norm(os.path.normpath(home)).rstrip("/").casefold()
    users = {user, _real(user).rstrip("/").casefold()}
    for dest in dests:
        cand = _expand(dest, home)
        if not cand or _computed(cand) or (cwd == UNKNOWN and not os.path.isabs(cand)):
            continue
        full = _abs(cand, base, home)
        low = full.rstrip("/").casefold()
        if low in users or _above_home(full) or _above_home(_real(full)):
            named = any(re.search(r"(?:^|/)\.hermes(?:/|$)", w.casefold().rstrip("/")) for w in args)
            return ("file:sensitive", CAP) if named else ("file:unknown", HIGH)
    return None


def _above_home(full: str) -> bool:
    """``full`` is a Hermes home or a folder above one: removing or moving it takes the home with it."""
    low = full.rstrip("/").casefold()
    return any(root == low or root.startswith(low + "/") for root in _roots())


# Files git reads configuration (and so programs to run) from: a repository's config and hooks (submodules and work
# trees included), the user's global configuration (audit 10/11). An attribute only names a driver defined in the
# configuration, and git ignores `!command` in .gitmodules: those two files are ordinary.
GIT_CONFIG_FILES = re.compile(r"(?:^|/)\.git/(?:(?:modules|worktrees)/(?:[^/]+/)*?)?(?:config(?:\.worktree)?$"
                              r"|hooks(?:/|$)|commondir$)|(?:^|/)\.gitconfig$|(?:^|/)\.config/git/config$")


# Files a shell, the session manager or Python runs by themselves: start-up files, login agents and services,
# Python's site hooks, and the user's own program folder that comes before the system on PATH (counter-audit P1).
START_UP_FILES = re.compile(r"(?:^|/)\.(?:zshenv|zshrc|zprofile|zlogin|zlogout|bashrc|bash_profile|bash_login|bash_logout"
                            r"|profile|kshrc|cshrc|tcshrc|login|inputrc|bash_aliases|(?:zshenv|zshrc|zprofile|zlogin)\.zwc|curlrc"
                            r"|wgetrc|lesskey|less|vimrc|exrc|gvimrc|nanorc)$|/\.config/(?:lesskey|bat/config)$|/\.oh-my-zsh/custom/|/\.cargo/env$|/\.config/(?:gh|nvim)/|/library/launchagents/|/library/launchdaemons/"
                            r"|/\.config/(?:systemd/user|autostart|fish)/|(?:^|/)(?:site|user)customize\.py$"
                            r"|/site-packages/[^/]*\.pth$|/\.local/bin/")


# Folders whose contents run by themselves, as a destination: what is copied, moved or unpacked into them runs.
AUTORUN_DIRS = re.compile(r"(?:^|/)\.local/bin$|/library/launch(?:agents|daemons)$"
                          r"|/\.config/(?:systemd/user|autostart|fish|gh|nvim)$|/\.oh-my-zsh(?:/custom)?$|(?:^|/)\.git$")


def _sensitive(probe: str) -> bool:
    low = probe.casefold()
    return bool(any(f in low for f in SENSITIVE_FRAGMENTS) or GIT_CONFIG_FILES.search(low.rstrip("/"))
                or AUTORUN_DIRS.search(low.rstrip("/"))
                or START_UP_FILES.search(low.rstrip("/"))
                or any(d.casefold() in low + "/" for d in SENSITIVE_DIRS)
                or low.startswith(tuple(x.casefold() for x in SENSITIVE_PREFIXES))
                or SENSITIVE_NAME.match(low.rstrip("/").rsplit("/", 1)[-1])
                or _self_hit(low))


def _file(path: str, cwd: str | None, home: str) -> tuple[str, str, bool]:
    base = cwd or os.getcwd()
    full = _abs(path, base, home)
    real = _real(full)
    lexical = _lexical(full)                             # `link/../x` as a program that normalises by itself reads it
    if any(TENURE_NAMES.search(p.casefold()) for p in (full, real, lexical)):
        return "self:tenure", CAP, False
    if not _computed(_norm(_expand(path, home))) and (HERMES_BIN.search(full.rstrip("/"))
                                                     or _hermes_path(full, "/", home)
                                                     or (lexical != full and _hermes_path(lexical, "/", home))):
        return "self:hermes", CAP, False                 # the Hermes program, or a file of its installed package
    if _sensitive(full) or _sensitive(real) or _linked_entry(real) or (lexical != full and _sensitive(lexical)):
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
    bare = [q for q in (p.strip("'\"") for p in _v4a_paths(str(args.get("patch") or "")) if p[:1] in "'\"") if q]
    paths += [_abs(q, cwd, home) for q in bare] if tool_name == "patch" else []     # a header path given in quotes
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
WRAPPERS = {"sudo", "env", "nohup", "time", "nice", "command", "exec", "stdbuf", "doas", "builtin", "busybox",
            "setsid"}
OUTSIDE = {"scp": "shell:scp", "sftp": "shell:sftp", "ssh": "shell:ssh", "ftp": "shell:ftp", "mail": "shell:mail",
           "sendmail": "shell:mail", "mutt": "shell:mail", "nc": "shell:nc", "ncat": "shell:nc", "telnet": "shell:nc",
           "crontab": "schedule:crontab", "at": "schedule:at", "batch": "schedule:at", "launchctl": "schedule:launchctl"}
PUBLISH = {("npm", "publish"), ("pnpm", "publish"), ("yarn", "publish"), ("twine", "upload"), ("cargo", "publish"),
           ("gem", "push"), ("docker", "push"), ("podman", "push"), ("docker", "login"), ("git", "push")}
CLOUD = {"aws", "gcloud", "az"}
CLOUD_WRITE = {"create", "delete", "put", "update", "deploy", "rm", "cp", "mv", "sync", "mb", "rb", "set", "add",
               "remove", "attach", "detach", "start", "stop", "terminate", "run", "invoke", "publish", "send"}
CLOUD_READ = {"describe", "list", "get", "show", "ls", "help", "wait", "version", "info", "search", "lookup", "whoami"}


def _cloud_read(args: list[str]) -> bool:
    """A cloud CLI call is a read when one of its words (the operation, after the service) starts with a read verb
    (``describe-instances``, ``get-caller-identity``, ``list``, ``s3 ls``) and none carries a write verb, dashes
    included (``terminate-instances``, ``send-email``, ``put-object``). Anything else leaves the machine."""
    words = [a.lower() for a in args if a and not a.startswith("-") and "=" not in a and "/" not in a]
    parts = [w.split("-") for w in words]
    if any(set(p) & (CLOUD_WRITE | CLOUD_WRITE_MORE) for p in parts):
        return False
    return any(p[0] in CLOUD_READ for p in parts[1:] or parts)


CLOUD_WRITE_MORE = {"upload", "up", "patch", "modify", "reboot", "restore", "import", "export", "enable", "disable",
                    "grant", "revoke", "tag", "untag", "copy", "move", "apply", "promote", "failover", "reset", "rotate",
                    "submit", "execute", "exec", "ssh", "scp", "login", "configure", "init", "build", "push", "release"}
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
# Audit 10/11: variables that make an ordinary program run code of the agent's choosing (the program lookup, the
# dynamic loader, shell start-up files, git's configuration, pagers, editors, interpreter option variables, the home
# folders configuration is read from, Hermes' own). Assigning one, as a prefix, behind env or with export, is capped:
# a read-only command would otherwise run a project file without anyone being asked.
HIJACK_VARS = re.compile(
    r"(?:PATH|LD_\w+|DYLD_\w+|BASH_ENV|ENV|ZDOTDIR|PROMPT_COMMAND|IFS|PS4|SHELLOPTS|BASHOPTS|CDPATH"
    r"|GIT_(?!AUTHOR_|COMMITTER_|TERMINAL_PROMPT$|TRACE|OPTIONAL_LOCKS$|PROGRESS_DELAY$)\w+|PAGER|MANPAGER|LESSOPEN|LESSCLOSE|LESSKEY\w*|EDITOR|VISUAL"
    r"|PYTHONSTARTUP|PYTHONHOME|PYTHONBREAKPOINT|PYTHONUSERBASE|NODE_OPTIONS|PERL5OPT|PERL5DB|RUBYOPT"
    r"|JAVA_TOOL_OPTIONS|_JAVA_OPTIONS|GCONV_PATH|\w*ASKPASS|LESS|BROWSER|TERMINFO|TERMINFO_DIRS"
    r"|HOME|XDG_CONFIG_HOME|XDG_CONFIG_DIRS|XDG_DATA_HOME|HERMES_\w+)")
# Assignments that change nothing a read-only command runs: it stays free. Any other assignment lifts it to high.
HARMLESS_VARS = re.compile(r"(?:LANG|LANGUAGE|LC_\w+|TZ|TERM|COLUMNS|LINES|NO_COLOR|FORCE_COLOR|CLICOLOR\w*"
                           r"|GREP_COLOR\w*|LS_COLORS)")
ASSIGN_WORD = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\+?=")
APPENDED_PATH = re.compile(r"^PATH=(?:\$PATH|\$\{PATH\})(?::|$)")   # the system's programs still come first
# Builtins that assign the variables they name (`printf -v PATH`, `read PATH`, `for PATH in`, `declare -n r=PATH`).
ASSIGNING_BUILTINS = {"printf", "read", "mapfile", "readarray", "getopts", "for", "declare", "typeset", "local",
                      "export", "readonly", "let", "unset"}
SELF_ENV = ("self:env", CAP)
# A program named on PATH with plain arguments (vim, less -R, ssh -i key): no path, no shell punctuation, no `!`.
BARE_PROGRAM = re.compile(r"[A-Za-z0-9._+-]+(?:\s+[^;|&$`<>(){}!\\'\"\n]*)?")
OUT_OPS = {">", ">>", ">|", "&>", "&>>", ">&", "<>"}
REDIR_OPS = OUT_OPS | {"<", "<<", "<<-", "<<<", "<&"}
WRITERS = {"tee", "cp", "mv", "install", "ln", "rsync", "touch", "truncate", "rm", "chmod", "chown", "shred",
           "mkdir", "rmdir"}
REMOVERS = {"rm", "rmdir", "mv", "chmod", "chown", "shred", "rsync", "truncate"}   # can take a whole folder away
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


class Tok(str):
    """A word that was (partly) written between single quotes: ``masked`` is the same text with the shell's special
    characters of the quoted parts replaced by LITERAL, so that a quoted `$D` or `*` is never read as a variable or a
    glob, and an unquoted one elsewhere on the line still is. Quoting belongs to each word, not to its text."""
    masked: str

    def __new__(cls, text: str, masked: str):
        t = super().__new__(cls, text)
        t.masked = masked
        return t


LITERAL = "\x01"
QUOTED_META = set("$`*?[]{}~")


def _mask_single_quotes(text: str) -> str:
    """``text`` with the special characters inside single quotes replaced by LITERAL (same length)."""
    out, state, i = [], "", 0
    while i < len(text):
        ch = text[i]
        if state == "'":
            out.append(LITERAL if ch in QUOTED_META else ch)
            if ch == "'":
                state = ""
        elif ch == "\\" and i + 1 < len(text):
            out.append(text[i:i + 2])
            i += 2
            continue
        else:
            out.append(ch)
            if ch == '"':
                state = "" if state == '"' else '"'
            elif ch == "'" and state != '"':
                state = "'"
        i += 1
    return "".join(out)


def _shlex(text: str) -> list[str]:
    lex = shlex.shlex(text, posix=True, punctuation_chars=PUNCT)
    lex.whitespace_split = True
    lex.whitespace = " \t\r"                         # an unquoted newline is a separator, not a blank
    lex.commenters = ""                              # a comment is read as code: the safe side
    return list(lex)


def _lex(text: str) -> list[str]:
    text = FD_PREFIX.sub(" ", text)
    words = _shlex(text)
    if "'" not in text:
        return words
    try:
        masked = _shlex(_mask_single_quotes(text))
    except ValueError:
        return words
    if len(masked) != len(words) or any(len(a) != len(b) for a, b in zip(words, masked)):
        return words
    return [Tok(w, m) if m != w else w for w, m in zip(words, masked)]


def _view(word: str) -> str:
    """The word as the shell reads its special characters: quoted ones masked."""
    return word.masked if isinstance(word, Tok) else word


def _cut(word: str, start: int, end: int | None = None) -> str:
    """A slice of a word that keeps its quoting."""
    piece = str.__getitem__(word, slice(start, end))
    return Tok(piece, word.masked[start:end]) if isinstance(word, Tok) else piece


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


SHELLS = {"bash", "sh", "zsh", "dash", "ksh", "fish", "ash", "mksh", "csh", "tcsh", "nu", "elvish", "xonsh"}
INTERPRETERS = {"python", "python2", "python3", "node", "deno", "bun", "perl", "ruby", "php", "osascript", "pwsh",
                "powershell", "Rscript", "lua", "tclsh", "ipython", "pypy", "pypy3", "irb", "luajit", "julia", "R",
                "swift", "guile", "racket", "sbcl", "elixir", "erl", "ocaml", "ghci", "groovy", "jshell", "nodejs"}
INLINE_FLAGS = {"-c", "-e", "-r", "-Command", "--command", "--eval", "-p", "--print"}
RUNNERS = {"npm", "pnpm", "yarn", "bun"}
MAKES = {"make", "gmake", "just", "task"}
GIT_VALUE_OPTS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--config-env",
                  "--attr-source", "--super-prefix"}
# Long options of git that name a program, a configuration, a template or a file it writes: an abbreviation of one
# of them (git accepts any unique prefix) is read as the option itself.
GIT_LONG_OPTS = ("--upload-pack", "--receive-pack", "--exec-path", "--exec", "--config-env", "--config", "--template",
                 "--output-directory", "--output", "--open-files-in-pager", "--edit", "--file", "--git-dir",
                 "--work-tree", "--namespace", "--attr-source", "--super-prefix", "--prefix", "--extcmd")


def _canon_long(args: list[str], names: tuple[str, ...]) -> list[str]:
    """``args`` with each long option that abbreviates one of ``names`` (at least two letters after the dashes)
    written in full, its `=value` kept."""
    out = []
    for a in args:
        if a.startswith("--") and len(a) > 3:
            name, eq, value = a.partition("=")
            if name not in names and len(name) >= 4:
                full = min((f for f in names if f.startswith(name)), key=len, default=None)
                if full:
                    a = full + eq + value
        out.append(a)
    return out


def _sub_at(args: list[str], value_opts: set[str]) -> int:
    """Position of the subcommand: the first word that is neither an option nor the value of one."""
    n = 0
    while n < len(args):
        if args[n] in value_opts:
            n += 2
        elif args[n].startswith("-"):
            n += 1
        else:
            return n
    return len(args)
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
            a.startswith("--comp") for a in args) or any(
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
        return bool(_opt_values(args, "o", ("--log-file",)) or _opt_values(args, "O", ("--LOG-FILE",))
                    or _opt_values(args, "k", ("--lesskey-file", "--lesskey-src", "--lesskey-content"))
                    or any(a.startswith(("--lesskey", "--log", "--LOG", "+")) for a in args))
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


def _sed_script(text: str, brackets: bool, files: list | None = None) -> tuple[bool, bool] | None:
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
            if c in "wW" and files is not None:
                files.append(text[i:end].strip())
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
                    if files is not None:
                        files.append(text[i + 1:eol(i + 1)].strip())
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


def _sed_files(args: list[str]) -> list[str]:
    """The files a sed script writes: the name after the w or W command and after the w flag of s (`w file`,
    `wfile`, `s/a/b/wfile`), over every way a sed may read the call."""
    files: list[str] = []
    for gnu in (True, False):
        reading = _sed_reading(args, gnu)
        for text in (reading[0] if reading else []):
            for brackets in ((True, False) if gnu else (True,)):
                _sed_script(text, brackets, files)
    return [f for f in dict.fromkeys(files) if f]


def _tar_creates(args: list[str]) -> bool:
    """tar writes its archive (create, append, update), rather than reading one."""
    first = args[0] if args and not args[0].startswith("-") else ""
    return bool(set(first) & set("cruA")) or any(
        a in ("--create", "--append", "--update", "--catenate", "--concatenate")
        or (re.fullmatch(r"-[A-Za-z]+.*", a) and not a.startswith("--") and set(re.match(r"-[A-Za-z]+", a).group(0)) & set("cruA"))
        for a in args)


def _write_args(prog: str, args: list[str]) -> list[str]:
    """Paths a write-capable command is given. A value may be glued to the last letter of a group of short options
    (`-xCdir`, `-cffile`, `-odDIR`, `-rtDIR`, `-sdDIR`, `-qfFILE`): ``_opt_values`` reads it there."""
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
    if prog in SEDS and _sed_call(args)[0]:
        return [a for a in args if not a.startswith("-")] + _sed_files(args)   # in place: every word may be the file
    if prog in ("tar", "gtar", "bsdtar"):
        out = _opt_values(args, "C", ("--directory",))
        if _tar_creates(args):
            out += _opt_values(args, "f", ("--file",))       # the archive it writes
            if args and not args[0].startswith("-") and "f" in args[0]:
                out += args[1:2]                             # tar cf FILE
        return out
    if prog == "unzip":
        return _opt_values(args, "d", ())
    if prog == "patch":
        return (_positionals(args)[:1] + _opt_values(args, "o", ("--output",))
                + _opt_values(args, "d", ("--directory",)))
    if prog == "ssh-keygen":
        return _opt_values(args, "f", ())
    if prog in ("cp", "gcp", "mv", "ln", "install"):
        return [a for a in args if not a.startswith("-")] + _opt_values(args, "t", ("--target-directory",))
    if prog in ("ed", "ex", "red", "script"):
        return _positionals(args)[:1]
    if prog in ("iconv", "base64", "shuf", "gpg", "gpg2"):
        return _opt_values(args, "o", ("--output",))
    if prog == "openssl":
        return [v for k, v in zip(args, args[1:]) if k == "-out"]
    if prog in ("split", "csplit"):
        return _positionals(args)[1:]
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
MAX_COMMAND = 64 * 1024                                  # a command this long or longer is not lexed: complex


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
    if "{}" in inner and not _seg_pure(clause) and RANK[r[1]] < RANK[HIGH]:
        r = (r[0], HIGH)                                 # R37: what a found path is cannot be read here
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
    hit = _find_home(args, cwd, home) if prog in FINDS and FIND_WRITES & set(args) else None
    return (hit, CAP) if hit else _runner(own, inners)


FIND_NAMES = {"-name", "-iname", "-path", "-ipath", "-wholename", "-iwholename", "-regex", "-iregex"}
TENURE_FILES = ("plugin-data/tenure/tenure.db", "plugin-data/tenure/passport-ed25519.pem",
                   "plugin-data/tenure/undo/0/manifest.json")
HERMES_FILES = ("config.yaml", ".env", "auth.json", "state.db", "plugins/tenure/__init__.py")


def _find_home(args: list[str], cwd, home: str) -> str | None:
    """A find that deletes or runs something, from a starting point inside, at or above a Hermes home (or one that
    cannot be resolved), and whose name tests may select tenure's data or Hermes' files (no test, a regex, or a
    pattern that matches them): self:tenure or file:sensitive."""
    starts = []
    for a in args:
        if a.startswith("-") or a in ("(", "!", ","):
            if a in ("-H", "-L", "-P") and not starts:
                continue
            break
        starts.append(a)
    base = "/" if cwd == UNKNOWN else cwd
    reach = False
    for a in starts or ["."]:
        a = _expand(a, home)
        if _computed(a) or (cwd == UNKNOWN and not os.path.isabs(a)):
            reach = True
            break
        full = _abs(a, base, home)
        if _above_home(full) or _above_home(_real(full)) or _self_hit(full.casefold()) or _self_hit(_real(full).casefold()):
            reach = True
            break
    if not reach:
        return None
    pats = [(args[n], args[n + 1]) for n in range(len(args) - 1) if args[n] in FIND_NAMES]

    def selects(files: tuple[str, ...]) -> bool:
        if not pats:
            return True
        for test, pat in pats:
            if "regex" in test:
                return True                              # a regex: not read here, assume it may
            fold = test.startswith("-i")
            for f in files:
                name = f"/h/.hermes/{f}" if "path" in test or "wholename" in test else f.rsplit("/", 1)[-1]
                if fnmatch.fnmatchcase(name.lower() if fold else name, pat.lower() if fold else pat):
                    return True
        return False
    if selects(TENURE_FILES):
        return "self:tenure"
    return "file:sensitive" if selects(HERMES_FILES) else None


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


OUTPUT_OPTS = {
    "curl": ("oDc", ("--output", "--output-dir", "--dump-header", "--cookie-jar", "--trace", "--trace-ascii",
                     "--stderr", "--libcurl", "--etag-save", "--hsts", "--alt-svc")),
    "wget": ("OoaP", ("--output-document", "--output-file", "--append-output", "--directory-prefix",
                      "--save-cookies", "--warc-file", "--rejected-log", "--hsts-file")),
    "sort": ("o", ("--output",)),
    "less": ("oO", ("--log-file", "--LOG-FILE")),
}


def _tool_outputs(tokens: list[str]) -> list[str]:
    """Files curl, wget, sort or less write through an option, long options abbreviated or not, short ones alone,
    grouped (`-fsSLo f`) or with the value attached; for wget -P, also the folder with each URL's file name."""
    toks = _unwrap(tokens)
    if not toks or os.path.basename(toks[0]) not in OUTPUT_OPTS:
        return []
    prog = os.path.basename(toks[0])
    shorts, longs = OUTPUT_OPTS[prog]
    args = _canon_long(toks[1:], longs)
    out, n = [], 0
    while n < len(args):
        a = args[n]
        name, eq, value = a.partition("=")
        if name in longs:
            if eq:
                out.append(value)
            elif n + 1 < len(args):
                out.append(args[n + 1])
        elif a.startswith("-") and not a.startswith("--") and len(a) > 1:
            for k, ch in enumerate(a[1:], 1):
                if ch in shorts:
                    out.append(a[k + 1:] or (args[n + 1] if n + 1 < len(args) else ""))
        if "%output{" in a:
            out += re.findall(r"%output\{([^}]*)\}", a)
        n += 1
    if prog == "wget":
        dirs = [v for k, v in zip(args, args[1:]) if k in ("-P", "--directory-prefix")]
        dirs += [a.split("=", 1)[1] for a in args if a.startswith("--directory-prefix=")]
        dirs += [a.split("P", 1)[1] for a in args if re.match(r"-[A-Za-z]*P.", a) and not a.startswith("--")]
        urls = [a for a in args if not a.startswith("-") and "." in a]
        out += [d.rstrip("/") + "/" + u.rstrip("/").rsplit("/", 1)[-1] for d in dirs for u in urls]
    return out


def _fetcher_risky(tokens: list[str], home: str) -> tuple[str, str] | None:
    """curl reading a config file (-K), wget running its own commands (-e) or an askpass program, or either one
    saving into the home folder itself: where the files land, or what runs, is not on the command line."""
    toks = _unwrap(tokens)
    if not toks or os.path.basename(toks[0]) not in ("curl", "wget"):
        return None
    prog, args = os.path.basename(toks[0]), toks[1:]
    if prog == "curl" and any(a in ("-K", "--config") or a.startswith(("--config=", "-K")) for a in args):
        return "shell:curl:config", HIGH
    if prog == "wget" and any(a in ("-e", "--execute") or a.startswith(("--execute", "--use-askpass", "-e"))
                              for a in args):
        return "shell:wget:execute", HIGH
    h = (home or os.path.expanduser("~")).rstrip("/")
    for d in _tool_outputs(tokens):
        if _expand(d, home).rstrip("/") in (h, "~"):
            return f"shell:{prog}", HIGH                     # saved into the home folder, under a name it picks
    if prog == "wget" and any(re.match(r"-[A-Za-z]*P", a) or a.startswith("--directory-prefix") for a in args) \
            and any(a in ("-r", "--recursive", "-m", "--mirror", "-i") or re.match(r"-[A-Za-z]*[rmi]", a)
                    for a in args):
        return "shell:wget", HIGH                            # many files, names the server picks
    return None


def _shell_segment(tokens: list[str], cwd, home, depth: int = 0) -> tuple[str, str]:
    """One command (``_segment_main``); a segment that sets a code-hijacking variable is capped as self:env unless
    it is already capped under a more precise type (Hermes' own CLI, a protected file)."""
    r = _segment_main(tokens, cwd, home, depth)
    if r[1] == CAP:
        return r
    for target in _tool_outputs(tokens):
        f = _file(_expand(target, home), None if cwd == UNKNOWN else cwd, home)
        if f[1] == CAP:
            return f[0], CAP                                 # a protected file written through an option
    risky = _fetcher_risky(tokens, home)
    if risky and RANK[r[1]] < RANK[HIGH]:
        r = risky
    h = _hijacks(tokens)
    if h == CAP:
        return SELF_ENV
    return ("shell:env", HIGH) if h == HIGH and RANK[r[1]] < RANK[HIGH] else r


def _segment_main(tokens: list[str], cwd, home, depth: int = 0) -> tuple[str, str]:
    """One command. A sensitive path it writes (redirect or argument) caps it; a write target that cannot be
    resolved (variable, glob, brace, or a relative path while the working directory is unknown) is file:unknown.
    R36: a `cd`, `pushd` or `env -C` to a Hermes level or entry, or to a target that cannot be resolved, is capped
    even alone; `env -C dir` runs its command in dir; a command that writes while the working directory is unknown,
    or that unpacks an archive into the user's home, is at least high stakes."""
    known = {"HOME": _norm(home)}
    if cwd != UNKNOWN:
        known["PWD"] = cwd.rstrip("/") or "/"
    tokens = _substitute(tokens, known)
    cd, chdir = _cd_kind(tokens), _env_chdir(tokens)
    target = chdir if chdir is not None else (cd[1][0] if cd and cd[0] != "popd" and cd[1] else None)
    if target is not None:
        if _substituted(tokens):
            return ("self:tenure", CAP) if _names_hermes(" ".join(tokens), cwd, home) else ("file:unknown", HIGH)
        hit = _chdir_hit(target, cwd, home)
        if hit:
            return hit
    if chdir is not None:
        cwd = _move((cwd, None), "cd", [chdir], home)[0]
    floor = None
    if not cd and not _seg_pure(tokens):
        floor = _unresolved_floor(tokens, cwd, home)
        if floor and floor[1] == CAP:
            return floor
    tree = _tree_above_home(tokens, cwd, home)
    if tree and tree[1] == CAP:
        return tree
    if floor is None and tree:
        floor = tree
    if floor is None and ((cwd == UNKNOWN and not cd and not _seg_pure(tokens))
                          or _into_user_home(tokens, cwd, home) or _absolute_members(_unwrap(tokens))):
        floor = ("file:unknown", HIGH)
    unresolved = False
    base = "/" if cwd == UNKNOWN else cwd
    targets = _redirects(tokens)
    toks = _unwrap(tokens)
    if toks:
        targets += _write_args(os.path.basename(toks[0]), toks[1:])
    removes = bool(toks) and os.path.basename(toks[0]) in REMOVERS
    gone: list[str] = []                                     # what the command takes away: rm's, mv's sources
    if toks and os.path.basename(toks[0]) in ("rm", "rmdir", "shred", "mv"):
        gone = [a for a in toks[1:] if not a.startswith("-")]
        if os.path.basename(toks[0]) == "mv" and len(gone) > 1 and not _opt_values(toks[1:], "t", ("--target-directory",)):
            gone = gone[:-1]
    for target in targets:
        expanded = _expand(target, home)
        view = _view(target) if expanded is target else expanded     # quoted characters are literal
        target = expanded
        if any(c in view for c in UNRESOLVED) or (cwd == UNKNOWN and not os.path.isabs(target)):
            unresolved = True
            continue
        found = _file(target, base, home)
        if found[1] == CAP:
            return found[0], CAP
        full = _abs(target, base, home)
        if removes and (_above_home(full) or _above_home(_real(full))):
            return "file:sensitive", CAP
        if any(target is g or target == _expand(g, home) for g in gone) and _holds_hermes(full):
            return SELF_HERMES                               # the folder that holds the program or its package
    own = _core(tokens, cwd, home, depth)
    principle = _r35(tokens, cwd, home, reads=own[1] == FREE and not _redirects(tokens))
    if principle:
        return principle
    if unresolved:
        return "file:unknown", HIGH
    if own[1] == FREE and any(not HARMLESS_VARS.fullmatch(n) for n in _assigned(tokens)):
        own = (own[0], MEDIUM)                               # a read-only command, under an environment it chose
    return floor if floor and RANK[floor[1]] > RANK[own[1]] else own


def _env_chdir(tokens: list[str]) -> str | None:
    """The folder `env -C dir` / `env --chdir=dir` runs its command in (behind other wrappers too), else None."""
    toks = _unwrap(tokens, wrappers=False)
    while toks and os.path.basename(toks[0]) in WRAPPERS | {"timeout"}:
        wrapper, toks = os.path.basename(toks[0]), toks[1:]
        value_opts = WRAPPER_VALUE_OPTS.get(wrapper, set())
        while toks and (toks[0].startswith("-") or ENV_ASSIGN.match(toks[0])):
            t = toks[0]
            if wrapper == "env":
                if t in ("-C", "--chdir") and len(toks) > 1:
                    return toks[1]
                if t.startswith("--chdir="):
                    return t.split("=", 1)[1]
                glued = re.fullmatch(r"-[i0v]*C(.*)", t)
                if glued and (glued.group(1) or len(toks) > 1):
                    return glued.group(1) or toks[1]
            takes_value = t in value_opts or (len(t) > 2 and t[1] != "-" and "-" + t[-1] in value_opts)
            toks = toks[2:] if takes_value and len(toks) > 1 else toks[1:]
        if wrapper == "timeout" and toks:
            toks = toks[1:]
    return None


STDIN_CODE = ("shell:stdin-code", HIGH)
# A program named by a path in the system's own folders is that program; any other path is a file someone wrote.
SYSTEM_PROGRAM = re.compile(r"^/(?:usr/(?:local/)?)?s?bin/[^/]+$|^/opt/homebrew/bin/[^/]+$|^/opt/local/bin/[^/]+$")
VERSION_FLAGS = {"--version", "-V", "-v", "--help", "-h", "-version"}


def _stdin_code(args: list[str], script: str) -> bool:
    """A shell or interpreter that reads its program from standard input (`| sh`, `| python3`, `bash -s`, `sh -`):
    what runs is whatever came down the pipe (audit 10/11). A version or help query is not."""
    if args and set(args) <= VERSION_FLAGS:
        return False
    if "-" in args or any(re.fullmatch(r"-[A-Za-z]*s[A-Za-z]*", a) for a in args if not a.startswith("--")):
        return True
    if script in ("/dev/stdin", "/dev/fd/0", "/proc/self/fd/0"):
        return True
    return not script


# Programs whose arguments are files, never a command to run: a file named `hermes` given to them is a file.
FILE_PROGS = {"tee", "cp", "mv", "install", "ln", "rsync", "touch", "truncate", "rm", "chmod", "chown", "shred",
              "mkdir", "rmdir", "tar", "gtar", "bsdtar", "unzip", "zip", "ditto", "gcp"}
SUBCOMMAND = re.compile(r"-.*|[a-z][a-z0-9_-]*")
HERMES_ONLY_SUBS = {"plugins", "tenure", "gateway", "profile", "profiles", "approvals", "skills", "hooks"}


# The hermes-agent distribution, as a package manager names it (`hermes-agent`, `hermes_agent`, a wheel, a checkout).
HERMES_DIST = re.compile(r"(?<![A-Za-z0-9])hermes[-_.]+agent(?![A-Za-z0-9])", re.I)
PACKAGE_SOURCE = re.compile(r"^(?:[a-z][a-z0-9+.-]*\+|[a-z][a-z0-9+.-]*://|file:|\.{0,2}/|~)|\s@\s|@\s*[a-z][a-z0-9+.-]*:"
                            r"|\.(?:whl|zip|tar\.gz|tgz|tar\.bz2|egg)$", re.I)
PYPI = re.compile(r"^https://(?:[\w.-]+\.)?(?:pypi\.org|pythonhosted\.org)(?:/|$)", re.I)
INDEX_OPTS = {"-i", "--index-url", "--extra-index-url", "-f", "--find-links", "--index", "--default-index"}
REINSTALL_OPTS = {"--force-reinstall", "--reinstall", "--ignore-installed", "-I", "--force", "-f"}


def _dist_named(word: str) -> bool:
    """A requirement that names the hermes-agent distribution: `hermes-agent`, `hermes_agent[all]==1.0`."""
    m = re.match(r"[A-Za-z0-9][A-Za-z0-9._-]*", word.strip("'\" "))
    return bool(m) and re.sub(r"[-_.]+", "-", m.group(0)).casefold() == "hermes-agent"


def _package_install(args: list[str], force_opts: set) -> bool:
    """An install that replaces Hermes with something else than a release from PyPI: its distribution named with a
    forced reinstall, with another index, or taken from a source that is not PyPI (git+, a URL, a local path, a
    wheel). `install -U hermes-agent` and `install hermes-agent==1.2` from PyPI are ordinary."""
    named = forced = other_index = False
    for n, a in enumerate(args):
        name, eq, value = a.partition("=")
        if a in force_opts or a.startswith("--reinstall-package"):
            forced = True
        elif name in INDEX_OPTS or a == "--no-index":
            url = value if eq else (args[n + 1] if n + 1 < len(args) else "")
            other_index = other_index or not PYPI.match(url)
        elif a.startswith("-"):
            continue
        elif PACKAGE_SOURCE.search(a):
            if HERMES_DIST.search(a) or os.path.basename(a.rstrip("/")).casefold() in HERMES_PROGS:
                return True                                  # Hermes taken from a checkout, a wheel, a URL
        elif _dist_named(a) and not (n and args[n - 1] in INDEX_OPTS):
            named = True
    return named and (forced or other_index)


def _hermes_package(prog: str, args: list[str]) -> bool:
    """A package manager told to remove or replace the hermes-agent distribution (pip, `python -m pip`, uv, pipx,
    brew): uninstall, a forced reinstall, or an install from a source that is not PyPI. Upgrading or installing a
    release from PyPI is an ordinary install."""
    words = [a for a in args if not a.startswith("-")]
    base = re.sub(r"\d+(\.\d+)*$", "", prog)
    if base == "pip" and words:
        after = args[args.index(words[0]) + 1:]
        if words[0] in ("uninstall", "remove"):
            return any(_dist_named(a) for a in after if not a.startswith("-"))
        return words[0] == "install" and _package_install(after, REINSTALL_OPTS - {"--force", "-f"})
    if prog == "uv" and len(words) > 1 and words[0] in ("pip", "tool"):
        after = args[args.index(words[1]) + 1:]
        if words[1] == "uninstall":
            return any(_dist_named(a) for a in after if not a.startswith("-")) or "--all" in after
        return words[1] in ("install", "sync", "upgrade") and _package_install(after, REINSTALL_OPTS - {"-f", "-I"})
    if prog == "pipx" and words:
        after = args[args.index(words[0]) + 1:]
        if words[0] in ("uninstall", "reinstall"):
            return any(_dist_named(a) for a in after if not a.startswith("-"))
        if words[0] in ("uninstall-all", "reinstall-all"):
            return True
        return words[0] in ("install", "upgrade", "inject") and _package_install(after, {"--force", "-f"})
    if prog == "brew" and words:
        names = [os.path.basename(w.rstrip("/")).casefold() for w in words[1:]]
        named = any(n in HERMES_PROGS or re.sub(r"\.rb$", "", n) in HERMES_PROGS for n in names)
        if words[0] in ("uninstall", "remove", "rm", "reinstall", "unlink"):
            return named
        return words[0] == "install" and named and any(PACKAGE_SOURCE.search(w) for w in words[1:])
    return False


def _hermes_inside(toks: list[str], cwd, home: str) -> bool:
    """Hermes' CLI started from any word of a command, whatever stands in front (caffeinate, arch, flock, the macOS
    form of script, a launcher nobody listed): a word whose base name is hermes, hermes-agent or hermes-acp is read
    as the start of an invocation, and what follows is judged by ``_hermes`` (its reads stay allowed); a word that
    holds `hermes_cli` runs Hermes' module. A file or a folder that is only named like the program is not one: a
    path must resolve to Hermes (or be a bin/hermes), and a bare name must be followed by an option or by a word
    shaped like a subcommand, in a command that does more than move files."""
    if not toks:
        return False
    prog = os.path.basename(toks[0])
    for n, word in enumerate(toks):
        low = word.casefold()
        if "hermes_cli" in low and not any(ch.isspace() for ch in low):
            return True                                      # a module to run or a file of the package, not prose
        if n == 0 or os.path.basename(low) not in HERMES_PROGS or _computed(word):
            continue
        rest = toks[n + 1:]
        if "/" in word:
            if not (HERMES_BIN.search(_norm(low)) or _hermes_program(word, cwd, home)):
                continue
        elif (prog in FILE_PROGS or not rest or not SUBCOMMAND.fullmatch(rest[0])
              or (prog == "git" and not {"bisect", "foreach"} & set(toks[1:n]))):
            continue                                         # a file, a folder, a branch named like the program
        if os.path.basename(low) != "hermes" or _hermes(rest, cwd, home) == SELF_HERMES:
            return True
    return False


def _may_be_hermes(word: str, args: list[str]) -> bool:
    """A program name the shell computes (`${H}ermes`, `herm?s`, `{hermes,x}`, `$(echo hermes)`, `$X plugins ...`)
    that can come out as Hermes: its literal part holds a piece of the name, a glob or a brace alternative matches
    it, or what follows is a subcommand only Hermes has."""
    view = _view(word)
    if not _computed(view):
        return False
    base = os.path.basename(view.rstrip("/"))
    if any(os.path.basename(alt) in HERMES_PROGS for alt in _braces(view)):
        return True
    if not re.search(r"[$`{]", base) and GLOB.search(base):
        return any(_part_may(p, base) for p in HERMES_PROGS)
    literal = re.sub(r"\$\{?[A-Za-z_][A-Za-z0-9_]*\}?|[$`(){}]", " ", base)
    if re.search(r"[$`]", view) and _hermes_hint(literal):
        return True
    return bool(args) and (args[0] in HERMES_ONLY_SUBS or any("tenure" in a.casefold() for a in args[:8]))


def _core(tokens: list[str], cwd, home, depth: int = 0) -> tuple[str, str]:
    """One command, plus what it runs from a string or another program it names (``_wrapped``)."""
    own = _core_main(tokens, cwd, home, depth)
    toks = _unwrap(tokens)
    if (own[1] != CAP and toks and (not _seg_pure(tokens) or _substituted(tokens)) and not _hermes_read(tokens)
            and (_hermes_inside(toks, cwd, home) or _may_be_hermes(toks[0], toks[1:]))
            # words echo or printf only print are text (piped into a shell: ``_hermes_floor``)
            and not (os.path.basename(toks[0]) in ("echo", "printf") and not _substituted(tokens))):
        return SELF_HERMES
    if (own[1] == FREE and toks and "/" in toks[0] and not SYSTEM_PROGRAM.match(_norm(toks[0]))
            and not own[0].startswith("shell:hermes:")):     # Hermes' own read-only CLI, found under that path
        own = (f"shell:exec:{os.path.basename(toks[0])}", MEDIUM)   # a project file named like a read (C1)
    if depth > MAX_DEPTH:
        return own
    inners = [_lit(r) for r in _wrapped(_unwrap(tokens), cwd, home, depth)]
    return _top([own] + inners) if inners else own


def _core_main(tokens: list[str], cwd, home, depth: int = 0) -> tuple[str, str]:
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
    prog = re.sub(r"[`$()'\"{}]", "", os.path.basename(toks[0])) or "unknown"   # a type name, no shell punctuation
    args = toks[1:]
    if prog not in HERMES_PROGS and _hermes_program(toks[0], cwd, home):
        return SELF_HERMES if substitution else _hermes(args, cwd, home)   # Hermes under another name
    if prog in HERMES_PROGS:
        return SELF_HERMES if substitution or prog != "hermes" else _hermes(args, cwd, home)
    if _hermes_package(prog, args):
        return SELF_HERMES                                   # the hermes-agent distribution removed or replaced
    if substitution:
        return f"shell:{prog}", HIGH
    if prog in ("eval", "source", "."):
        return "shell:eval", HIGH
    if prog in SHELLS:
        i = next((n for n, a in enumerate(args) if re.fullmatch(r"-[A-Za-z]*c[A-Za-z]*", a)), None)
        if i is not None:
            if i + 1 >= len(args):
                return STDIN_CODE                            # `xargs sh -c`: the code arrives as the argument
            inner = args[i + 1]
            t, st, _ = _shell(inner, cwd, home, depth + 1)
            return t, st
        script = next((a for a in args if not a.startswith("-")), "")
        if _stdin_code(args, script):
            return STDIN_CODE
        return (f"shell:{prog}:{os.path.basename(script)}" if script else f"shell:{prog}"), MEDIUM
    if prog == "xargs":
        rest = _xargs_rest(args)
        return _shell_segment(rest, cwd, home, depth + 1) if rest else ("shell:xargs", MEDIUM)
    base = re.sub(r"\d+(\.\d+)*$", "", prog)
    if prog in INTERPRETERS or base in INTERPRETERS:
        if INLINE_FLAGS & set(args) or _inline_cluster(args):
            text = " ".join(args)
            if _runs_hermes_code(text):
                return SELF_HERMES
            return _code_levels(text, cwd, home) or (f"shell:{prog}:inline", HIGH)
        if "-m" in args:
            i = args.index("-m")
            mod = args[i + 1] if i + 1 < len(args) else ""
            if mod == "hermes" or mod.startswith(("hermes_cli", "hermes.")):
                return SELF_HERMES                       # Hermes' own CLI, run as a module
            if mod == "pip" and _hermes_package("pip", args[i + 2:]):
                return SELF_HERMES
            return f"shell:{prog}:-m:{mod}", MEDIUM
        script = next((a for a in args if not a.startswith("-")), "")
        if _stdin_code(args, script):
            return STDIN_CODE
        if (os.path.basename(script) in HERMES_PROGS or "hermes_cli" in script
                or (script and "/" in script and _hermes_program(script, cwd, home))):
            return SELF_HERMES
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
        if (prog == "crontab" and args == ["-l"]) or (prog == "launchctl" and sub in ("list", "print", "blame")):
            return OUTSIDE[prog], FREE                       # a listing
        return OUTSIDE[prog], HIGH
    if prog in VIM_EDITORS:
        code = _vim_commands(args)
        if code is not None:
            inners = [_lit(_shell(c[1:], cwd, home, depth + 1)[:2]) for c in code if c.startswith("!")]
            return _top([(f"shell:{prog}:command", HIGH)] + inners)
    if prog == "git":
        args = _canon_long(args, GIT_LONG_OPTS)
        plain = _strip(args, GIT_VALUE_OPTS)
        sub = plain[0] if plain else ""
        if _git_config_runs_code(args, plain):
            return "file:sensitive", CAP                     # git configuration that runs a program (audit 10/11)
        for target in _git_outputs(args, sub):
            r = _file(_expand(target, home), None if cwd == UNKNOWN else cwd, home)
            if r[1] == CAP:
                return r[0], CAP                             # a file git writes is a protected one
        if sub == "push":
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
    if prog == "kubectl" and sub in ("port-forward", "proxy"):
        return f"shell:kubectl:{sub}", MEDIUM                # opens a local port
    if prog in ("docker", "podman") and sub in ("ps", "images", "logs", "inspect", "version", "info", "stats", "top",
                                                "history", "port", "diff") and not writes:
        return f"shell:{prog}:{sub}", FREE
    if prog == "kubectl":
        if any(a == "--kubeconfig" or a.startswith("--kubeconfig=") for a in args):
            plain = _strip(args, SUB_VALUE_OPTS | {"--kubeconfig"})
            sub = plain[0] if plain else ""
            return f"shell:kubectl:{sub}", HIGH if sub in KUBE_WRITE else MEDIUM   # its exec plugins run
        return f"shell:kubectl:{sub}", HIGH if sub in KUBE_WRITE else FREE
    if prog == "terraform":
        return f"shell:terraform:{sub}", HIGH if sub in ("apply", "destroy", "import") else MEDIUM
    if prog in CLOUD:
        return f"shell:{prog}:{sub}", FREE if _cloud_read(args) else HIGH
    if prog == "git":
        if sub == "grep" and any(a.startswith("--open-files-in-pager") or re.match(r"-[A-Za-z]*O", a)
                                 and not a.startswith("--") for a in args):
            return "shell:git:grep", MEDIUM                  # opens the matches with a program it names
        rest = plain[1:] if plain else []
        if not writes and ((sub == "config" and ((rest and rest[0] in ("get", "list") and len(rest) <= 2)
                                                 or (set(args) & GIT_CONFIG_READS
                                                     and len([w for w in rest if not w.startswith("-")]) <= 1)))
                           or (sub == "stash" and rest[:1] in (["list"], ["show"]))):
            return f"shell:git:{sub}", FREE                  # a read of the configuration, the stash list
        if not writes and not _ro_writes("git", args) and (sub in GIT_READ or (sub in ("branch", "tag", "remote") and len(args) <= 2
                                                and not any(a in ("-d", "-D", "--delete", "add", "remove", "rm",
                                                                  "set-url", "rename") for a in args))):
            return f"shell:git:{sub}", FREE
        return f"shell:git:{sub or 'unknown'}", MEDIUM
    if prog in READ_ONLY and not writes and not _ro_writes(prog, args):
        return f"shell:{prog}", FREE
    return f"shell:{prog}", MEDIUM


# Git configuration keys that cannot run a program: setting them is ordinary. Any other key may (core.fsmonitor,
# core.pager, diff.external, a textconv, a filter, an alias starting with `!`, core.hooksPath, include.path...).
GIT_SAFE_KEYS = re.compile(r"user\.(?:name|email|signingkey)|color\..+|core\.(?:quotepath|autocrlf|eol|filemode"
                           r"|ignorecase)|init\.defaultbranch|advice\..+|commit\.gpgsign|tag\.gpgsign|pull\.(?:rebase|ff)"
                           r"|push\.(?:default|autosetupremote)|merge\.ff|fetch\.prune|rebase\.autosquash"
                           r"|branch\.[^.]+\.(?:remote|merge|rebase)|safe\.directory|http\.sslverify|protocol\.version"
                           r"|core\.(?:longpaths|abbrev|excludesfile|precomposeunicode)|diff\.(?:noprefix|renames|algorithm)"
                           r"|merge\.conflictstyle|rerere\.enabled|log\.(?:showsignature|date|decorate)"
                           r"|remote\.[^.]+\.(?:url|pushurl|fetch)|commit\.template|status\.\w+|gc\.auto"
                           r"|credential\.username|http\.version|rebase\.autostash|commit\.verbose|diff\.colormoved"
                           r"|core\.whitespace|user\.useconfigonly|http\.postbuffer|url\..+\.insteadof"
                           r"|gpg\.format|lfs\.[^.]+|branch\.sort|tag\.sort|push\.followtags|fetch\.prunetags"
                           r"|rerere\.autoupdate|rebase\.updaterefs|column\.ui|core\.untrackedcache|submodule\.recurse"
                           r"|help\.autocorrect|http\.proxy|difftool\.prompt|mergetool\.(?:prompt|keepbackup)")
# Options of `git config` that take the next word as their value.
GIT_CONFIG_VALUE_OPTS = {"-f", "--file", "--blob", "--type", "--default", "--comment", "--value", "--url"}
# Options that make `git config` a read on their own; display options (-z, --show-origin...) do not.
GIT_CONFIG_READS = {"--get", "--get-all", "--get-regexp", "--get-urlmatch", "-l", "--list", "--get-color",
                    "--get-colorbool"}
# Subcommand options that name a program git starts (the transport helpers on either side of a fetch or a push).
# For fetch and pull, -u is --update-head-ok.
GIT_PROGRAM_OPTS = {"fetch": {"--upload-pack"}, "pull": {"--upload-pack"}, "clone": {"--upload-pack", "-u"},
                    "ls-remote": {"--upload-pack", "-u"}, "archive": {"--exec"},
                    "push": {"--receive-pack", "--exec"}, "send-pack": {"--receive-pack", "--exec"}}
# Keys whose value is a program: ordinary when that value names a known editor, pager or helper.
GIT_PROGRAM_KEYS = re.compile(r"core\.(?:editor|pager|sshcommand|fsmonitor)|sequence\.editor|pager\.\w+|diff\.tool|merge\.tool"
                              r"|credential\.helper|interactive\.difffilter|gpg\.program")
# Editors, pagers and helpers a setting may name, by name or by their path in a system folder, each with the only
# arguments it may take (an allow list: any other argument, a file name among them, refuses the value). Shells,
# interpreters and wrappers are not among them: a value that starts one runs whatever it is given.
_EDITOR = r"-w|--wait|-n|--new-window|-r|--reuse-window"
_VIM = r"-[fpOon]+|--nofork|\+\d*"
TOOL_ARGS = {
    "code": _EDITOR, "code-insiders": _EDITOR, "cursor": _EDITOR, "subl": r"-[wn]+|--wait|--new-window",
    "mate": r"-w|--wait", "zed": r"-w|--wait|-n|--new", "vim": _VIM, "nvim": _VIM, "vi": _VIM, "vimdiff": _VIM,
    "nvimdiff": _VIM, "emacs": r"-nw|-q|-Q|--no-window-system", "emacsclient": r"-t|-c|-nw|--tty|--create-frame",
    "less": r"-[A-JL-NP-Za-jl-np-z0-9#~]+|--quit-if-one-screen|--RAW-CONTROL-CHARS|--chop-long-lines|--no-init|--mouse"
            r"|--tabs=\d+|--ignore-case",
    "bat": r"-p+|--plain|--paging=\w+|--style=[\w,-]+|--color=\w+|--theme=[\w-]+|--decorations=\w+"
           r"|--language=[\w+-]+",
    "delta": r"--color-only|--side-by-side|-s|--dark|--light|--features=[\w,-]+|--navigate|-n|--line-numbers"
             r"|--paging=\w+|--hyperlinks",
    "cache": r"--timeout=\d+", "nano": r"-[lmi]+|--linenumbers",
}
for _name in ("hx", "micro", "kak", "more", "most", "cat", "diff-so-fancy", "true", ":", "meld", "kdiff3",
              "opendiff", "p4merge", "osxkeychain", "store", "manager", "manager-core", "libsecret", "gpg", "gpg2",
              "open", "xdg-open", "wslview", "vscode", "bc", "bc3", "smerge", "gvimdiff", "firefox", "chromium", "google-chrome", "interactive-rebase-tool"):
    TOOL_ARGS[_name] = ""                                    # no arguments at all
KNOWN_TOOLS = set(TOOL_ARGS) | {"ssh"}
# ssh -o options that neither run nor load anything, nor write a file of the agent's choice.
SSH_SAFE_OPTIONS = {"identitiesonly", "stricthostkeychecking", "batchmode", "connecttimeout", "serveraliveinterval",
                    "serveralivecountmax", "port", "user", "loglevel", "passwordauthentication", "pubkeyauthentication",
                    "connectionattempts", "compression", "addressfamily", "hostkeyalias"}


def _ssh_args_safe(args: list[str]) -> bool:
    """ssh's arguments: -i a key (not one of Hermes' or tenure's own files), -p a port, -v, -q, -T, -4, -6,
    -F /dev/null, and -o options from SSH_SAFE_OPTIONS (UserKnownHostsFile only to /dev/null)."""
    n = 0
    while n < len(args):
        a = args[n]
        if re.fullmatch(r"-[vqT46]+", a):
            n += 1
            continue
        if a in ("-i", "-p", "-o", "-F"):
            if n + 1 >= len(args):
                return False
            a, n = a + args[n + 1], n + 2
        else:
            n += 1
        if a.startswith("-i") and len(a) > 2:
            low = a[2:].casefold()
            if _self_hit(low) or TENURE_NAMES.search(low) or "$" in low:
                return False
        elif a.startswith("-p") and a[2:].isdigit():
            pass
        elif a == "-F/dev/null":
            pass
        elif a.startswith("-o") and "=" in a:
            key, value = a[2:].split("=", 1)
            key = key.casefold()
            if not (key in SSH_SAFE_OPTIONS or (key == "userknownhostsfile" and value == "/dev/null")):
                return False
        else:
            return False
    return True


def _bare_program(value: str) -> bool:
    """``value`` starts a known editor, pager or helper (KNOWN_TOOLS, by name or from a system folder) with only the
    arguments its allow list names: no file name, no shell punctuation, no `!`."""
    value = value.strip().strip("'\"")
    if value in (":", "true", ""):
        return True
    if not BARE_PROGRAM.fullmatch(value.replace("/", "_")) or "!" in value:
        return False
    if re.search(r"\$\{?HERMES", value) or _self_hit(value.casefold()):
        return False                                         # the value names Hermes' own home
    first, *args = value.split()
    if "/" in first and os.path.dirname(first) not in SYSTEM_BIN_DIRS:
        return False
    name = os.path.basename(first)
    if name == "ssh":
        return _ssh_args_safe(args)
    allowed = TOOL_ARGS.get(name)
    if allowed is None:
        return False
    return all(allowed and re.fullmatch(allowed, a) for a in args)


ALIAS_RISKY_COMMANDS = {"push", "bundle", "merge-file", "mailinfo", "worktree", "send-pack", "fast-export",
                        "index-pack", "credential-store", "apply", "checkout-index", "clone", "ls-remote", "submodule", "bisect", "filter-branch", "difftool", "mergetool", "instaweb", "daemon",
                        "send-email", "web--browse", "config", "credential", "hook", "for-each-repo", "p4", "svn",
                        "archimport", "cvsimport", "cvsexportcommit", "quiltimport"}
ALIAS_OPTIONS = re.compile(r"--(?:oneline|graph|decorate|all|stat|short|cached|staged|amend|no-edit|abbrev-commit"
                           r"|no-merges|verbose|branch|soft|force-with-lease)?|-[sbvpam]+|-\d+")


def _alias_safe(value: str) -> bool:
    """An alias that names a git command with plain words and display options only: no `!`, no option that runs
    a program or writes a file, no command that runs one by design (submodule foreach, bisect run...)."""
    words = value.strip().strip("'\"").split()
    if not words or words[0].startswith("!") or words[0] in ALIAS_RISKY_COMMANDS:
        return False
    return all(re.fullmatch(r"[\w./:@^~{}-]+", w) and (not w.startswith("-") or ALIAS_OPTIONS.fullmatch(w))
               for w in words)


VIM_EDITORS = {"vim", "nvim", "vi", "ex", "view", "gvim", "vimdiff", "nvimdiff"}


def _vim_commands(args: list[str]) -> list[str] | None:
    """The editor commands a vim call runs (`+cmd`, `-c cmd`, `--cmd cmd`), or None without any; a script it
    sources or replays (`-S`, `-s`, `-u`) counts as a command."""
    out, found, n = [], False, 0
    while n < len(args):
        a = args[n]
        if a.startswith("+") and not re.fullmatch(r"\+\d*", a):
            out.append(a[1:])
            found = True
        elif a in ("-c", "--cmd", "-S", "-s", "-u", "-U") and n + 1 < len(args):
            out.append(args[n + 1] if a in ("-c", "--cmd") else "")
            found, n = True, n + 1
        elif a.startswith("-c") and len(a) > 2 and not a.startswith("--"):
            out.append(a[2:])
            found = True
        n += 1
    return out if found else None


def _git_outputs(args: list[str], sub: str) -> list[str]:
    """Files a git command writes through an option: --output, and -o for archive, format-patch and bundle."""
    out = []
    for n, a in enumerate(args):
        if a.startswith("--output="):
            out.append(a.split("=", 1)[1])
        elif (a == "--output" or (a == "-o" and sub in ("archive", "format-patch"))) and n + 1 < len(args):
            out.append(args[n + 1])
        elif a.startswith("-o") and len(a) > 2 and not a.startswith("--") and sub in ("archive", "format-patch"):
            out.append(a[2:])
        elif a in ("-f", "--file", "--output-directory", "--git-dir", "--work-tree") and n + 1 < len(args) \
                and (a not in ("-f", "--file") or sub == "config"):
            out.append(args[n + 1])
        elif a.startswith(("--output-directory=", "--git-dir=", "--work-tree=")) or (a.startswith("--file=") and sub == "config"):
            out.append(a.split("=", 1)[1])
    plain = _strip(args, GIT_VALUE_OPTS)
    if sub == "bundle" and len(plain) > 2 and plain[1] == "create":
        out.append(plain[2])
    if sub == "clone" and len(plain) > 2:
        out.append(plain[-1])
    if sub == "merge-file" and len(plain) > 1:
        out.append(plain[1])
    if sub == "mailinfo":
        out += plain[1:3]
    for a in args:
        if a.startswith(("--export-marks=", "--import-marks=")):
            out.append(a.split("=", 1)[1])
        elif sub == "config" and a.startswith("-f") and len(a) > 2:
            out.append(a[2:])
    if sub in ("index-pack", "credential-store"):
        out += [v for k, v in zip(args, args[1:]) if k in ("-o", "--file")]
    prefix = next((a.split("=", 1)[1] for a in args if a.startswith("--prefix=")), None)
    if prefix and sub != "archive":
        out += [prefix] + [prefix + w for w in plain[1:]]
    return out


def _git_key_safe(key: str, value) -> bool:
    key = key.casefold()
    if key.startswith("alias."):
        return value is not None and _alias_safe(value)
    if GIT_PROGRAM_KEYS.fullmatch(key):
        if key == "core.fsmonitor" and value is not None and value.strip().strip("'\"").casefold() in ("true", "false"):
            return True                                      # git's own monitor, or none
        if key == "credential.helper" and value is not None and value.strip().strip("'\"") == "":
            return True                                      # empties the list of helpers
        if (key.startswith("pager.") or key == "core.pager") and value is not None \
                and value.strip().strip("'\"").casefold() in ("", "true", "false"):
            return True                                      # a pager switched on or off
        return value is not None and _bare_program(value)
    return bool(GIT_SAFE_KEYS.fullmatch(key))


def _git_config_runs_code(args: list[str], plain: list[str]) -> bool:
    """A global `-c key=value`, `--config-env=key=VAR` or `--exec-path`, a `clone -c/--config`, a `--template`
    (it installs hooks), with a key that may run a program; or a `git config` that sets such a key or opens the
    editor on the file."""
    sub = plain[0] if plain else ""
    at = _sub_at(args, GIT_VALUE_OPTS)
    i = 0
    while i < len(args):
        a = args[i]
        value = None
        scoped = i < at or sub == "clone"
        if scoped and a in ("-c", "--config-env", "--config") and i + 1 < len(args):
            value, i = args[i + 1], i + 1
        elif scoped and a.startswith(("--config-env=", "--config=")):
            value = a.split("=", 1)[1]
        elif scoped and a.startswith("-c") and len(a) > 2 and not a.startswith("--"):
            value = a[2:]
        elif i < at and (a == "--exec-path" or a.startswith("--exec-path=")):
            return True
        elif sub in ("init", "clone") and (a == "--template" or a.startswith("--template=")):
            return True
        elif i > at and (a.split("=", 1)[0] in GIT_PROGRAM_OPTS.get(sub, ())
                         or a.split("=", 1)[0] in ("--upload-pack", "--receive-pack")
                         or (a.split("=", 1)[0] == "--exec" and sub != "rebase")):   # an alias of fetch or push
            return True                                      # the program run on the other end of the transport
        if value is not None:
            key, eq, val = value.partition("=")
            if not _git_key_safe(key, val if eq else None):
                return True
        i += 1
    if sub != "config":
        return False
    rest = plain[1:]
    tail = args[at + 1:] if at < len(args) else []
    if tail and tail[0] in ("get", "list", "set", "unset", "edit", "rename-section", "remove-section"):
        tail = tail[1:]
    n = 0
    while n < len(tail) and tail[n].startswith("-") and tail[n] != "--":
        n += 2 if tail[n] in GIT_CONFIG_VALUE_OPTS else 1
    words = tail[n + (1 if n < len(tail) and tail[n] == "--" else 0):]
    opts = {a.split("=", 1)[0] for a in tail[:n]} | {a.split("=", 1)[0] for a in args[:at] if a.startswith("-")}
    if opts & {"-e", "--edit"} or (rest and rest[0] == "edit"):
        return True
    if rest and rest[0] in ("set", "unset") and words[:1] != [rest[0]]:
        words = [rest[0]] + words
    if rest and rest[0] in ("get", "list") and len(words) <= 2:
        return False
    if opts & GIT_CONFIG_READS and len(words) <= 1:
        return False
    if words and words[0] in ("set", "unset"):
        words = words[1:]
    if opts & {"--unset", "--unset-all"} or (rest and rest[0] == "unset"):
        return False                                         # a setting taken away: git's default comes back
    writes = len(words) >= 2 or bool(opts & {"--add", "--replace-all", "--rename-section", "--remove-section"})
    return writes and bool(words) and not _git_key_safe(words[0], words[1] if len(words) > 1 else None)


# ------------------------------------------------------------------------------------------- Hermes' own CLI (C1)
HERMES_PROGS = {"hermes", "hermes-agent", "hermes-acp"}
SELF_HERMES = ("self:hermes", CAP)
# Code that calls Hermes' CLI or imports its modules: a quoted "hermes" program, hermes_cli.
# Code that imports Hermes' modules, or names the hermes program as the first item of an argv list.
HERMES_CODE = re.compile(r"\bhermes_(?:cli|constants)\b|['\"](?:[^'\"\s]*/)?hermes(?:-agent|-acp)?['\"]\s*[,\]]"
                         r"|which\(\s*['\"]hermes(?:-agent|-acp)?['\"]|/bin/hermes(?:-agent|-acp)?(?![\w.-])"
                         r"|runpy\.\w+\([^)]*hermes")
# Text that runs Hermes' CLI: the program followed by one of its subcommands that change things, or a lookup of the
# program (`$(which hermes)`). Checked in the raw text of any command that is not purely read-only.
HERMES_SUBS = ("config|plugins|tenure|profile|profiles|gateway|update|auth|setup|model|login|logout|uninstall|"
               "install|skills|hooks|cron|mcp|tools|memory|secrets|vault|approvals|security|backup|migrate")
# Between the program and its subcommand, Hermes' own options and their values (`hermes -p work config set`).
HERMES_RUN = re.compile(
    r"(?:^|(?<=[\s;&|(`'\"!{}=\\]))(?:[^\s;&|()`'\"=]*/)?hermes(?:-agent|-acp)?"
    r"(?:[\s'\"]+-[^\s'\"]+(?:[\s'\"]+(?!(?:" + HERMES_SUBS + r")\b)[^\s'\"-][^\s'\"]*)?){0,4}[\s'\"]+"
    r"(?:" + HERMES_SUBS + r")\b"
    r"|\b(?:which|whereis|whence|type\s+-[A-Za-z]+|command\s+-[vV])(?:\s+-[A-Za-z]+)*\s+['\"]?hermes\b")
# A shell name bound to the program: `h=hermes`, `alias h=hermes`.
HERMES_ALIAS = re.compile(r"=['\"]?(?:[^\s;&|'\"=]*/)?hermes(?:-agent|-acp)?(?=$|[\s;&|'\")])")


# Code that can start a program, and a string that is exactly the Hermes program (`h = "hermes"; run([h, ...])`).
CODE_STARTS = re.compile(r"subprocess|Popen|os\.system|os\.exec|os\.spawn|os\.popen|pty\.spawn|check_output|check_call"
                         r"|\bsystem\(|\bexec\w*\(|\bspawn\w*\(|child_process|\brun\(|\bcall\(|`")
HERMES_LITERAL = re.compile(r"(['\"])(?:[^'\"\s]*/)?hermes(?:-agent|-acp)?\1")


def _runs_hermes_code(code: str) -> bool:
    return bool(HERMES_CODE.search(code) or HERMES_RUN.search(code)
                or (HERMES_LITERAL.search(code) and CODE_STARTS.search(code)))


# Programs whose arguments carry a command string, or that run another program they name.
STRING_RUNNERS = {"script", "su", "tmux", "screen", "expect", "ssh"}
PROGRAM_RUNNERS = {"uvx": 0, "pipx": 1, "bunx": 0, "npx": 0, "uv": 1, "poetry": 1, "pdm": 1, "hatch": 1, "conda": 1,
                   "pnpm": 1, "yarn": 1, "rye": 1}           # how many words (a subcommand) come before the program
RUNNER_SUBS = {"run", "exec", "dlx", "x"}
RUNNER_VALUE_OPTS = {"--from", "--with", "-p", "--python", "--spec", "-w", "--package", "-n", "--name", "--env", "-e",
                     "--directory", "--project", "--extra", "--group"}
SSH_VALUE_OPTS = {"-p", "-i", "-l", "-o", "-F", "-J", "-L", "-R", "-D", "-b", "-c", "-E", "-e", "-m", "-O", "-Q", "-S",
                  "-W", "-w", "-B", "-I"}
GIT_COMMAND_KEYS = {"core.pager", "core.editor", "core.sshcommand", "core.fsmonitor", "core.askpass",
                    "sequence.editor", "diff.external", "credential.helper", "gpg.program", "ssh.variant"}


def _option_value(args: list[str], short: str, long: str) -> list[str]:
    """Values of -c / --command style options: `-c v`, `-qc v` (a cluster ending with the letter), `--command=v`."""
    out = []
    for n, a in enumerate(args):
        nxt = args[n + 1] if n + 1 < len(args) else ""
        if a == long or re.fullmatch(rf"-[A-Za-z]*{short}", a):
            out.append(nxt)
        elif a.startswith(long + "="):
            out.append(a.split("=", 1)[1])
    return [v for v in out if v]


def _wrapped(toks: list[str], cwd, home, depth: int) -> list[tuple[str, str]]:
    """What a command runs besides itself: the command string of script -c, su -c, tmux, screen, expect's spawn,
    ssh's remote command; the program uvx, uv run, pipx run, npx... run; git's command-valued -c settings."""
    if not toks:
        return []
    prog, args = os.path.basename(toks[0]), toks[1:]
    nxt = depth + 1
    out: list[tuple[str, str]] = []
    if prog in ("script", "su"):
        out += [_shell(v, cwd, home, nxt)[:2] for v in _option_value(args, "c", "--command")]
    elif prog in ("tmux", "screen"):
        pos = [a for a in args if not a.startswith("-")]
        out += [_shell(a, cwd, home, nxt)[:2] for a in pos[:16]]
        out += [_shell_segment(pos[i:], cwd, home, nxt) for i in range(min(len(pos), 8))]
    elif prog == "expect":
        for v in [a for a in args if not a.startswith("-")]:
            out.append(_shell(re.sub(r"(^|[;\n{\[])\s*spawn\s+(-\S+\s+)*", r"\1 ", v), cwd, home, nxt)[:2])
    elif prog == "ssh":
        rest, skip = [], False
        for n, a in enumerate(args):
            if skip:
                skip = False
            elif a in SSH_VALUE_OPTS:
                skip = True
            elif not a.startswith("-"):
                rest = args[n + 1:]
                break
        if rest:
            out.append(_shell(" ".join(rest), cwd, home, nxt)[:2])
    elif prog in PROGRAM_RUNNERS:
        words, n, skip = PROGRAM_RUNNERS[prog], 0, False
        rest = list(args)
        if words:
            plain = [a for a in rest if not a.startswith("-")]
            if not plain or plain[0] not in RUNNER_SUBS:
                return out
            rest = rest[rest.index(plain[0]) + 1:]
        for n, a in enumerate(rest):
            if skip:
                skip = False
            elif a in RUNNER_VALUE_OPTS:
                skip = True
            elif a == "--":
                continue
            elif not a.startswith("-"):
                out.append(_shell_segment(rest[n:], cwd, home, nxt))
                break
    elif prog == "git":
        for n, a in enumerate(args):
            if a != "-c" or n + 1 >= len(args) or "=" not in args[n + 1]:
                continue
            key, val = args[n + 1].split("=", 1)
            key = key.casefold()
            if key.startswith("alias.") and val.startswith("!"):
                out.append(_shell(val[1:], cwd, home, nxt)[:2])
            elif key in GIT_COMMAND_KEYS or key.startswith("pager."):
                out.append(_shell(val, cwd, home, nxt)[:2])
    return out


def _only_opts(args: list[str], flags: set[str], values: set[str]) -> bool:
    """Every word is one of ``flags``, or one of ``values`` with its value (next word, or after =)."""
    n = 0
    while n < len(args):
        a = args[n]
        name = a.split("=", 1)[0]
        if a in flags:
            n += 1
        elif name in values and "=" in a:
            n += 1
        elif a in values and n + 1 < len(args) and not args[n + 1].startswith("-"):
            n += 2
        else:
            return False
    return True


def _hermes(args: list[str], cwd, home) -> tuple[str, str]:
    """Hermes' CLI. Only invocations that read are not capped: ``--version``, ``status``, ``config get|show|path|
    env-path`` and ``tenure status|models|explain|verify|anchor`` (``export`` writes a file: a low or medium write,
    or a cap at a sensitive path). Every other subcommand, an unknown one, a flag we do not know, or a top-level
    flag before the subcommand is self:hermes: capped, and no override lowers it."""
    if args in (["--version"], ["-V"]):
        return "shell:hermes:version", FREE
    sub, rest = (args[0], args[1:]) if args else ("", [])
    if sub == "status" and _only_opts(rest, {"--full", "--all", "--deep"}, set()):
        return "shell:hermes:status", FREE
    if sub == "config" and (rest in (["show"], ["path"], ["env-path"]) or (
            len(rest) >= 2 and rest[0] == "get" and not rest[1].startswith("-")
            and _only_opts(rest[2:], {"--json"}, set()))):
        return "shell:hermes:config", FREE
    if sub != "tenure":
        return SELF_HERMES
    what, more = (rest[0], rest[1:]) if rest else ("status", [])
    if ((what == "status" and _only_opts(more, {"--all"}, {"--profile", "--model"}))
            or (what == "models" and _only_opts(more, set(), {"--type"}))
            or (what in ("explain", "anchor") and not more)
            or (what == "verify" and 1 <= len(more) <= 2 and not any(m.startswith("-") for m in more))):
        return "shell:hermes:tenure", FREE
    if what == "export" and len(more) <= 1 and not any(m.startswith("-") for m in more):
        if not more:
            return "shell:hermes:tenure:export", LOW       # into tenure's own folder
        target = _expand(more[0], home)
        if any(c in target for c in UNRESOLVED) or (cwd == UNKNOWN and not os.path.isabs(target)):
            return "file:unknown", HIGH
        t, stakes, _ = _file(target, "/" if cwd == UNKNOWN else cwd, home)
        if stakes == CAP:
            return t, CAP
        return "shell:hermes:tenure:export", stakes if RANK[stakes] > RANK[LOW] else LOW
    return SELF_HERMES


def _cd_kind(tokens: list[str]):
    toks = _unwrap(tokens)
    if toks and os.path.basename(toks[0]) in ("cd", "pushd", "popd"):
        return os.path.basename(toks[0]), [a for a in toks[1:] if a == "-" or not a.startswith("-")]
    return None


def _move(state: tuple, kind: str, args: list[str], home: str, physical: bool = True) -> tuple:
    """The (cwd, previous cwd) after a cd. A directory that cannot be worked out becomes UNKNOWN. ``physical``: a
    `..` after a link is applied to the link's target (`cd -P`), else to the text (the shell's default)."""
    cwd, old = state
    if kind == "popd":
        return UNKNOWN, cwd
    if not args:
        return (UNKNOWN, cwd) if kind == "pushd" else (_norm(home), cwd)
    d = args[0]
    if d == "-":
        return (old if old is not None else UNKNOWN), cwd
    d = _expand(_pwd(d, cwd), home)
    if d.startswith("~") or any(c in d for c in "$`*?[{"):
        return UNKNOWN, cwd
    if cwd == UNKNOWN and not os.path.isabs(d):
        return UNKNOWN, cwd
    return _abs(d, cwd, home, physical), cwd


SHELL_VAR = re.compile(r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))")
DECLARERS = {"export", "local", "declare", "readonly", "typeset"}


def _substitute(tokens: list[str], known: dict) -> list[str]:
    """The words with the variables assigned earlier on the line replaced by their value (never inside single
    quotes); a word keeps its quoting."""
    if not known:
        return tokens
    out = []
    for t in tokens:
        view, text, mask, last = _view(t), [], [], 0
        for m in SHELL_VAR.finditer(view):
            name = m.group(1) or m.group(2)
            if name not in known:
                continue
            text += [str.__getitem__(t, slice(last, m.start())), known[name]]
            mask += [view[last:m.start()], known[name]]
            last = m.end()
        if not text:
            out.append(t)
            continue
        text.append(str.__getitem__(t, slice(last, None)))
        mask.append(view[last:])
        new, masked = "".join(text), "".join(mask)
        out.append(Tok(new, masked) if masked != new else new)
    return out


def _assign(tokens: list[str], known: dict, home: str) -> None:
    """A segment that only assigns (`D=x`, `export D=x`): its values are kept for the rest of the line when they
    are plain (no other variable left, no substitution); `~` and $HOME expanded as the shell does."""
    toks = [t for t in tokens if t not in ("(", ")", "{", "}")]
    if toks and toks[0] in DECLARERS:
        toks = [t for t in toks[1:] if not t.startswith("-")]
    if not toks or not all(ENV_ASSIGN.match(t) for t in toks):
        return
    for t in toks:
        name, value = t.split("=", 1)
        value = _expand(_substitute([value], known)[0], home)
        if "$" in value or "`" in value:
            known.pop(name, None)
            if name == "CDPATH":
                known[name] = value
        else:
            known[name] = value


def _assigned(tokens: list[str]) -> list[str]:
    """The names a segment assigns: leading `NAME=value` words, those after a declarer (`export PATH=...`) and those
    given to env or another wrapper (`env PATH=bin ls`, `sudo PATH=x ls`). An argument such as `echo PATH=x` is
    not an assignment."""
    toks = [t for t in tokens if t not in ("(", ")", "{", "}")]
    names: list[str] = []
    if toks and toks[0] in DECLARERS:
        return [m.group(1) for t in toks[1:] if (m := ASSIGN_WORD.match(t))]
    i = 0
    while i < len(toks):
        m = ASSIGN_WORD.match(toks[i])
        if m:
            names.append(m.group(1))
            i += 1
            continue
        wrapper = os.path.basename(toks[i])
        if wrapper in WRAPPERS or wrapper == "timeout":
            i += 1
            values = WRAPPER_VALUE_OPTS.get(wrapper, set())
            while i < len(toks) and toks[i].startswith("-"):
                i += 2 if toks[i] in values and i + 1 < len(toks) else 1
            if wrapper == "timeout" and i < len(toks) and not ASSIGN_WORD.match(toks[i]):
                i += 1                                       # the duration
            continue
        break
    return names


# Variables whose value is a program to run: ordinary when it names a program found on PATH.
PROGRAM_VARS = re.compile(r"EDITOR|VISUAL|PAGER|MANPAGER|GIT_EDITOR|GIT_PAGER|GIT_SEQUENCE_EDITOR|GIT_SSH_COMMAND"
                          r"|BROWSER")
# Interpreter option variables load code only through these options.
LOADING_OPTIONS = re.compile(r"(?:^|\s)(?:--require|-r|--import|--loader|--experimental-loader|-javaagent|-agentpath"
                             r"|-agentlib|-XX:OnOutOfMemoryError|-XX:OnError)")
SYSTEM_BIN_DIRS = {"/usr/local/bin", "/usr/local/sbin", "/opt/homebrew/bin", "/opt/homebrew/sbin", "/usr/bin", "/bin",
                   "/usr/sbin", "/sbin", "/opt/local/bin"}


def _value_hijacks(name: str, value: str) -> str | None:
    """What this value of a listed variable does: None (ordinary), HIGH (asks: a folder of the user's own before
    the system on PATH), or CAP (the agent chooses the program). Ordinary values: PATH that puts only system
    folders or ~/.local/bin (whose writes are capped) before $PATH, or only system folders; an editor, pager, ssh
    or browser setting naming a known tool; LESS without `+` or `!`; NODE_OPTIONS or JAVA_TOOL_OPTIONS without an
    option that loads code."""
    value = value.strip().strip("'\"")
    if name == "PATH":
        home = (getattr(_CACHE, "home", None) or os.path.expanduser("~")).rstrip("/")
        parts = value.split(":")
        mark = next((n for n, x in enumerate(parts) if x in ("$PATH", "${PATH}")), len(parts))
        verdict = None
        for x in parts[:mark]:
            work = re.fullmatch(r"\$(?:PWD|\{PWD\})((?:/[\w.+-]+)+)", x)
            if work and not any(part in (".", "..") for part in work.group(1).split("/")):
                verdict = HIGH                               # a folder of the working tree, before the system
                continue
            full = _expand(x, home).rstrip("/")
            if full in SYSTEM_BIN_DIRS or full == home + "/.local/bin":
                continue
            if (not os.path.isabs(full) or any(ch in full for ch in "$`*?[")
                    or any(part in (".", "..") for part in full.split("/"))):
                return CAP                                   # a relative or computed folder
            verdict = HIGH                                   # a folder of the user's own, before the system
        return verdict
    if PROGRAM_VARS.fullmatch(name):
        return None if _bare_program(value) else CAP
    if name == "LESS":
        return None if all(re.fullmatch(TOOL_ARGS["less"], a) for a in value.split()) else CAP
    if name in ("NODE_OPTIONS", "JAVA_TOOL_OPTIONS", "_JAVA_OPTIONS"):
        return CAP if LOADING_OPTIONS.search(value) else None
    return CAP


def _env_split(tokens: list[str]) -> list[str] | None:
    """The words of `env -S 'string'` (also -S'string' and --split-string=), read as a command line, else None."""
    for n, t in enumerate(tokens):
        if os.path.basename(t) != "env":
            continue
        skip = False
        for m in range(n + 1, len(tokens)):
            a, value = tokens[m], None
            if skip:
                skip = False
                continue
            if a in ENV_VALUE_OPTS:
                skip = True
                continue
            if a in ("-S", "--split-string") and m + 1 < len(tokens):
                value = tokens[m + 1]
            elif a.startswith("--split-string="):
                value = a.split("=", 1)[1]
            elif a.startswith("-S") and len(a) > 2:
                value = a[2:]
            if value is not None:
                try:
                    return _shlex(value)
                except ValueError:
                    return [value]
            if not a.startswith("-"):
                break
    return None


ENV_VALUE_OPTS = {"-u", "--unset", "-C", "--chdir", "-P"}


def _hijacks(tokens: list[str]) -> str | None:
    """CAP when the segment sets a variable that makes the next programs run code of the agent's choosing (by
    assignment: prefix, behind env, `env -S`, a wrapper, after export; or by a builtin that assigns the variable it
    names: printf -v, read, mapfile, getopts, for, declare -n); HIGH when it puts a folder of the user's own before
    the system on PATH; else None. `PATH=$PATH:dir` keeps the system's programs first."""
    split = _env_split(tokens)
    worst = _hijacks(split) if split is not None else None
    if worst == CAP:
        return CAP
    toks = [t for t in tokens if t not in ("(", ")", "{", "}")]
    names = set(_assigned(tokens))
    for t in toks:
        m = ASSIGN_WORD.match(t)
        if m and m.group(1) in names and HIJACK_VARS.fullmatch(m.group(1)) and not APPENDED_PATH.match(t):
            v = _value_hijacks(m.group(1), t.split("=", 1)[1])
            if v == CAP:
                return CAP
            worst = worst or v
    if toks and os.path.basename(toks[0]) in ASSIGNING_BUILTINS:
        for t in toks[1:]:
            for word in (t, t.split("=", 1)[-1]):
                if not word.startswith("-") and HIJACK_VARS.fullmatch(word):
                    return CAP
    return worst


TILDE_DIR = re.compile(r"^~([+-])(?=/|$)")


def _tilde_dirs(tokens: list[str]) -> list[str]:
    """`~+` and `~-` at the start of a word are `$PWD` and `$OLDPWD`: written that way, they are read the same way
    (the working directory when it is known, the previous one once a `cd` on the line gave it)."""
    out = []
    for t in tokens:
        m = TILDE_DIR.match(_view(t))
        if not m:
            out.append(t)
            continue
        var = "$PWD" if m.group(1) == "+" else "$OLDPWD"
        rest = _cut(t, 2)
        new = var + str(rest)
        out.append(Tok(new, var + rest.masked) if isinstance(rest, Tok) else new)
    return out


def _run(segs: list[Seg], start: str, home: str, depth: int) -> tuple[str, str]:
    best, first = ("shell:unknown", MEDIUM), True
    states = [(start, None)]       # every (cwd, previous cwd) the shell may be in: a cd that may not stick adds one
    known: dict = {}               # variables assigned earlier on the line (R36)
    for n, seg in enumerate(segs):
        top = None
        tokens = _substitute(_tilde_dirs(seg.tokens), known)
        _assign(seg.tokens, known, home)
        seg = Seg(tokens, seg.sub, seg.cond, seg.sep)
        for cwd, old in states:
            here = seg.tokens
            if old is not None and old != UNKNOWN and "OLDPWD" not in known:
                here = _substitute(here, {"OLDPWD": old.rstrip("/") or "/"})
            r = _shell_segment(here, cwd, home, depth)
            if top is None or RANK[r[1]] > RANK[top[1]]:
                top = r
            fed = _xargs_feed(segs, n, here, cwd, home) if RANK[top[1]] < RANK[CAP] else None
            if fed:
                top = fed
        if any(t.startswith("CDPATH=") for t in seg.tokens) or (_cd_kind(seg.tokens) and "CDPATH" in known):
            top = ("self:tenure", CAP)                    # where the cd lands cannot be worked out
        if (first or RANK[top[1]] > RANK[best[1]]
                or (RANK[top[1]] == RANK[best[1]] and top[0] in FLOORS and best[0] not in FLOORS)):
            best, first = top, False
        cd = _cd_kind(seg.tokens)
        if cd:
            moved = [_move(st, cd[0], cd[1], home, physical) for st in states for physical in (True, False)]
            states = list(dict.fromkeys(states + moved if seg.sub or seg.cond else moved))
            if len(states) > 32:
                states = [(UNKNOWN, None)]
    return best


def _xargs_feed(segs: list[Seg], n: int, tokens: list[str], cwd, home: str) -> tuple[str, str] | None:
    """A pipeline that ends in an xargs (or parallel) whose command is not a pure read: the names it is given come
    from the commands before the pipe, so their arguments are judged as that command's own. `ls ~/.hermes | xargs
    rm`, `grep -rl x ~/.hermes | xargs sed -i ...`, `echo link | xargs rm` are capped like the same path given to
    rm; what a command prints from a file or computes is not read."""
    toks = _unwrap(tokens)
    if not toks or segs[n].sep not in PIPES or os.path.basename(toks[0]) not in ("xargs", "parallel"):
        return None
    inner = _xargs_rest(toks[1:]) if os.path.basename(toks[0]) == "xargs" else toks[1:]
    if not inner or _seg_pure(inner):
        return None
    base = "/" if cwd == UNKNOWN else cwd
    k = n
    while k > 0 and segs[k].sep in PIPES:
        k -= 1
        up = _substitute(_tilde_dirs(segs[k].tokens), {"HOME": _norm(home), **({} if cwd == UNKNOWN else {"PWD": base})})
        for word in _unwrap(up)[1:]:
            hit = _word_hit(word, base, cwd, home, text_tool=True)
            if hit:
                return hit
    return None


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
    home = getattr(_CACHE, "home", None) or os.path.expanduser("~")
    for cand in {word, word.split("=", 1)[-1], word.lstrip("@")}:
        low = cand.casefold().replace("\\", "/")
        if (any(f in low for f in SENSITIVE_FRAGMENTS) or any(d.casefold() in "/" + low + "/" for d in SENSITIVE_DIRS)
                or low.startswith(tuple(x.casefold() for x in SENSITIVE_PREFIXES))
                or SENSITIVE_NAME.match(low.rstrip("/").rsplit("/", 1)[-1])
                or GIT_CONFIG_FILES.search(low.rstrip("/"))
                or GIT_CONFIG_FILES.search(_norm(_expand(cand, home)).casefold().rstrip("/"))
                or _self_hit(low) or _self_hit(_norm(_expand(cand, home)).casefold())):
            return True
    return False


def _text_floor(text: str) -> str | None:
    """The protected type that a word or a piece of code names, or None: tenure's own data (self:tenure),
    else a sensitive file or a Hermes home (file:sensitive)."""
    if TENURE_NAMES.search(text.casefold().replace("\\", "/")):
        return "self:tenure"
    return "file:sensitive" if _frag(text) else None


def _seg_pure(seg_tokens: list[str]) -> bool:
    toks = _unwrap(seg_tokens)
    prog = os.path.basename(toks[0]) if toks else ""
    if prog in ("cd", "pushd", "popd") and not _redirects(seg_tokens):
        return True                                      # moves the shell, writes nothing (followed by _run)
    return not (prog not in READ_ONLY or _redirects(seg_tokens) or "<(" in seg_tokens or ">(" in seg_tokens
                or _ro_writes(prog, toks[1:]))


def _substituted(seg_tokens: list[str]) -> bool:
    """A command substitution: what runs is computed (`$(which x) args`)."""
    return any("`" in t or "$(" in t or (t == "$" and n + 1 < len(seg_tokens) and seg_tokens[n + 1] == "(")
               for n, t in enumerate(seg_tokens))


def _hermes_read(seg_tokens: list[str]) -> bool:
    """The segment is one of Hermes' read commands that _hermes leaves uncapped."""
    toks = _unwrap(seg_tokens)
    return (bool(toks) and os.path.basename(toks[0]) == "hermes" and not _substituted(seg_tokens)
            and _hermes(toks[1:], UNKNOWN, os.path.expanduser("~")) != SELF_HERMES)


def _launched_read(seg_tokens: list[str]) -> bool:
    """One of Hermes' read commands behind a launcher (`caffeinate hermes status`): every word named hermes starts
    an invocation that ``_hermes`` leaves uncapped."""
    toks = _unwrap(seg_tokens)
    at = [n for n, w in enumerate(toks) if n and os.path.basename(w) == "hermes"]
    return (bool(at) and not _substituted(seg_tokens) and os.path.basename(toks[0]) not in HERMES_PROGS
            and all("/" not in toks[n] and _hermes(toks[n + 1:], UNKNOWN, os.path.expanduser("~")) != SELF_HERMES
                    for n in at))


SEARCHERS = {"grep", "egrep", "fgrep", "rg", "ag", "ack"}
GIT_TEXT_OPTS = ("--grep", "--author", "--committer", "--message", "-S", "-G", "-m", "-e")
GH_TEXT_OPTS = ("--title", "-t", "--body", "-b", "--notes", "-n", "--message", "-m", "--subject", "--description", "-d",
                "--search", "-S")


def _prose(tokens: list[str], piped: bool) -> set:
    """Positions, in a segment's tokens, of the words that are text nobody runs: what echo or printf prints when it
    goes to the screen or to a file (not down a pipe), the pattern of a search (grep, rg, git grep, git log --grep,
    -S, -G), a message or a title (git commit -m, tag -m, gh --title, --body). A word that holds a substitution is
    never one: the shell runs it."""
    toks = _unwrap(tokens)
    if not toks or _substituted(tokens):
        return set()
    prog, at = os.path.basename(toks[0]), {id(t): n for n, t in enumerate(tokens)}
    args, out = toks[1:], []
    if prog in ("echo", "printf") and not piped:
        out = list(args)
    elif prog in SEARCHERS and not any(a.startswith("--pre") for a in args):
        out = [a for a in args if not a.startswith("-")][:1] + [v for k, v in zip(args, args[1:]) if k in ("-e", "--regexp")]
    elif prog in ("git", "gh"):
        opts = GIT_TEXT_OPTS if prog == "git" else GH_TEXT_OPTS
        out = [v for k, v in zip(args, args[1:]) if k in opts or re.fullmatch(r"-[A-Za-z]*m", k)]
        out += [a for a in args if a.startswith(tuple(o + "=" for o in opts if o.startswith("--")))]
        plain = _strip(args, GIT_VALUE_OPTS) if prog == "git" else []
        if plain[:1] == ["grep"]:
            out += [a for a in plain[1:2]]
    return {at[id(w)] for w in out if id(w) in at}


def _hermes_floor(command: str) -> bool:
    """Hermes' CLI run from text: in a line that is not purely read-only (Hermes' own reads count as read-only), the
    program with a subcommand that changes things, a lookup of the program, or a name bound to it. A mention in a
    string counts when the string may be run as a command; text that is only printed, searched for or sent as a
    message (``_prose``) is not a command. Where the grammar is not understood, the raw text is searched."""
    readings = [_build(tokens) for tokens in (_tokens_lines(command), _tokens_whole(command))]
    if all((_seg_pure(seg.tokens) and not _substituted(seg.tokens)) or _hermes_read(seg.tokens)
           or _launched_read(seg.tokens) for segs in readings for seg in segs):
        return False
    if _complex_floor(command):
        text = command
        for segs in readings:
            for seg in segs:
                toks = _unwrap(seg.tokens)
                if toks and os.path.basename(toks[0]) == "git":   # a commit message is text, not a command
                    text = functools.reduce(lambda t, v: t.replace(v, " "),
                                            _option_value(toks[1:], "m", "--message"), text)
        return bool(HERMES_RUN.search(text) or HERMES_ALIAS.search(text))
    for segs in readings:
        for n, seg in enumerate(segs):
            skip = _prose(seg.tokens, any(later.sep in PIPES for later in segs[n + 1:]))   # printed into a pipe
            text = " ".join(str(t) for k, t in enumerate(seg.tokens) if k not in skip)
            if HERMES_RUN.search(text) or HERMES_ALIAS.search(text):
                return True
    return False


def _validated_setting(word: str) -> bool:
    """`NAME=value` for a setting whose value was checked on its own (PATH of known folders, an editor, pager or ssh
    naming a known tool): its folders and key file are not write targets."""
    m = ASSIGN_WORD.match(word)
    if not m:
        return False
    name, value = m.group(1), word.split("=", 1)[1]
    if name == "PATH":
        return _value_hijacks("PATH", value) != CAP
    return bool(PROGRAM_VARS.fullmatch(name)) and _bare_program(value)


def _sensitive_floor(command: str) -> str | None:
    """A write target, or any argument of a command that is not purely read-only, names a sensitive file: the
    protected type (``_text_floor``), else None."""
    for tokens in (_tokens_lines(command), _tokens_whole(command)):
        pure, words = True, []
        for seg in _build(tokens):
            toks = _unwrap(seg.tokens)
            if not _seg_pure(seg.tokens):
                pure = False
            ws = list(seg.tokens)
            if toks and toks[0] in ws:
                ws.remove(toks[0])
            words += ws
        if not pure:
            words = [w for w in words if not _validated_setting(w)]
            found = {_text_floor(w) for w in words} - {None}
            if found:
                return "self:tenure" if "self:tenure" in found else "file:sensitive"
    return None


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
    (cap) and constructs outside the grammar (shell:complex, high). A command of MAX_COMMAND characters or more is
    not read at all."""
    if len(command or "") >= MAX_COMMAND:
        # Not lexed as a whole. It never gets less than its beginning read alone, and Hermes named in plain words
        # anywhere in it is capped; what a link or a computed name reaches beyond the limit is not seen: it asks.
        named = _plain_hermes(command)
        if named:
            return named[0], named[1], False
        low = command.casefold()
        if any(f in low for f in SENSITIVE_FRAGMENTS) or any(d.casefold() in low for d in SENSITIVE_DIRS):
            return "file:sensitive", CAP, False
        head = _shell(command[:MAX_COMMAND - 1], cwd, home, depth)
        return head if head[1] == CAP else ("shell:complex", HIGH, False)
    home = _norm(home or os.path.expanduser("~"))
    command = _join_lines(command)
    start = cwd or os.getcwd()
    by_lines = _run(_glue_find(_build(_tokens_lines(command))), start, home, depth)
    whole = _run(_glue_find(_build(_tokens_whole(command))), start, home, depth)
    best = whole if RANK[whole[1]] >= RANK[by_lines[1]] else by_lines
    if best[1] == CAP:
        return best[0], best[1], False
    floor = _sensitive_floor(command)
    if floor:
        return floor, CAP, False
    if _hermes_floor(command):
        return "self:hermes", CAP, False
    if _complex_floor(command):
        low = command.casefold()          # quotes cannot be trusted here: look at the raw text
        if TENURE_NAMES.search(low):
            return "self:tenure", CAP, False
        if (any(f in low for f in SENSITIVE_FRAGMENTS) or any(d.casefold() in low for d in SENSITIVE_DIRS)
                or _self_hit(low, anywhere=True)):
            return "file:sensitive", CAP, False
        return "shell:complex", HIGH, False
    return best[0], best[1], False                  # a command is never reversible by Tenure


# Programs that bring in content from another host (HTTP clients, text browsers, downloaders, raw sockets), and the
# git subcommands that bring in someone else's commits. Listed in the README.
EXTERNAL_PROGRAMS = frozenset({"curl", "wget", "http", "https", "xh", "xhs", "lynx", "w3m", "links", "aria2c", "nc",
                               "ncat"})
GIT_EXTERNAL = frozenset({"clone", "pull", "fetch"})


def _seg_reads_external(tokens: list[str], depth: int) -> bool:
    if depth > MAX_DEPTH:
        return False
    for n, t in enumerate(tokens):                      # <(curl x), $(curl x), "$(curl x)", `curl x`
        if t in ("<(", ">(", "(") and n + 1 < len(tokens) and os.path.basename(tokens[n + 1]) in EXTERNAL_PROGRAMS:
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
    if prog in EXTERNAL_PROGRAMS:
        return True
    if prog == "git":
        plain = _strip(args, GIT_VALUE_OPTS)
        return bool(plain) and plain[0] in GIT_EXTERNAL
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
                    "playwright", "puppeteer", "firecrawl", "crawl", "scrape", "github", "gitlab", "notion",
                    "linear", "jira", "confluence", "asana", "trello", "drive", "docs")
WHOLE_WORD_SERVERS = {"x", "exa"}                       # too short to match inside another name
HIGH_VERBS = {"send", "post", "publish", "email", "mail", "sms", "tweet", "message", "notify", "invite", "share", "pay",
              "payment", "payments", "purchase", "buy", "charge", "transfer", "refund", "order", "checkout", "invoice",
              "payout", "withdraw", "deposit", "broadcast", "reply", "comment", "dm", "forward", "respond", "text"}
MEDIUM_VERBS = {"create", "update", "add", "set", "put", "patch", "edit", "modify", "upsert", "insert", "save", "write",
                "delete", "remove", "archive", "move", "rename", "upload", "assign", "close", "complete", "merge",
                "approve", "schedule", "cancel", "enable", "disable", "tag", "label", "mark", "append", "clear"}
FREE_VERBS = {"get", "list", "search", "read", "fetch", "find", "query", "lookup", "describe", "show", "view", "count",
              "check", "status", "retrieve", "info", "inspect", "preview", "summarize"}
# Verbs that save something to disk: never free (audit 10/11: download_file, export_* wrote under ~/.hermes).
DISK_VERBS = {"download", "export", "save", "dump", "extract", "unpack", "unzip", "clone", "sync", "pull", "mirror",
              "backup", "restore", "import", "install", "store", "persist", "write", "cache", "record"}
# Argument names that say where something is written: a tool given one is never a free read.
DISK_ARGS = re.compile(r"(?:^|_)(?:dest|destination|output|out|save|saveto|download|local|target)(?:_|$)|save_?to",
                       re.I)


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
    if w & DISK_VERBS:
        return f"mcp:{server}:{tool}", HIGH if w & HIGH_VERBS else MEDIUM, False
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


CODE_PREFIX = re.compile(r"(?:^|[\s'\"`(=,\[])(?:" + "|".join(re.escape(x) for x in SENSITIVE_PREFIXES) + ")")


CODE_LITERAL = re.compile(r"""(['"])((?:\\.|(?!\1)[^\\\n])*)\1""")
CODE_HOME = re.compile(r"""expanduser|Path\.home|\bgetenv\(\s*['"]HOME|environ\s*\[\s*['"]HOME['"]|homedir\(|\$HOME|['"]~/?['"]""")


CODE_ENV_HOME = re.compile(r"""environ\s*(?:\[\s*|\.get\(\s*)['"]HERMES_HOME['"]|getenv\(\s*['"]HERMES_HOME['"]"""
                           r"""|\bENV\W{1,3}HERMES_HOME\b|process\.env\W{1,3}HERMES_HOME\b""")
CODE_WRITES = re.compile(r"""extractall|\bextract\(|unpack_archive|copytree|copyfile|\bcopy2?\(|\bmove\(|rename\w*[\s(]|"""
                         r"""\breplace\(|makedirs|mkdir|write_text|write_bytes|symlink|\blink\(|rmtree|remove\(|"""
                         r"""unlink|\bdelete\(|chdir|subprocess|os\.system|Popen|open\([^)]*['"][wax]""")


CODE_REMOVES = re.compile(r"rmtree|removedirs|\brmdir\(|\bmove\(|rename\w*\(|\breplace\(|\brm\b")
CODE_MOVES = re.compile(r"chdir|cwd\s*=|\bcd\b|pushd")       # code that changes where a relative path leads


def _code_levels(code: str, cwd, home: str) -> tuple[str, str] | None:
    """R35 for code (execute_code, python -c): a string literal that names a Hermes home level (expanduser's `~` and
    $HOME read as the shell reads them, a relative literal against the working directory), `$HERMES_HOME`, or a
    `.hermes` literal joined to the user's home: self:tenure, capped."""
    code = re.sub(r"'\s*\+\s*'|\"\s*\+\s*\"", "", code or "")      # 'a' + 'b' is 'ab'
    if CODE_ENV_HOME.search(code) and CODE_WRITES.search(code):
        return "self:tenure", CAP                     # R37: Hermes' home read from the environment, written to
    homeward = bool(CODE_HOME.search(code))
    writes = bool(CODE_WRITES.search(code))
    known = cwd is not None and cwd != UNKNOWN
    if (homeward or CODE_MOVES.search(code)) and _self_hit(_norm(code).casefold(), anywhere=True):
        return "file:sensitive", CAP                     # a relative `.hermes/...` in code that goes to the home
    unread: list = []
    strings = _code_strings(code, unread)
    if unread and unread[0] < len(code):
        # Beyond the literals that are read: Hermes named in plain words is capped (never less than the start alone).
        named = _plain_hermes(code[unread[0]:])
        if named:
            return named
    for lit, joined in strings:
        lit = lit.strip()
        if not lit or len(lit) > 4096 or "\n" in lit:
            continue
        if HERMES_VAR.fullmatch(lit):
            return "self:tenure", CAP
        if homeward and lit.strip("/") == ".hermes":
            return "self:tenure", CAP
        pieces = [lit]
        if any(ch.isspace() for ch in lit):              # a command line or a statement held in a string
            pieces = [x for x in STRING_PIECES.split(lit) if "/" in x or x.startswith(("~", ".."))][:32]
        for piece in pieces:
            cand = _expand(piece, home)
            if not os.path.isabs(cand) and not known:
                continue
            if re.search(r"[$`{]", cand) or (cand.startswith("~") and cand != "~"):
                continue
            if GLOB.search(cand):
                hit = _glob_hit(_abs(cand, cwd, home), home, named=False) if "/" in cand and writes else None
            else:
                full = _abs(cand, cwd, home)
                # a folder above a home counts in code that writes, for a path (never the lone `/` of a join or
                # a split, never a bare word)
                hit = _path_hit(full, home, above=writes and full != "/" and ("/" in piece or piece == ".."))
                if not hit and "/" in piece and CODE_REMOVES.search(code) and _holds_hermes(full):
                    hit = SELF_HERMES                        # the folder that holds the program or its package
            if hit and hit[1] == CAP:
                return hit
    return None


CODE_LITERALS = 512                                      # distinct string literals read in one piece of code
CODE_SCAN = 20000                                        # literals looked at to find them


def _code_strings(code: str, unread: list | None = None) -> list[tuple[str, bool]]:
    """The string literals of a piece of code, each as written and with its escapes decoded, then the literals that
    belong together read as one path: `'a' 'b'` and `'a' + 'b'` end to end, the arguments of one os.path.join and
    the parts of a pathlib `/` chain joined with a slash. (text, joined)."""
    lits, texts = [], set()
    for m in itertools.islice(CODE_LITERAL.finditer(code or ""), CODE_SCAN):
        lits.append((m.start(), m.end(), m.group(2)))
        texts.add(m.group(2))
        if len(texts) >= CODE_LITERALS:                      # distinct literals: a repeated one costs nothing
            break
    if unread is not None:
        unread.append(lits[-1][1] if lits and (len(texts) >= CODE_LITERALS or len(lits) >= CODE_SCAN) else len(code or ""))
    out: list[tuple[str, bool]] = []
    for text in dict.fromkeys(t for _, _, t in lits):
        out.append((text, False))
        if "\\" in text:
            try:
                decoded = text.encode("latin-1", "backslashreplace").decode("unicode_escape")
            except (UnicodeError, ValueError):
                decoded = text
            if decoded != text:
                out.append((decoded, False))
    run: list[str] = []
    for n, (start, end, text) in enumerate(lits):
        run = run or [text]
        gap = code[end:lits[n + 1][0]] if n + 1 < len(lits) else None
        nxt = lits[n + 1][2] if n + 1 < len(lits) else ""
        if gap is not None and len(run) < 16 and re.fullmatch(r"\s*\+?\s*", gap):
            run[-1] = run[-1] + nxt                          # 'a' 'b' and 'a' + 'b'
            out.append(("/".join(run), True))
        elif (gap is not None and len(run) < 16 and re.fullmatch(r"\s*\)?\s*[,/]\s*", gap)
              and not nxt.startswith(("/", "~"))):
            run = [x.rstrip("/") for x in run] + [nxt]       # os.path.join('a', 'b'), Path('a') / 'b'
            out.append(("/".join(run), True))
        else:
            run = []
    return list(dict.fromkeys(out))[:2048]


CODE_GIT_CONFIG = re.compile(r"\.git/(?:(?:modules|worktrees)/\S*?)?(?:config\b|hooks\b|commondir\b)|\.gitconfig\b"
                             r"|\.config/git/config\b")


def _code(code: str, cwd=None, home: str | None = None) -> tuple[str, str, bool]:
    """execute_code: the same floors as ``python -c``. Code that calls Hermes' CLI or imports its modules is
    self:hermes; code naming tenure's data is self:tenure; a sensitive file or a Hermes home, file:sensitive;
    a literal naming a Hermes home level (R36), self:tenure."""
    if _runs_hermes_code(code):
        return "self:hermes", CAP, False
    low = code.casefold().replace("\\\\", "/").replace("\\", "/")
    if TENURE_NAMES.search(low):
        return "self:tenure", CAP, False
    if (any(f in low for f in SENSITIVE_FRAGMENTS) or any(d.casefold() in low for d in SENSITIVE_DIRS)
            or _self_hit(low) or CODE_PREFIX.search(code) or CODE_GIT_CONFIG.search(low)):
        return "file:sensitive", CAP, False
    level = _code_levels(code, cwd, home or os.path.expanduser("~"))
    if level:
        return level[0], level[1], False
    return "code:execute", MEDIUM, False


def sensitive_path(path: str, cwd: str | None = None, home: str | None = None) -> bool:
    """A path classify caps as a write target (a sensitive file, a Hermes entry, tenure's data), judged from the
    session's ``cwd`` and user ``home``. For callers outside ``classify`` (undo checks a restore target with it)."""
    home = home or os.path.expanduser("~")
    _CACHE.memo, _CACHE.roots, _CACHE.cwd, _CACHE.home = {}, None, cwd, home
    try:
        return _file(path, cwd or os.getcwd(), home)[1] == CAP
    finally:
        _CACHE.memo = _CACHE.roots = None


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


def _strings(value, depth: int = 0, out: list | None = None) -> list:
    """Every string in a tool's arguments, keys and nested values included; a None marks nesting too deep to read."""
    out = [] if out is None else out
    if len(out) > 2000:
        return out
    if depth > 8:
        out.append(None)
        return out
    if isinstance(value, str):
        out.append(value)
    elif isinstance(value, dict):
        for k, v in value.items():
            if isinstance(k, str):
                out.append(k)
            _strings(v, depth + 1, out)
    elif isinstance(value, (list, tuple)):
        for v in value:
            _strings(v, depth + 1, out)
    return out


def _keys(value, depth: int = 0) -> list:
    if depth > 8:
        return []
    if isinstance(value, dict):
        return list(value) + [x for v in value.values() for x in _keys(v, depth + 1)]
    if isinstance(value, (list, tuple)):
        return [x for v in value for x in _keys(v, depth + 1)]
    return []


def _pairs(value, depth: int = 0) -> list:
    """Every (key, value) pair in nested arguments (bounded)."""
    if depth > 8:
        return []
    if isinstance(value, dict):
        return list(value.items()) + [x for v in value.values() for x in _pairs(v, depth + 1)]
    if isinstance(value, (list, tuple)):
        return [x for v in value for x in _pairs(v, depth + 1)]
    return []


def _saves_to_disk(args: dict) -> bool:
    """An argument that says where to write a file: a key such as output_path, save_to or dest whose value looks
    like a path (a folder separator, `~`, or a file extension). `output_format: md` is not one."""
    for k, v in _pairs(args):
        if (isinstance(k, str) and isinstance(v, str) and DISK_ARGS.search(k)
                and ("/" in v or v.startswith("~") or re.search(r"\.\w{1,6}$", v))):
            return True
    return False


REMOTE_PATH_KEYS = {"path", "paths", "file_path_in_repo", "repo_path"}   # a path inside the service's repository


REPOSITORY_SERVERS = {"github", "gitlab", "bitbucket"}


def _repository_path(server: str | None, args: dict, value) -> bool:
    """A `path` argument names a file inside a hosted repository: a repository service by its exact name, given an
    owner and a repository, and a relative value (never absolute, `~`, `$` or file:)."""
    if (server or "").casefold() not in REPOSITORY_SERVERS or not {"owner", "repo"} <= set(args):
        return False
    from urllib.parse import unquote
    values = [unquote(v) if isinstance(v, str) else v for v in (value if isinstance(value, list) else [value])]
    return all(isinstance(v, str) and not v.strip().startswith(("/", "~", "$", "\\")) and ":" not in v
               for v in values)


SCHEME_PATH = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*:(?=[/~.])")
# Arguments of Hermes' own tools that carry prose, not a place on disk: a note, a message, a prompt.
PROSE_KEYS = {"content", "text", "prompt", "goal", "message", "summary", "title", "body", "description", "query",
              "context", "instructions", "caption", "comment", "old_text", "new_text", "negative_prompt", "notes"}
# Hermes' own tools that act from their text: a goal handed to another agent, keys typed, code run, a job scheduled.
ACTING_TOOLS = {"delegate_task", "computer_use", "browser_exec", "browser_cdp", "cronjob_manage", "process_manage"}


def _runs_hermes_text(text: str) -> bool:
    """Free text that runs Hermes' CLI with a subcommand that changes things (a command line, a goal, typed keys)."""
    return bool(HERMES_RUN.search(text))


def _native_hit(tool_name: str, args: dict, cwd, home: str) -> tuple[str, str] | None:
    """One of Hermes' own tools (media, kanban, cron, delegation...) given a protected path, in `output_path` or any
    other argument: capped like the same path given to a plugin tool. Prose arguments (a note, a message, a prompt)
    are not read as paths, except for the tools that act from their text."""
    checked = args
    if tool_name not in ACTING_TOOLS:
        checked = {k: v for k, v in args.items() if not (isinstance(k, str) and k.casefold() in PROSE_KEYS)}
    hit = _args_hit(checked, cwd, home, reading=True, commands=tool_name in ACTING_TOOLS, anywhere=False)
    return hit if hit and hit[1] == CAP else None


# Words in the name of an MCP or plugin tool (or of its server) that say it runs something.
EXEC_WORDS = {"shell", "exec", "execute", "run", "bash", "sh", "zsh", "terminal", "command", "cmd", "docker", "podman",
              "spawn", "script", "eval", "ssh", "kubectl", "python", "repl", "sandbox"}
COMMAND_KEYS = ("command", "cmd", "program", "executable", "binary", "argv", "commandline", "command_line", "script",
                "shell", "run", "exec")
ARGS_KEYS = ("args", "argv", "arguments", "params", "parameters")
CWD_KEYS = ("cwd", "workdir", "working_dir", "working_directory", "workingdir", "directory", "dir")
CODE_KEYS = ("code", "source", "script", "python", "snippet")


def _exec_hit(args: dict, cwd, home: str) -> tuple[str, str] | None:
    """A tool that runs something, given its command: each command is classified like the same line in the
    terminal, whether it comes as one string, as a list (`cmd`, `args`, `argv`) or as a program and its arguments,
    in the folder the call names (`cwd`); code (`code`, `source`) like execute_code. Only a cap is taken from it."""
    low = {k.casefold(): v for k, v in args.items() if isinstance(k, str)}
    here = next((low[k] for k in CWD_KEYS if isinstance(low.get(k), str) and low[k].strip()), None)
    base = _abs(here, cwd, home) if here and not _computed(_expand(here, home)) else cwd
    words = lambda v: [str(x) for x in v] if isinstance(v, (list, tuple)) and all(
        isinstance(x, (str, int, float)) for x in v) else None
    lines: list[str] = []
    for v in args.values():
        if isinstance(v, str) and v.strip():
            lines.append(v)
        elif words(v):
            lines.append(shlex.join(words(v)))               # ["hermes", "plugins", "disable"]: the same command
    for ck in COMMAND_KEYS:
        head = low.get(ck)
        head = head if isinstance(head, str) else shlex.join(words(head)) if words(head) else None
        for ak in ARGS_KEYS:
            tail = low.get(ak)
            tail = tail if isinstance(tail, str) else shlex.join(words(tail)) if words(tail) else None
            if head and tail and ck != ak:
                lines.append(head + " " + tail)              # a program and its arguments, given apart
    for line in list(dict.fromkeys(lines))[:32]:
        r = _shell(line, base, home, 1)
        if r[1] == CAP:
            return r[0], CAP
    for k in CODE_KEYS:
        if isinstance(low.get(k), str):
            r = _code(low[k], base, home)
            if r[1] == CAP:
                return r[0], CAP
    return None


def _args_hit(args: dict, cwd, home: str, reading: bool = False, commands: bool = False,
              anywhere: bool = True) -> tuple[str, str] | None:
    """An MCP or other plugin tool whose arguments name tenure's data, a sensitive file, one of Hermes' own
    entries or a Hermes home level (audit 10/11): the tool name alone cannot say where it writes, so a protected
    path in the arguments caps it, percent-encoded, as a file:// URL, split into a folder and a name, or given as a
    key. Arguments nested too deep to read make it high stakes. Words without a path (a search query) are left
    alone."""
    from urllib.parse import unquote
    base = cwd if cwd and cwd != UNKNOWN else None
    deep = False
    for s in _strings(args):
        if s is None:
            deep = True
            continue
        for variant in dict.fromkeys((s, unquote(s), unquote(unquote(s)))):
            low = _norm(variant).casefold()
            if TENURE_NAMES.search(low):
                return "self:tenure", CAP
            if _self_hit(low, anywhere=anywhere):
                return "file:sensitive", CAP             # one of Hermes' own entries, under any .hermes folder
            if commands and _runs_hermes_text(variant):
                return SELF_HERMES                       # a command line, or keys to type, that runs Hermes' CLI
            words = [variant] + [w for w in re.split(r"[\s'\"`,;=()\[\]{}<>|]+", variant) if w and w != variant]
            words += [w.split(":", 1)[1] for w in words if SCHEME_PATH.match(w)]       # dir:/path, vscode:~/x
            words += [x for w in words if ":" in w and w.startswith(("/", "~", ".", "$")) and "://" not in w
                      for x in w.split(":") if x]                                       # a volume: /host:/inside
            for cand in words[:400]:
                if cand.startswith("file://"):
                    cand = cand[len("file://"):]
                    if cand and not cand.startswith("/") and "/" in cand:
                        cand = cand[cand.index("/"):]        # file://localhost/path: the host is not the path
                if len(cand) > 4096:
                    continue
                if not ("/" in cand or cand.startswith(("~", ".", "$"))):
                    if base and len(cand) < 256 and not _computed(cand):     # a bare name: a link in the folder?
                        hit = _path_hit(_abs(cand, base, home), home, above=False)
                        if hit:
                            return hit
                    continue
                if not _computed(cand) and (base or os.path.isabs(_expand(cand, home))):
                    hit = _path_hit(_abs(cand, base, home), home, above=False)
                    if hit:
                        return hit
                found = _file(cand, base, home)
                if found[1] == CAP:
                    return found[0], CAP
                full = _abs(cand, base, home)
                if _above_home(full) or _above_home(_real(full)):
                    if reading:
                        deep = True                      # listing a home: asked, not capped
                        continue
                    return "file:sensitive", CAP     # a whole Hermes home, or a folder above one
    return ("tool:unreadable-args", HIGH) if deep else None


def classify(tool_name: str, args: dict | None, *, cwd: str | None = None, overrides: dict | None = None,
             home: str | None = None) -> Action:
    args = args if isinstance(args, dict) else {}
    home = home or os.path.expanduser("~")
    _CACHE.memo, _CACHE.roots, _CACHE.cwd, _CACHE.home = {}, None, cwd, home
    if tool_name in FREE_TOOLS:
        t, stakes, rev = f"read:{tool_name}", FREE, False
    elif tool_name in ("write_file", "patch"):
        t, stakes, rev = _files(tool_name, args, cwd, home)
    elif tool_name == "terminal":
        t, stakes, rev = _shell(str(args.get("command", "")), cwd, home)
    elif tool_name == "execute_code":
        t, stakes, rev = _code(str(args.get("code") or ""), cwd, home)
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
    if (tool_name in TOOLS or tool_name.startswith("kanban_")) and tool_name != "execute_code" and stakes != CAP:
        hit = _native_hit(tool_name, args, cwd, home)
        if hit:
            t, stakes, rev = hit[0], CAP, False
    if t.startswith(("mcp:", "tool:")):
        split = _mcp_split(tool_name)
        name_words = _words(split[1]) if split else set()
        checked = args
        if split and not (name_words & (DISK_VERBS | {"upload", "attach", "send"})):
            checked = {k: v for k, v in args.items() if not (isinstance(k, str) and k.casefold() in REMOTE_PATH_KEYS
                                                             and _repository_path(split[0], args, v))}
        runs = bool((name_words | (_words(split[0]) if split else _words(tool_name))) & EXEC_WORDS)
        hit = _args_hit(checked, cwd, home,
                        reading=not runs and not (name_words & (HIGH_VERBS | MEDIUM_VERBS | DISK_VERBS | {
                            "delete", "remove", "move", "rename", "copy"})),
                        commands=not (split and _read_only_verbs(split[1])))
        if runs and not (hit and hit[1] == CAP):
            hit = _exec_hit(args, cwd or os.getcwd(), home) or hit
        if hit and hit[1] == CAP:
            t, stakes, rev = hit[0], CAP, False
        elif hit and RANK[stakes] < RANK[HIGH]:
            stakes = HIGH
        if stakes == FREE and _saves_to_disk(args):
            stakes = MEDIUM                              # a "read" told where to write
    stakes = _override(t, stakes, overrides)
    rev = rev and t == "file:write"                 # only a write inside the project can be undone
    return Action(type=t, stakes=stakes, reversible=rev, summary=_summary(tool_name, args, t))
