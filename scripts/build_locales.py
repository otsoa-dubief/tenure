#!/usr/bin/env python3
# Copyright 2026 Otsoa Dubief
# SPDX-License-Identifier: Apache-2.0
"""Embed the translation catalogs of the two JavaScript surfaces into their files.

The source of truth is ``tenure/locales/<lang>/<surface>.json``. The desktop plugin (one ``plugin.js`` copied by
Hermes) and the dashboard bundle cannot read files at runtime, so each carries its catalogs between the markers
``/* TENURE_LOCALES_BEGIN */`` and ``/* TENURE_LOCALES_END */``.

    python3 scripts/build_locales.py           # rewrite the blocks
    python3 scripts/build_locales.py --check   # exit 1 if a block is out of date (the test suite runs this)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCALES = ROOT / "tenure" / "locales"
TARGETS = {"desktop": ROOT / "tenure" / "desktop" / "plugin.js",
           "dashboard": ROOT / "tenure" / "dashboard" / "dist" / "index.js"}
BEGIN, END = "/* TENURE_LOCALES_BEGIN */", "/* TENURE_LOCALES_END */"


def catalogs(surface: str) -> dict:
    out = {}
    for d in sorted(p for p in LOCALES.iterdir() if p.is_dir()):
        f = d / f"{surface}.json"
        if f.exists():
            out[d.name] = json.loads(f.read_text(encoding="utf-8"))
    if "en" not in out:
        raise SystemExit(f"no English catalog for {surface}")
    return dict(sorted(out.items(), key=lambda kv: (kv[0] != "en", kv[0])))


def block(surface: str) -> str:
    cats = {lang: dict(sorted(cat.items())) for lang, cat in catalogs(surface).items()}   # English first, keys sorted
    body = json.dumps(cats, ensure_ascii=False, indent=2)
    return f"{BEGIN}\nconst TENURE_LOCALES = {body};\n{END}"


def rebuilt(surface: str) -> tuple[str, str]:
    path = TARGETS[surface]
    text = path.read_text(encoding="utf-8")
    i, j = text.find(BEGIN), text.find(END)
    if i < 0 or j < i:
        raise SystemExit(f"{path}: markers not found")
    return text, text[:i] + block(surface) + text[j + len(END):]


def main(argv: list[str]) -> int:
    check = "--check" in argv
    stale = []
    for surface, path in TARGETS.items():
        old, new = rebuilt(surface)
        if old != new:
            stale.append(str(path.relative_to(ROOT)))
            if not check:
                path.write_text(new, encoding="utf-8")
    if check and stale:
        print("out of date: " + ", ".join(stale) + " (run python3 scripts/build_locales.py)")
        return 1
    print("rebuilt: " + (", ".join(stale) or "nothing to do"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
