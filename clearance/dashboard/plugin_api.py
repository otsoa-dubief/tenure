# Copyright 2026 Otsoa Dubief
# SPDX-License-Identifier: Apache-2.0
"""Dashboard API of clearance, mounted by Hermes at ``/api/plugins/clearance/``.

Every route sits under ``/api/``, so Hermes' dashboard auth middleware (session token, or the OAuth gate) covers it:
``/api/plugins/...`` is not in the public path list. This file adds no authentication of its own.

GETs open each profile's database read-only (``Store.open_readonly``), skip a profile that has none, run in a worker
thread (``asyncio.to_thread``) so the dashboard's event loop never waits on SQLite, and use ``LIMIT``ed queries. They
never write: not a row, not a file (the passport is unsigned when its key does not exist yet).

POSTs act on the dashboard's current profile only (the process's Hermes home; a ``?profile=`` naming another one is
refused) and go through the same functions as the hooks and the CLI, so the ledger gets the same input events.
"""
from __future__ import annotations

import asyncio
import contextlib
import importlib.util
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter()

TIMELINE_LIMIT = 200          # ledger events per agent in /timeline
UNDOABLE_LIMIT = 200          # undoable actions per profile in /activity
DAY = 24 * 3600
_FOLDER = ("plugin-data", "clearance")
_DB = "clearance.db"


def _core():
    """The plugin package as Hermes loaded it (the hooks' ``ST`` lives there), else imported from this file's place."""
    for name in ("hermes_plugins.clearance", "clearance"):
        mod = sys.modules.get(name)
        if mod is not None and hasattr(mod, "ST"):
            return mod
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("clearance", root / "__init__.py",
                                                  submodule_search_locations=[str(root)])
    mod = importlib.util.module_from_spec(spec)
    sys.modules["clearance"] = mod
    spec.loader.exec_module(mod)
    return mod


# ------------------------------------------------------------------------------------------------------ profiles
def _root() -> Path:
    """The machine's Hermes root: hermes_constants when importable, else HERMES_HOME (or its grandparent when it is
    ``<root>/profiles/<name>``), else ~/.hermes."""
    try:
        from hermes_constants import get_default_hermes_root
        return Path(get_default_hermes_root())
    except Exception:
        home = os.environ.get("HERMES_HOME") or os.path.join(os.path.expanduser("~"), ".hermes")
        p = Path(home)
        return p.parent.parent if p.parent.name == "profiles" else p


def _profiles() -> list[dict]:
    """The root as "default", then ``profiles/*``: [{name, home}]."""
    root = _root()
    out = [{"name": "default", "home": root}]
    try:
        names = sorted(e.name for e in (root / "profiles").iterdir() if e.is_dir() and not e.name.startswith("."))
    except OSError:
        names = []
    return out + [{"name": n, "home": root / "profiles" / n} for n in names]


def _current(core) -> str:
    """Name of the profile this process serves: the one whose home is the process's Hermes home."""
    home = os.path.realpath(core._hermes_home())
    for p in _profiles():
        if os.path.realpath(str(p["home"])) == home:
            return p["name"]
    return os.path.basename(home) or "default"


def _data_dir(p: dict) -> str:
    return os.path.join(str(p["home"]), *_FOLDER)


@contextlib.contextmanager
def _open(core, p: dict):
    """The profile's store, read-only; None when it has no usable database yet (nothing is created)."""
    path = os.path.join(_data_dir(p), _DB)
    try:
        st = core.store.Store.open_readonly(path)
    except (FileNotFoundError, RuntimeError, sqlite3.Error, OSError):
        yield None
        return
    try:
        yield st
    finally:
        st.db.close()


def _profile(name: str | None, core) -> dict:
    name = name or _current(core)
    for p in _profiles():
        if p["name"] == name:
            return p
    raise HTTPException(404, f"no such profile: {name}")


def _settings(core, st) -> dict:
    """The settings in force in a profile: those of the ledger's last settings event (what its tiers were computed
    under), else the default preset."""
    row = st.db.execute("SELECT event FROM ledger WHERE event LIKE '%\"event\":\"settings\"%' "
                        "ORDER BY seq DESC LIMIT 1").fetchone()
    params = core.params
    ev = json.loads(row[0]) if row else {}
    risks = dict(params.PRESETS[params.DEFAULT_PRESET])
    risks.update({k: v for k, v in (ev.get("risks") or {}).items() if k in params.LEVELS})
    spot = ev.get("spot")
    return {"preset": "custom" if row else params.DEFAULT_PRESET, "risks": risks,
            "spot": spot if isinstance(spot, (int, float)) and 0 < spot < 1 else params.DEFAULT_SPOT,
            "strict": bool(ev.get("strict")), "overrides": {}, "enabled": True}


def _type_row(core, cfg: dict, s) -> dict:
    rule, params = core.rule, core.params
    n = params.required_n(cfg["risks"], s.stakes)
    return {"type": s.key, "stakes": s.stakes, "reversible": s.reversible,
            "tier": s.tier, "effective_tier": rule.effective_tier(s, n, s.stakes),
            "capped": n is None, "required": None if n is None else rule.required(s, n),
            "series": s.series, "sessions": len(s.sessions), "wald": s.wald,
            "successes": s.successes, "faults": s.faults, "neutrals": s.neutrals, "spot_checks": s.spot_checks,
            "provisional": s.provisional, "trial_left": s.trial_left, "trial_wait": s.trial_wait,
            "unresolved_fault": s.unresolved_fault, "unresolved_fault_label": "fault on record",
            "guarantee": rule.guarantee(s, n, cfg["spot"])}


def _agent_rows(core, st, cfg: dict, suspended: int) -> list[dict]:
    by_agent: dict[str, list] = {}
    for agent, s in st.states():
        by_agent.setdefault(agent, []).append(s)
    out = []
    for agent, states in by_agent.items():
        model, provider = core.personal.split_agent(agent)
        types = [_type_row(core, cfg, s) for s in states]
        out.append({"agent": agent, "model": model, "provider": provider, "types": types,
                    "provisional": any(t["provisional"] for t in types),
                    "trial": any(t["trial_left"] or t["trial_wait"] for t in types),
                    "unresolved_fault": any(t["unresolved_fault"] for t in types),
                    "unresolved_fault_label": "fault on record",
                    "suspended": suspended, "totals": st.totals(agent)})
    return out


# ---------------------------------------------------------------------------------------------------------- GETs
def _agents() -> dict:
    core = _core()
    current = _current(core)
    out = []
    for p in _profiles():
        with _open(core, p) as st:
            if st is None:
                continue
            cfg = _settings(core, st)
            # Sessions are stored without their agent: the suspended count is the profile's, repeated on each agent.
            suspended = st.db.execute("SELECT COUNT(*) FROM sessions WHERE tainted = 1").fetchone()[0]
            out.append({"profile": p["name"], "current": p["name"] == current, "suspended": suspended,
                        "settings": {"preset": cfg["preset"], "risks": cfg["risks"], "spot": cfg["spot"],
                                     "strict": cfg["strict"]},
                        "agents": _agent_rows(core, st, cfg, suspended)})
    return {"current": current, "profiles": out}


def _activity(since: float) -> dict:
    core = _core()
    now = time.time()
    total = dict.fromkeys(core.store.STAT_FIELDS, 0)
    profiles, undoable = [], []
    for p in _profiles():
        with _open(core, p) as st:
            if st is None:
                continue
            t = st.totals(since=since)
            for k, v in t.items():
                total[k] += v
            profiles.append({"profile": p["name"], "totals": t})
            rows = st.db.execute("SELECT id, agent, type, at, fault FROM undo WHERE undone = 0 AND snap_id IS NOT NULL "
                                 "AND at > ? ORDER BY id DESC LIMIT ?", (now - core.UNDO_WINDOW, UNDOABLE_LIMIT)).fetchall()
            undoable += [{"profile": p["name"], "id": r[0], "agent": r[1], "type": r[2], "age": round(now - r[3], 1),
                          "counts_as_fault": not r[4]} for r in rows]
    return {"since": since, "totals": total, "profiles": profiles, "undoable": undoable}


def _models(type_key: str | None) -> dict:
    core = _core()
    rows = []
    for p in _profiles():
        with _open(core, p) as st:
            if st is None:
                continue
            for r in core.personal.model_table(st, type_key):
                r["profile"] = p["name"]
                r["public"] = core.benchmarks.card(None, r["model"], r["type"])
                rows.append(r)
    rows.sort(key=lambda r: (r["type"], r["high"], r["agent"], r["profile"]))
    types = sorted({r["type"] for r in rows})
    return {"rows": rows, "benchmarks": {t: core.benchmarks.benchmark_for(t) for t in types}}


def _preview(agent: str, to: str, profile: str | None) -> dict:
    core = _core()
    p = _profile(profile, core)
    if "@" not in to:
        to = f"{to}@{core.personal.split_agent(agent)[1]}"
    old_model, new_model = core.personal.split_agent(agent)[0], core.personal.split_agent(to)[0]
    with _open(core, p) as st:
        if st is None:
            raise HTTPException(404, f"profile {p['name']} has no clearance database yet")
        cfg = _settings(core, st)
        old = {s.key: s for _, s in st.states(agent)}
        if not old:
            raise HTTPException(404, f"no record for {agent} in profile {p['name']}")
        have = {s.key: s for _, s in st.states(to)}
        personal = {(r["agent"], r["type"]): r for r in core.personal.model_table(st)
                    if r["agent"] in (agent, to)}
        types = []
        for key, s in sorted(old.items()):
            n_new = core.params.required_n(cfg["risks"], s.stakes)
            if key in have:
                status, new = "kept", have[key]          # the new agent's own evidence is never overwritten
            else:
                eligible = not cfg["strict"] and s.stakes != "high" and n_new is not None
                veto = bool(eligible and core.benchmarks.veto(old_model, new_model, key))
                status = "vetoed" if veto else "carried" if eligible else "reset"
                new = core.rule.carry_over(s, n_new=n_new, veto=veto, strict=cfg["strict"])
            types.append({"type": key, "stakes": s.stakes, "status": status,
                          "old": _type_row(core, cfg, s), "new": _type_row(core, cfg, new),
                          "card": core.benchmarks.card(old_model, new_model, key),
                          "personal": [personal[(a, key)] for a in (agent, to) if (a, key) in personal]})
    return {"profile": p["name"], "from": agent, "to": to, "strict": cfg["strict"], "types": types}


_PASSPORTS: dict = {}          # (database, agent, ledger head, key present) -> response; verifying replays the whole ledger
_PASSPORTS_MAX = 64


def _passport(agent: str, profile: str | None) -> dict:
    core = _core()
    p = _profile(profile, core)
    with _open(core, p) as st:
        if st is None or not st.states(agent):
            raise HTTPException(404, f"no record for {agent} in profile {p['name']}")
        head = st.db.execute("SELECT seq, hash FROM ledger ORDER BY seq DESC LIMIT 1").fetchone()
        key = (st.path, agent, tuple(head or ()), os.path.exists(os.path.join(_data_dir(p), core.passport.KEY_FILE)))
        hit = _PASSPORTS.get(key)
        if hit is not None:                           # the ledger has not moved: same passport, same verdict
            return hit
        rows = st.ledger()
        cfg = _settings(core, st)
        doc = core.passport.build(st, agent, {"profile": p["name"], "risks": cfg["risks"], "spot": cfg["spot"],
                                              "strict": cfg["strict"]}, _data_dir(p), redact=True, create_key=False,
                                  rows=rows)
    out = {"profile": p["name"], "passport": doc, "verify": core.passport.verify(doc, rows)}
    if len(_PASSPORTS) >= _PASSPORTS_MAX:
        _PASSPORTS.clear()
    _PASSPORTS[key] = out
    return out


def _timeline(agent: str, profile: str | None) -> dict:
    core = _core()
    p = _profile(profile, core)
    needle = json.dumps(agent)[1:-1].replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    with _open(core, p) as st:
        if st is None:
            raise HTTPException(404, f"profile {p['name']} has no clearance database yet")
        rows = st.db.execute("SELECT seq, at, event FROM ledger WHERE event LIKE ? ESCAPE '\\' "
                             "ORDER BY seq DESC LIMIT ?", (f'%"agent":"{needle}"%', TIMELINE_LIMIT)).fetchall()
    return {"profile": p["name"], "agent": agent,
            "events": [{"seq": r[0], "at": r[1], "input": json.loads(r[2]).get("event") in core.store.INPUT_KINDS,
                        **json.loads(r[2])} for r in rows]}


@router.get("/agents")
async def agents():
    return await asyncio.to_thread(_agents)


@router.get("/activity")
async def activity(since: float | None = Query(None, description="epoch seconds; default: the last 24 h")):
    return await asyncio.to_thread(_activity, time.time() - DAY if since is None else since)


@router.get("/models")
async def models(type: str | None = Query(None)):
    return await asyncio.to_thread(_models, type)


@router.get("/preview")
async def preview(agent: str, to: str, profile: str | None = None):
    return await asyncio.to_thread(_preview, agent, to, profile)


@router.get("/passport")
async def passport(agent: str, profile: str | None = None):
    return await asyncio.to_thread(_passport, agent, profile)


@router.get("/timeline")
async def timeline(agent: str, profile: str | None = None):
    return await asyncio.to_thread(_timeline, agent, profile)


# --------------------------------------------------------------------------------------------------------- POSTs
class RevokeBody(BaseModel):
    agent: str
    type: str | None = None
    all: bool = False


class FlagBody(BaseModel):
    agent: str
    type: str
    note: str = ""            # accepted, never stored: the ledger holds no free text


class UndoBody(BaseModel):
    id: int


class SettingsBody(BaseModel):
    preset: str | None = None
    risks: dict | None = None
    spot: float | None = None
    strict: bool | None = None


def _mine(core, profile: str | None) -> None:
    """POSTs write to this process's own profile: any other one is refused."""
    if profile is not None and profile != _current(core):
        raise HTTPException(409, f"{profile} is not the dashboard's current profile ({_current(core)})")


def _cfg(core, st) -> tuple[dict, bool]:
    """(settings, synced). With the plugin context (hooks registered in this process) the configured settings are
    used and synced into the ledger; without it, the ones the ledger already holds, so nothing is re-logged."""
    if core.ST.ctx is not None:
        return core.settings(), True
    return _settings(core, st), False


def _known(st, agent: str) -> dict:
    known = {s.key: s for _, s in st.states(agent)}
    if not known:
        raise HTTPException(404, f"no record for {agent}")
    return known


def _revoke(body: RevokeBody) -> dict:
    core = _core()
    if body.type is None and not body.all:
        raise HTTPException(422, "give a type, or all")
    key = "all" if body.all or body.type == "all" else body.type
    done = []
    try:
        with core.txn() as st:
            _known(st, body.agent)
            for _, s in st.states(body.agent):
                if key not in ("all", s.key):
                    continue
                if key == "all" and s.tier == core.rule.T1 and not s.series and not s.provisional and s.wald >= 0:
                    continue                                       # nothing earned to take back
                events = core.rule.revoke(s)
                st.put_state(body.agent, s)
                st.log({"event": "revoke", "agent": body.agent, "type": s.key})
                for ev in events:
                    st.log({**ev, "agent": body.agent})
                done.append(s.key)
    except core.LockTimeout:
        raise HTTPException(503, "the store is busy, try again")
    if key != "all" and not done:
        raise HTTPException(404, f"no record of {key} for {body.agent}")
    return {"agent": body.agent, "revoked": done}


def _flag(body: FlagBody) -> dict:
    core = _core()
    try:
        with core.txn() as st:
            s = _known(st, body.agent).get(body.type)
            if s is None:
                raise HTTPException(404, f"no record of {body.type} for {body.agent}")
            cfg, synced = _cfg(core, st)
            if synced:
                core.sync_settings(st, cfg)
            core.record_outcome(st, cfg, agent=body.agent, type_key=body.type, stakes=s.stakes,
                                reversible=s.reversible, result="fault", source="flag")
            st.bump(body.agent, "faults")
            s = st.get_state(body.agent, body.type, s.stakes, s.reversible)
            row = _type_row(core, cfg, s)
    except core.LockTimeout:
        raise HTTPException(503, "the store is busy, try again")
    return {"agent": body.agent, "type": body.type, "tier": s.tier, "state": row}


def _undo(body: UndoBody) -> dict:
    core = _core()
    try:
        with core.txn() as st:
            entry = st.get_undo(body.id)
            if entry is None:
                raise HTTPException(404, f"no action #{body.id} to undo")
            cfg, synced = _cfg(core, st)
            message = core.undo_entry(st, body.id, None if synced else cfg)
            done = st.get_undo(body.id)["undone"]
    except core.LockTimeout:
        raise HTTPException(503, "the store is busy, try again")
    return {"id": body.id, "undone": done, "message": message}


def _set_settings(body: SettingsBody) -> dict:
    core = _core()
    ctx = core.ST.ctx
    if ctx is None or not callable(getattr(ctx, "set_config", None)):
        raise HTTPException(501, "this process cannot write settings: set them in config.yaml "
                                 "(plugins.entries.clearance.settings)")
    changes = {}
    if body.preset is not None:
        if body.preset.strip().lower() not in core.params.PRESETS:
            raise HTTPException(422, f"preset must be one of {', '.join(core.params.PRESETS)}")
        changes["preset"] = body.preset.strip().lower()
    if body.risks is not None:
        for level, v in body.risks.items():
            if level not in core.params.LEVELS or (core.parse_risk(v, "bad") == "bad"):
                raise HTTPException(422, f"risks: {level}={v!r}: use low, medium or high with a value between 0 and 1 "
                                         "(0.02, 2%, 1/50) or cap")
        changes["risks"] = dict(body.risks)
    if body.spot is not None:
        if not 0 < body.spot < 1:
            raise HTTPException(422, "spot must be strictly between 0 and 1")
        changes["spot_check"] = body.spot
    if body.strict is not None:
        changes["strict"] = body.strict
    if not changes:
        raise HTTPException(422, "give preset, risks, spot or strict")
    try:
        for k, v in changes.items():
            ctx.set_config(k, v)
    except Exception as e:
        raise HTTPException(501, f"could not save the settings ({type(e).__name__})")
    cfg = core.settings()
    try:
        with core.txn() as st:
            core.sync_settings(st, cfg)           # logs the settings event now, as the next hook would
    except core.LockTimeout:
        raise HTTPException(503, "the store is busy: saved, logged at the next action")
    return {"saved": sorted(changes), "settings": {"preset": cfg["preset"], "risks": cfg["risks"],
                                                    "spot": cfg["spot"], "strict": cfg["strict"]}}


@router.post("/revoke")
async def revoke(body: RevokeBody, profile: str | None = None):
    _mine(_core(), profile)
    return await asyncio.to_thread(_revoke, body)


@router.post("/flag")
async def flag(body: FlagBody, profile: str | None = None):
    _mine(_core(), profile)
    return await asyncio.to_thread(_flag, body)


@router.post("/undo")
async def undo(body: UndoBody, profile: str | None = None):
    _mine(_core(), profile)
    return await asyncio.to_thread(_undo, body)


@router.post("/settings")
async def settings(body: SettingsBody, profile: str | None = None):
    _mine(_core(), profile)
    return await asyncio.to_thread(_set_settings, body)
