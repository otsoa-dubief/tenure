#!/usr/bin/env python3
# Copyright 2026 Otsoa Dubief
# SPDX-License-Identifier: Apache-2.0
"""Build clearance/data/benchmarks.json from the Epoch AI Benchmarking Hub CSV bundle (CC BY 4.0).

This is the only place that touches the network, once per release, never at runtime.

    python3 scripts/build_benchmarks.py            # download, build
    python3 scripts/build_benchmarks.py DIR        # build from an already extracted bundle

Kept: Terminal-Bench (2.0), SWE-bench Verified, OSWorld; the other benchmarks of the plan (BFCL, tau2-bench) are
not in the bundle. Every score is a percentage. Where several runs exist for a model (agent harnesses, step
budgets, reasoning efforts) the best is kept, because the bundle does not hold one harness per model: the card
therefore compares best published results, not a controlled head-to-head.
"""
from __future__ import annotations

import csv
import datetime
import io
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from clearance.benchmarks import normalise  # noqa: E402

BUNDLE_URL = "https://epoch.ai/data/benchmark_data.zip"
PAGE_URL = "https://epoch.ai/benchmarks"
OUT = ROOT / "clearance" / "data" / "benchmarks.json"

# name -> (csv file, model column, score column, factor to percent, version)
SOURCES = {
    "Terminal-Bench": ("terminalbench_external.csv", "Model version", "Accuracy mean", 100.0, "2.0"),
    "SWE-bench Verified": ("swe_bench_verified.csv", "Model version", "mean_score", 100.0, "Verified"),
    "OSWorld": ("os_world_external.csv", "Model version", "Score", 1.0, "1"),
}


def fetch(dest: Path) -> None:
    req = urllib.request.Request(BUNDLE_URL, headers={"User-Agent": "Mozilla/5.0 (compatible; benchmark-snapshot-builder)"})
    with urllib.request.urlopen(req, timeout=120) as r, zipfile.ZipFile(io.BytesIO(r.read())) as z:
        z.extractall(dest)


def build(src: Path, accessed: str) -> dict:
    models: dict[str, dict] = {}
    for name, (fname, mcol, scol, factor, _v) in SOURCES.items():
        path = src / fname
        if not path.exists():
            continue
        for row in csv.DictReader(path.open(encoding="utf-8")):
            raw, val = (row.get(mcol) or "").strip(), (row.get(scol) or "").strip()
            key = normalise(raw)
            if not key or not val:
                continue
            e = models.setdefault(key, {"aliases": set(), "scores": {}})
            e["aliases"].add(raw)
            score = round(float(val) * factor, 2)
            e["scores"][name] = max(score, e["scores"].get(name, score))
    if not models:
        raise SystemExit("none of the wanted benchmarks is in the bundle: nothing written")
    kept = {n: {"version": v[4], "unit": "percent"} for n, v in SOURCES.items()
            if any(n in m["scores"] for m in models.values())}
    return {
        "source": "Epoch AI Benchmarking Hub",
        "license": "CC BY 4.0",
        "url": PAGE_URL,
        "accessed": accessed,
        "benchmarks": kept,
        "models": {k: {"aliases": sorted(m["aliases"] - {k}), "scores": dict(sorted(m["scores"].items()))}
                   for k, m in sorted(models.items())},
    }


def main(argv: list[str]) -> None:
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(argv[1]) if len(argv) > 1 else Path(tmp)
        if len(argv) <= 1:
            fetch(src)
        data = build(src, datetime.date.today().isoformat())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(data['models'])} models, benchmarks: {', '.join(data['benchmarks'])}")


if __name__ == "__main__":
    main(sys.argv)
