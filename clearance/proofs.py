"""Proofs from execution: did the tool run cleanly, do written files still parse.

Hermes (model_tools.py `_tool_result_observer_fields`) passes status "ok" or
"error", error_type "tool_error" or an exception class name; the terminal
result is a JSON string with an `exit_code` key. A failed tool is neutral.
"""
from __future__ import annotations

import json
import os
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


def _check_one(path: str):
    ext = os.path.splitext(path)[1].lower()
    if ext not in (".py", ".json", ".toml"):
        return None
    try:
        if os.path.getsize(path) > _MAX_BYTES:
            return None
        with open(path, "rb") as f:
            raw = f.read()
    except OSError:
        return None
    try:
        if ext == ".py":
            compile(raw, "<written>", "exec", dont_inherit=True)
        elif ext == ".json":
            json.loads(raw.decode("utf-8"))
        else:
            tomllib.loads(raw.decode("utf-8"))
    except (SyntaxError, ValueError, MemoryError, RecursionError):
        # UnicodeDecodeError and JSON/TOML decode errors are ValueErrors
        return {".py": "python syntax error", ".json": "json syntax error",
                ".toml": "toml syntax error"}[ext]
    return None


def check_files(paths):
    for p in paths or []:
        reason = _check_one(p)
        if reason:
            return reason
    return None
