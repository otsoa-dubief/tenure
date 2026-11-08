# Copyright 2026 Otsoa Dubief
# SPDX-License-Identifier: Apache-2.0
"""What public benchmarks say about a model, per action type. Informs; never grants autonomy.

The numbers come from a snapshot bundled with the plugin (``data/benchmarks.json``, built offline by
``scripts/build_benchmarks.py`` from the Epoch AI Benchmarking Hub, CC BY 4.0). Nothing is fetched at runtime.
A model absent from the snapshot has "no public measure": the card says so and never vetoes.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

DATA_PATH = Path(__file__).parent / "data" / "benchmarks.json"
VETO_MARGIN = 5.0          # points; the snapshot stores every score as a percentage

TERMINAL, SWE, OSWORLD = "Terminal-Bench", "SWE-bench Verified", "OSWorld"
_NO_MEASURE = {"shell:git:push"}      # shell, but publishing code is not what a terminal benchmark measures
_cache: dict = {}


def normalise(model: str | None) -> str:
    """Comparable form of a model id: no provider prefix, no case, no date or variant suffix.

    ``openai/GPT-5.1-2025-11-13@openrouter`` -> ``gpt-5-1``. An id with a local tag (``qwen3:8b-q4_K_M``) is
    kept whole, "_" suffixes included: a quantisation is not the model that was measured.
    """
    m = (model or "").strip().lower().split("@", 1)[0].rsplit("/", 1)[-1]
    if ":" not in m:                      # a local id keeps everything after the colon, "_" included
        m = m.split("_", 1)[0]
    m = re.sub(r"[-.]?(20\d{2}-\d{2}-\d{2}|20\d{6})$", "", m)
    return m.replace(".", "-")


_EMPTY = {"source": "", "license": "", "url": "", "accessed": "", "benchmarks": {}, "models": {}}
_PUBLISHED = "best published score (any harness), not a controlled comparison"


def _checked(d) -> dict:
    if not isinstance(d, dict) or not isinstance(d["benchmarks"], dict) or not isinstance(d["models"], dict):
        raise ValueError("malformed snapshot")
    for e in d["models"].values():
        if not isinstance(e["scores"], dict) or not isinstance(e.get("aliases", []), list):
            raise ValueError("malformed snapshot")
    for k in ("source", "accessed"):
        if not isinstance(d[k], str):
            raise ValueError("malformed snapshot")
    return d


def load(path: Path | str | None = None) -> dict:
    """The snapshot; an empty one (no model, no benchmark) when the file is missing or unreadable."""
    p = Path(path) if path else DATA_PATH
    key = str(p)
    if key not in _cache:
        try:
            _cache[key] = _checked(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, ValueError, KeyError, TypeError):
            _cache[key] = {k: ({} if isinstance(v, dict) else v) for k, v in _EMPTY.items()}
    return _cache[key]


def lookup(model: str) -> dict | None:
    """The snapshot entry for a model id, or None when it has no public measure."""
    n = normalise(model)
    if not n:
        return None
    for mid, entry in load()["models"].items():
        if n == normalise(mid) or n in {normalise(a) for a in entry.get("aliases", [])}:
            return entry
    return None


def benchmark_for(type_key: str) -> str | None:
    """The public benchmark closest to an action type, if the snapshot has it."""
    if type_key in _NO_MEASURE:
        return None
    if type_key.startswith("shell:"):
        name = TERMINAL
    elif type_key.startswith("file:") or type_key == "code:execute":
        name = SWE
    elif type_key == "computer:use":
        name = OSWORLD
    else:
        return None
    return name if name in load()["benchmarks"] else None


def _score(model: str | None, bench: str) -> float | None:
    entry = lookup(model) if model else None
    return None if entry is None else entry["scores"].get(bench)


def card(old_model: str | None, new_model: str, type_key: str) -> dict:
    snap = load()
    bench = benchmark_for(type_key)
    out = {"benchmark": bench, "version": None, "source": snap["source"], "accessed": snap["accessed"],
           "old": None, "new": None, "delta": None, "note": ""}
    if bench is None:
        out["note"] = "No public measure for this action type."
        return out
    out["version"] = snap["benchmarks"][bench].get("version")
    out["old"], out["new"] = _score(old_model, bench), _score(new_model, bench)
    if out["new"] is None:
        out["note"] = f"No public measure for {new_model} on {bench}."
    elif out["old"] is None:
        out["note"] = (f"No public measure for {old_model} on {bench}." if old_model
                       else "No previous model to compare with.")
    else:
        out["delta"] = round(out["new"] - out["old"], 1)
        out["note"] = f"{bench} {out['version']}, percent. Public scores inform; they never grant autonomy."
    if out["old"] is not None or out["new"] is not None:
        out["note"] += f" Each score is the model's {_PUBLISHED}."
    return out


def veto(old_model: str, new_model: str, type_key: str, margin: float = VETO_MARGIN) -> bool:
    """True when the new model scores more than ``margin`` points under the old one on the type's benchmark.

    Both scores must exist on the same benchmark (one version per benchmark in a snapshot); otherwise no veto.
    """
    bench = benchmark_for(type_key)
    if bench is None:
        return False
    old, new = _score(old_model, bench), _score(new_model, bench)
    return old is not None and new is not None and old - new > margin
