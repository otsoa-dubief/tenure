#!/usr/bin/env python3
# Copyright 2026 Otsoa Dubief
# SPDX-License-Identifier: Apache-2.0
"""Build the community board from a folder of records written by ``hermes tenure share``.

    python3 scripts/aggregate_community.py DIR --out board.json

Every ``*.json`` in DIR (not recursive) is read and verified (shape, coarse families, Ed25519 signature); an invalid
record is reported and dropped. One record per public key counts, the latest. The board lists, per action family,
each model's contributors, verified successes and faults, and the Wilson 95% interval of its fault rate.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _community():
    """tenure.community, from this checkout."""
    sys.path.insert(0, str(ROOT))
    try:
        from tenure import community
    finally:
        sys.path.pop(0)
    return community


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("dir", help="folder of records (*.json)")
    ap.add_argument("--out", required=True, help="board file to write")
    ns = ap.parse_args(argv)
    community = _community()
    records = []
    for path in sorted(Path(ns.dir).glob("*.json")):
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            print(f"dropped {path.name}: not readable JSON ({e})")
            records.append(None)
            continue
        problems = community.verify_record(d)
        if problems:
            print(f"dropped {path.name}: " + "; ".join(problems))
        records.append(d)
    board = community.aggregate(records)
    Path(ns.out).write_text(json.dumps(board, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"board written: {ns.out} ({board['records']} records kept, {board['dropped']} dropped, "
          f"{len(board['families'])} families)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
