"""Proofs from execution: did the tool run cleanly, do written files still parse.

Hermes (model_tools.py `_tool_result_observer_fields`) passes status "ok" or
"error", error_type "tool_error" or an exception class name; the terminal
result is a JSON string with an `exit_code` key. A failed tool is neutral.
"""
from __future__ import annotations

import json
import os
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


# JSON files that tools read as JSON with comments (JSONC): tsconfig, jsconfig, VS Code and dev container settings.
_JSONC_NAMES = ("tsconfig", "jsconfig", "devcontainer", ".devcontainer", "settings", "launch", "tasks",
                "extensions", "keybindings", "deno", "biome", ".eslintrc", ".babelrc", "turbo", "nx", "project")


def _jsonc(path: str) -> bool:
    parts = os.path.normpath(path).replace("\\", "/").split("/")
    name = parts[-1].lower()
    return (name.endswith(".jsonc") or any(name == n + ".json" or name.startswith(n + ".") for n in _JSONC_NAMES)
            or ".vscode" in parts or ".devcontainer" in parts)


def _strip_jsonc(text: str) -> str:
    """JSON with ``//`` and ``/* */`` comments and trailing commas, as plain JSON (strings are kept as they are)."""
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c == '"':
            j = i + 1
            while j < n and text[j] != '"':
                j += 2 if text[j] == "\\" else 1
            out.append(text[i:j + 1])
            i = j + 1
        elif text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
        else:
            out.append(c)
            i += 1
    import re
    return re.sub(r",(\s*[}\]])", r"\1", "".join(out))


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
            json.loads(_strip_jsonc(text) if _jsonc(path) else text)
        else:
            tomllib.loads(raw.decode("utf-8-sig"))
    except (SyntaxError, ValueError, MemoryError, RecursionError):
        # UnicodeDecodeError and JSON/TOML decode errors are ValueErrors
        return {".py": "python syntax error", ".json": "json syntax error",
                ".toml": "toml syntax error"}[ext]
    return None


def broken(paths) -> frozenset:
    """The files among ``paths`` that already fail the check (before a call writes them): a file the agent did not
    break is never its fault."""
    return frozenset(p for p in paths or [] if _check_one(p))


def check_files(paths, broken_before=frozenset()):
    """The first reason a written file no longer parses, skipping the files that did not parse before the call."""
    for p in paths or []:
        if p in broken_before:
            continue
        reason = _check_one(p)
        if reason:
            return reason
    return None
