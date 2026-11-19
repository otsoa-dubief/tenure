"""Proofs from execution: did the tool run cleanly, do written files still parse.

Hermes (model_tools.py `_tool_result_observer_fields`) passes status "ok" or
"error", error_type "tool_error" or an exception class name; the terminal
result is a JSON string with an `exit_code` key. A failed tool is neutral.
"""
from __future__ import annotations

import json
import os
import re
import stat
import tomllib

_OK = {"ok", "success", "completed", None, ""}
_MAX_BYTES = 2 * 1024 * 1024


def _exit_code(result):
    data = result
    if isinstance(result, str):
        try:
            data = json.loads(result)
        except ValueError:
            return None
    if isinstance(data, dict):
        return data.get("exit_code")
    return None


def execution(tool_name, status, error_type, result) -> str:
    if error_type or status not in _OK:
        return "failed"
    if tool_name == "terminal":
        code = _exit_code(result)
        if isinstance(code, int) and not isinstance(code, bool) and code != 0:
            return "failed"
    return "ok"


def _read_regular(path: str):
    """The bytes of a regular file of at most _MAX_BYTES, else None. A FIFO, a device or a directory is never read:
    opening a FIFO would block the hook until a writer came. The open is non-blocking and the type is checked again
    on the open descriptor, so a file swapped for a FIFO after the first check cannot block either."""
    if not os.path.isfile(path):
        return None
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0))
    try:
        f = os.fdopen(fd, "rb")
    except BaseException:
        os.close(fd)
        raise
    with f:
        info = os.fstat(f.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > _MAX_BYTES:
            return None
        raw = f.read(_MAX_BYTES + 1)
    return None if len(raw) > _MAX_BYTES else raw


# JSON files that tools read as JSON with comments (JSONC). Anywhere: these names. In `.vscode/` and `.devcontainer/`:
# every JSON file. Never a generic name (`settings.json`, `tasks.json`) elsewhere: data files read by json.load.
_JSONC_ANYWHERE = ("tsconfig", "jsconfig", "devcontainer", ".devcontainer", "deno", "biome", ".eslintrc", ".babelrc",
                   "turbo")
_JSONC_DIRS = (".vscode", ".devcontainer")
_JSONC_TOKENS = re.compile(r'"(?:[^"\\]|\\.)*"|//[^\n]*|/\*.*?\*/|,(?=\s*[}\]])|[^"/,]+|[/,]', re.S)


def _jsonc(path: str) -> bool:
    parts = os.path.normpath(path).replace("\\", "/").split("/")
    name = parts[-1].lower()
    if name.endswith(".jsonc") or any(d in parts[:-1] for d in _JSONC_DIRS):
        return True
    stem = name[:-5] if name.endswith(".json") else name
    return any(stem == n or stem.startswith(n + ".") for n in _JSONC_ANYWHERE)


def _strip_jsonc(text: str) -> str:
    """JSON with ``//`` and ``/* */`` comments and trailing commas, as plain JSON: strings are kept as they are, a
    comment becomes a blank (``1/**/2`` stays two tokens), a comma before ``}`` or ``]`` outside a string goes."""
    out = []
    for m in _JSONC_TOKENS.finditer(text):
        t = m.group(0)
        if t.startswith("//") or t.startswith("/*"):
            out.append(" ")
        elif t == "," and text[m.end():].lstrip()[:1] in ("}", "]") and "".join(out).rstrip()[-1:] not in ("", "[", "{", ","):
            continue                                        # a trailing comma after a value; `[,]` stays an error
        else:
            out.append(t)
    return "".join(out)


def _check_one(path: str):
    ext = os.path.splitext(path)[1].lower()
    if ext not in (".py", ".json", ".toml"):
        return None
    try:
        raw = _read_regular(path)
    except OSError:
        return None
    if raw is None:
        return None
    try:
        if ext == ".py":
            compile(raw, "<written>", "exec", dont_inherit=True)
        elif ext == ".json":
            text = raw.decode("utf-8-sig")                  # a byte order mark is valid UTF-8 JSON on disk
            try:
                json.loads(text)
            except ValueError:
                if not _jsonc(path):
                    raise
                json.loads(_strip_jsonc(text))              # only when plain JSON fails: cheap in the usual case
        else:
            tomllib.loads(raw.decode("utf-8-sig"))
    except (SyntaxError, ValueError, MemoryError, RecursionError):
        # UnicodeDecodeError and JSON/TOML decode errors are ValueErrors
        return {".py": "python syntax error", ".json": "json syntax error",
                ".toml": "toml syntax error"}[ext]
    return None


def _real(path: str) -> str:
    try:
        return os.path.realpath(path)
    except (OSError, ValueError):
        return path


def broken(paths) -> frozenset:
    """The files among ``paths`` that already fail the check before a call writes them (real paths): a file the agent
    did not break is never its fault."""
    return frozenset(_real(p) for p in paths or [] if _check_one(p))


def check_files(paths, broken_before=frozenset()):
    """The first reason a written file no longer parses, skipping the files that did not parse before the call."""
    return judge_files(paths, broken_before)[0]


def judge_files(paths, broken_before=frozenset()) -> tuple[str | None, bool]:
    """(reason, unjudged): the first reason a file the call broke no longer parses; else ``unjudged`` is True when a
    file that was broken before is still broken: the call proved nothing, it is neither a fault nor a success."""
    unjudged = False
    for p in paths or []:
        reason = _check_one(p)
        if not reason:
            continue
        if _real(p) in broken_before:
            unjudged = True
            continue
        return reason, False
    return None, unjudged
