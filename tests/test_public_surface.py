# Copyright 2026 Otsoa Dubief
# SPDX-License-Identifier: Apache-2.0
"""Catalog review of f4a6285: tenure reaches Hermes only through public seams (the plugin context, the public
config reader, the plugin data folder), never through private modules or ``sys.modules`` reads."""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent / "tenure"
PRIVATE = ("tools.terminal_tool", "tools.approval", "agent.i18n", "hermes_cli.inventory",
           "hermes_cli.plugins_settings", "save_plugin_settings", "get_session_cwd", "get_current_session_key")


def sources():
    for path in ROOT.rglob("*.py"):
        if "__pycache__" not in path.parts:
            yield path, path.read_text(encoding="utf-8")


def test_no_private_hermes_module_is_named():
    found = [f"{p.relative_to(ROOT)}: {name}" for p, text in sources() for name in PRIVATE if name in text]
    assert found == []


def test_no_hermes_module_is_read_from_sys_modules():
    """Only tenure's own package (the dashboard and CLI find the loaded plugin) and Hermes' public
    ``hermes_constants`` are looked up there."""
    lookups = [(p, m.group(1)) for p, text in sources()
               for m in re.finditer(r"sys\.modules(?:\.get\(|\[)\s*([^)\]]+)", text)]
    assert lookups and all(arg in ("name", "__package__", '"tenure"', '"hermes_constants"') for _, arg in lookups), lookups
