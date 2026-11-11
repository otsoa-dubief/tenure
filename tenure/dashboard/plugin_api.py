# Copyright 2026 Otsoa Dubief
# SPDX-License-Identifier: Apache-2.0
"""Dashboard API of tenure, mounted by Hermes at ``/api/plugins/tenure/``.

Every route sits under ``/api/``, so Hermes' dashboard auth middleware (session token, or the OAuth gate) covers it:
``/api/plugins/...`` is not in the public path list. This file adds no authentication of its own.

GETs open each profile's database read-only (``Store.open_readonly``), skip a profile that has none, run in a worker
thread (``asyncio.to_thread``) so the dashboard's event loop never waits on SQLite, and use ``LIMIT``ed queries. They
never write: not a row, not a file (the passport is unsigned when its key does not exist yet).

POSTs act on the dashboard's current profile only (the process's Hermes home; an ``of=`` naming another one is
refused) and go through the same functions as the hooks and the CLI, so the ledger gets the same input events.
"""
from __future__ import annotations

import asyncio
import contextlib
import hashlib
import importlib.util
import json
import os
import sqlite3
import sys
import threading
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

# Our cross-profile selector is `of`, never `profile`: Hermes' own ``?profile=`` scopes a request to a served profile
# (it is stripped before the plugin sees it, and a secondary profile's request for this plugin then gets "Plugin not
# found"), so a parameter of that name would collide with it. tests/test_dashboard_api.py pins the name.
SELECTOR = "of"

router = APIRouter()

TIMELINE_LIMIT = 200          # ledger events per agent in /timeline
UNDOABLE_LIMIT = 200          # undoable actions per profile in /activity
DAY = 24 * 3600
_FOLDER = ("plugin-data", "tenure")
_DB = "tenure.db"


_CORE = None
_CORE_LOCK = threading.Lock()


def _core():
    """The plugin package, the same module object on every call (so one ``ST.lock``): as Hermes loaded it (the hooks'
    ``ST`` lives there), else imported once from this file's place."""
    global _CORE
    if _CORE is None:
        with _CORE_LOCK:
            if _CORE is None:
                for name in ("hermes_plugins.tenure", "tenure"):
                    mod = sys.modules.get(name)
                    if mod is not None and hasattr(mod, "ST"):
                        _CORE = mod
                        break
                else:
                    root = Path(__file__).resolve().parents[1]
                    spec = importlib.util.spec_from_file_location("tenure", root / "__init__.py",
                                                                  submodule_search_locations=[str(root)])
                    mod = importlib.util.module_from_spec(spec)
                    sys.modules["tenure"] = mod
                    spec.loader.exec_module(mod)
                    _CORE = mod
    return _CORE


class _Unreadable(Exception):
    """A profile's database exists but cannot be read."""


def _name(core, key: str, raw: bool) -> str:
    """A type as shown: hashed after the program and subcommand, as in the passport, unless ``raw`` (the owner asks)."""
    return key if raw else core.passport.redact_type(key)


def _wanted(core, states: dict, wanted: str) -> list:
    """The types of ``states`` the caller means: the exact raw name when one matches, else every type whose redacted
    name (the one the dashboard showed) is ``wanted``. More than one is ambiguous: the caller answers 409."""
    if wanted in states:
        return [wanted]
    return [k for k in states if core.passport.redact_type(k) == wanted]


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
    """The profile's store, read-only; None when it has no database yet (nothing is created); ``_Unreadable`` when it
    has one that cannot be opened."""
    path = os.path.join(_data_dir(p), _DB)
    try:
        st = core.store.Store.open_readonly(path)
    except FileNotFoundError:
        yield None
        return
    except (RuntimeError, sqlite3.Error, OSError):
        raise _Unreadable(p["name"])
    try:
        yield st
    finally:
        st.db.close()


def _profile(name: str | None, core) -> dict:
    """The profile named by ``of`` (default: this process's own)."""
    name = name or _current(core)
    for p in _profiles():
        if p["name"] == name:
            return p
    raise HTTPException(404, f"no such profile: {name}")


def _settings(core, st, own: bool = False) -> dict:
    """The settings in force in a profile, with ``pending`` when the ledger has not logged them yet.

    This process's own profile (``own``): the owner's settings, the ones the hooks decide with and `hermes tenure
    status` shows; the ledger logs them at the next action. Another profile: its config is not readable from here, so
    the settings of its ledger's last settings event (what its tiers were computed under), else the default preset."""
    if own:
        cfg = core.settings()
        pending = st.get_meta("settings:fingerprint") != core.settings_fingerprint(cfg)
        return {**cfg, "pending": pending}
    row = st.db.execute("SELECT event FROM ledger WHERE event LIKE '%\"event\":\"settings\"%' "
                        "ORDER BY seq DESC LIMIT 1").fetchone()
    params = core.params
    ev = json.loads(row[0]) if row else {}
    risks = dict(params.PRESETS[params.DEFAULT_PRESET])
    risks.update({k: v for k, v in (ev.get("risks") or {}).items() if k in params.LEVELS})
    spot = ev.get("spot")
    preset = next((n for n, r in params.PRESETS.items() if all(risks.get(lv) == r[lv] for lv in params.LEVELS)),
                  "custom")
    return {"preset": preset, "risks": risks,
            "spot": spot if isinstance(spot, (int, float)) and 0 < spot < 1 else params.DEFAULT_SPOT,
            "strict": bool(ev.get("strict")), "overrides": {}, "enabled": True, "pending": False,
            "start": ev.get("start") if ev.get("start") in params.STARTS else "probation"}


def _type_row(core, cfg: dict, s, raw: bool = False) -> dict:
    rule, params = core.rule, core.params
    n = params.required_n(cfg["risks"], s.stakes)
    return {"type": _name(core, s.key, raw), "stakes": s.stakes, "reversible": s.reversible,
            "tier": s.tier,
            # A copied profile that has not started yet will restart every type: nothing it shows is earned yet.
            "effective_tier": rule.T1 if cfg.get("copy_pending") else rule.effective_tier(s, n, s.stakes),
            # Trusted start: no fault yet, so it asks nothing Hermes would not (an earned T3 shows as T3).
            "trusted": (not cfg.get("copy_pending") and core.trusted(cfg, s, n, s.stakes)
                        and rule.effective_tier(s, n, s.stakes) != rule.T3),
            "distrusted": s.distrusted,
            "capped": n is None, "required": None if n is None else rule.required(s, n),
            "series": s.series, "sessions": len(s.sessions), "wald": s.wald,
            "successes": s.successes, "faults": s.faults, "neutrals": s.neutrals, "spot_checks": s.spot_checks,
            "provisional": s.provisional, "trial_left": s.trial_left, "trial_wait": s.trial_wait,
            "unresolved_fault": s.unresolved_fault, "unresolved_fault_label": "fault on record",
            "guarantee": rule.guarantee(s, n, cfg["spot"])}


def _agent_rows(core, st, cfg: dict, suspended: int, raw: bool) -> list[dict]:
    by_agent: dict[str, list] = {}
    for agent, s in st.states():
        by_agent.setdefault(agent, []).append(s)
    out = []
    for agent, states in by_agent.items():
        model, provider = core.personal.split_agent(agent)
        types = [_type_row(core, cfg, s, raw) for s in states]
        out.append({"agent": agent, "model": model, "provider": provider, "types": types,
                    "provisional": any(t["provisional"] for t in types),
                    "trial": any(t["trial_left"] or t["trial_wait"] for t in types),
                    "unresolved_fault": any(t["unresolved_fault"] for t in types),
                    "unresolved_fault_label": "fault on record",
                    "suspended": suspended, "totals": st.totals(agent)})
    return out


# ---------------------------------------------------------------------------------------------------------- GETs
def _agents(raw: bool) -> dict:
    core = _core()
    current = _current(core)
    out = []
    for p in _profiles():
        try:
            with _open(core, p) as st:
                if st is None:
                    continue
                cfg = _settings(core, st, own=p["name"] == current)
                cfg["copy_pending"] = core.copy_pending(st, str(p["home"]), os.path.join(_data_dir(p), _DB))
                # Sessions are stored without their agent: the suspended count is the profile's, repeated on each agent.
                suspended = st.db.execute("SELECT COUNT(*) FROM sessions WHERE tainted = 1").fetchone()[0]
                out.append({"profile": p["name"], "current": p["name"] == current, "suspended": suspended,
                            "settings": {"preset": cfg["preset"], "risks": cfg["risks"], "spot": cfg["spot"],
                                         "strict": cfg["strict"], "pending": cfg["pending"],
                                         "start": cfg.get("start", "probation"),
                                         "copy_pending": cfg["copy_pending"]},
                            "agents": _agent_rows(core, st, cfg, suspended, raw)})
        except (_Unreadable, sqlite3.Error):
            out.append({"profile": p["name"], "current": p["name"] == current, "error": "unreadable"})
    return {"current": current, "profiles": out}


def _activity(since: float, raw: bool) -> dict:
    core = _core()
    now = time.time()
    total = dict.fromkeys(core.store.STAT_FIELDS, 0)
    profiles, undoable = [], []
    for p in _profiles():
        try:
            with _open(core, p) as st:
                if st is None:
                    continue
                t = st.totals(since=since)
                rows = st.db.execute("SELECT id, agent, type, at, fault, snap_id FROM undo WHERE undone = 0 "
                                     "AND snap_id IS NOT NULL AND at > ? ORDER BY id DESC LIMIT ?",
                                     (now - core.UNDO_WINDOW, UNDOABLE_LIMIT)).fetchall()
        except (_Unreadable, sqlite3.Error):
            profiles.append({"profile": p["name"], "error": "unreadable"})
            continue
        for k, v in t.items():
            total[k] += v
        profiles.append({"profile": p["name"], "totals": t})
        undoable += [{"profile": p["name"], "id": r[0], "agent": r[1], "type": _name(core, r[2], raw),
                      "age": round(now - r[3], 1), "counts_as_fault": not r[4],
                      **_snap_files(p, r[5])} for r in rows]
    return {"since": since, "totals": total, "profiles": profiles, "undoable": undoable}


def _snap_files(p: dict, snap_id: str | None) -> dict:
    """What an undo would restore (``undo.describe``): the first file and how many in all, or {}."""
    return _core().undo.describe(snap_id, _data_dir(p))


def _models(type_key: str | None, raw: bool) -> dict:
    core = _core()
    rows, unreadable = [], []
    for p in _profiles():
        try:
            with _open(core, p) as st:
                if st is None:
                    continue
                table = core.personal.model_table(st)
        except (_Unreadable, sqlite3.Error):
            unreadable.append({"profile": p["name"], "error": "unreadable"})
            continue
        for r in table:
            if type_key is not None and type_key not in (r["type"], core.passport.redact_type(r["type"])):
                continue
            public = core.benchmarks.card(None, r["model"], r["type"])
            r.update(profile=p["name"], public=public, benchmark=core.benchmarks.benchmark_for(r["type"]),
                     type=_name(core, r["type"], raw))
            rows.append(r)
    rows.sort(key=lambda r: (r["type"], r["high"], r["agent"], r["profile"]))
    return {"rows": rows, "benchmarks": {r["type"]: r["benchmark"] for r in rows}, "unreadable": unreadable}


def _preview(agent: str, to: str, profile: str | None, raw: bool) -> dict:
    core = _core()
    p = _profile(profile, core)
    if "@" not in to:
        to = f"{to}@{core.personal.split_agent(agent)[1]}"
    old_model, new_model = core.personal.split_agent(agent)[0], core.personal.split_agent(to)[0]
    with _open(core, p) as st:
        if st is None:
            raise HTTPException(404, f"profile {p['name']} has no tenure database yet")
        cfg = _settings(core, st, own=p["name"] == _current(core))
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
            types.append({"type": _name(core, key, raw), "stakes": s.stakes, "status": status,
                          "old": _type_row(core, cfg, s, raw), "new": _type_row(core, cfg, new, raw),
                          "card": core.benchmarks.card(old_model, new_model, key),
                          "personal": [{**personal[(a, key)], "type": _name(core, key, raw)}
                                       for a in (agent, to) if (a, key) in personal]})
    return {"profile": p["name"], "from": agent, "to": to, "strict": cfg["strict"], "types": types}


_PASSPORTS: dict = {}          # (database, agent, ledger head, key present, raw) -> response; verifying replays the ledger
_PASSPORTS_MAX = 64


def _checked_ledger(st) -> tuple[list[dict], bool]:
    """The ledger rows, and whether the hash chain holds, in one pass over the stored text. The chain hash is taken over
    the canonical text the store wrote (``store.chain_hash``), so hashing that text as stored gives the same digest
    without serialising every event again; any mismatch just reports False and the caller runs the full check."""
    rows, ok, prev = [], True, _core().store.GENESIS
    for seq, at, text, p, h in st.db.execute("SELECT seq, at, event, prev, hash FROM ledger ORDER BY seq"):
        if ok and (seq != len(rows) + 1 or p != prev or
                   h != hashlib.sha256(f"{p}|{seq}|{at!r}|{text}".encode("utf-8")).hexdigest()):
            ok = False
        rows.append({"seq": seq, "at": at, "event": json.loads(text), "prev": p, "hash": h})
        prev = h
    return rows, ok


def _passport(agent: str, profile: str | None, raw: bool) -> dict:
    core = _core()
    p = _profile(profile, core)
    with _open(core, p) as st:
        if st is None or not st.states(agent):
            raise HTTPException(404, f"no record for {agent} in profile {p['name']}")
        if core.copy_pending(st, str(p["home"]), os.path.join(_data_dir(p), _DB)):
            raise HTTPException(409, f"profile {p['name']} was copied from another profile and has not started "
                                     f"since: its record is checked, and its passport signed, when it starts")
        head = st.db.execute("SELECT seq, hash FROM ledger ORDER BY seq DESC LIMIT 1").fetchone()
        key = (st.path, agent, tuple(head or ()), os.path.exists(os.path.join(_data_dir(p), core.passport.KEY_FILE)),
               raw)
        hit = _PASSPORTS.get(key)
        if hit is not None:                           # the ledger has not moved: same passport, same verdict
            return hit
        rows, chain_ok = _checked_ledger(st)
        cfg = _settings(core, st)
        doc = core.passport.build(st, agent, {"profile": p["name"], "risks": cfg["risks"], "spot": cfg["spot"],
                                              "strict": cfg["strict"]}, _data_dir(p), redact=not raw,
                                  create_key=False, rows=rows)
    out = {"profile": p["name"], "passport": doc, "verify": core.passport.verify(doc, rows, chain_ok=chain_ok)}
    if len(_PASSPORTS) >= _PASSPORTS_MAX:
        _PASSPORTS.clear()
    _PASSPORTS[key] = out
    return out


def _timeline(agent: str, profile: str | None, raw: bool) -> dict:
    core = _core()
    p = _profile(profile, core)
    # The event text is canonical JSON (ensure_ascii=False, like store._canon): match the agent the same way.
    needle = json.dumps(agent, ensure_ascii=False)[1:-1].replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    with _open(core, p) as st:
        if st is None:
            raise HTTPException(404, f"profile {p['name']} has no tenure database yet")
        rows = st.db.execute("SELECT seq, at, event FROM ledger WHERE event LIKE ? ESCAPE '\\' "
                             "ORDER BY seq DESC LIMIT ?", (f'%"agent":"{needle}"%', TIMELINE_LIMIT)).fetchall()
    events = []
    for seq, at, text in rows:
        e = json.loads(text)
        if isinstance(e.get("type"), str):
            e["type"] = _name(core, e["type"], raw)
        events.append({"seq": seq, "at": at, "input": e.get("event") in core.store.INPUT_KINDS, **e})
    return {"profile": p["name"], "agent": agent, "events": events}


def _get(fn, *args):
    """A GET's work, in a worker thread: an unreadable profile answers 503 instead of an error page."""
    try:
        return fn(*args)
    except _Unreadable as e:
        raise HTTPException(503, f"profile {e} has a tenure database that cannot be read")
    except sqlite3.Error:
        raise HTTPException(503, "the tenure database could not be read, try again")


_RAW = Query(False, description="1 shows raw action type names (default: redacted like the passport)")
_OF = Query(None, description="profile name (default: the dashboard's current profile)")


@router.get("/agents")
async def agents(raw: bool = _RAW):
    return await asyncio.to_thread(_get, _agents, raw)


@router.get("/activity")
async def activity(since: float | None = Query(None, description="epoch seconds; default: the last 24 h"),
                   raw: bool = _RAW):
    return await asyncio.to_thread(_get, _activity, time.time() - DAY if since is None else since, raw)


@router.get("/models")
async def models(type: str | None = Query(None), raw: bool = _RAW):
    return await asyncio.to_thread(_get, _models, type, raw)


@router.get("/preview")
async def preview(agent: str, to: str, of: str | None = _OF, raw: bool = _RAW):
    return await asyncio.to_thread(_get, _preview, agent, to, of, raw)


@router.get("/passport")
async def passport(agent: str, of: str | None = _OF, raw: bool = _RAW):
    return await asyncio.to_thread(_get, _passport, agent, of, raw)


@router.get("/timeline")
async def timeline(agent: str, of: str | None = _OF, raw: bool = _RAW):
    return await asyncio.to_thread(_get, _timeline, agent, of, raw)


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


def _mine(core, of: str | None) -> None:
    """POSTs write to this process's own profile: any other one is refused."""
    if of is not None and of != _current(core):
        raise HTTPException(409, f"{of} is not the dashboard's current profile ({_current(core)})")


def _post(fn, body, of: str | None, raw: bool):
    """A POST's work, in a worker thread: the profile check, then ``fn``; a busy store answers 503."""
    core = _core()
    _mine(core, of)
    try:
        out = fn(body, raw)
    except (core.LockTimeout, sqlite3.OperationalError):
        raise HTTPException(503, "the store is busy, try again")
    core._push("changed", {"by": fn.__name__.lstrip("_")})       # the desktop half refreshes at once
    return out


def _known(st, agent: str) -> dict:
    known = {s.key: s for _, s in st.states(agent)}
    if not known:
        raise HTTPException(404, f"no record for {agent}")
    return known


def _revoke(body: RevokeBody, raw: bool) -> dict:
    core = _core()
    if body.type is None and not body.all:
        raise HTTPException(422, "give a type, or all")
    every = body.all or body.type == "all"
    done = []
    with core.txn() as st:
        known = _known(st, body.agent)
        keys = list(known) if every else _wanted(core, known, body.type)
        if not keys:
            raise HTTPException(404, f"no record of {body.type} for {body.agent}")
        if len(keys) > 1:
            raise HTTPException(409, f"{body.type} names {len(keys)} action types: use the raw names (raw=1)")
        for key in keys:
            s = known[key]
            if every and s.tier == core.rule.T1 and not s.series and not s.provisional and s.wald >= 0:
                continue                                       # nothing earned to take back
            events = core.rule.revoke(s)
            st.put_state(body.agent, s)
            st.log({"event": "revoke", "agent": body.agent, "type": s.key})
            for ev in events:
                st.log({**ev, "agent": body.agent})
            done.append(_name(core, s.key, raw))
    return {"agent": body.agent, "revoked": done}


def _flag(body: FlagBody, raw: bool) -> dict:
    core = _core()
    with core.txn() as st:
        known = _known(st, body.agent)
        keys = _wanted(core, known, body.type)
        if not keys:
            raise HTTPException(404, f"no record of {body.type} for {body.agent}")
        if len(keys) > 1:
            raise HTTPException(409, f"{body.type} names {len(keys)} action types: use the raw names (raw=1)")
        key = keys[0]
        s = known[key]
        cfg = core.settings()
        core.sync_settings(st, cfg)
        core.record_outcome(st, cfg, agent=body.agent, type_key=key, stakes=s.stakes, reversible=s.reversible,
                            result="fault", source="flag")
        st.bump(body.agent, "faults")
        s = st.get_state(body.agent, key, s.stakes, s.reversible)
        row = _type_row(core, cfg, s, raw)
    return {"agent": body.agent, "type": _name(core, key, raw), "tier": s.tier, "state": row}


def _undo(body: UndoBody, raw: bool) -> dict:
    core = _core()
    with core.txn() as st:
        message = core.undo_entry(st, body.id)
        entry = st.get_undo(body.id)
    message.cleanup()                                 # the transaction has committed: the snapshot can go
    if entry is None:
        raise HTTPException(404, f"no action #{body.id} to undo")
    return {"id": body.id, "undone": entry["undone"], "ok": message.ok, "message": str(message)}


def _set_settings(body: SettingsBody, raw: bool) -> dict:
    core = _core()
    ctx = core.ST.ctx
    if ctx is None or not callable(getattr(ctx, "set_config", None)):
        raise HTTPException(501, "this process cannot write settings (Hermes offers plugins no other public writer): "
                                 "run `hermes tenure setup`, or set plugins.entries.tenure.settings in "
                                 "config.yaml")
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
    with core.txn() as st:
        core.sync_settings(st, cfg)           # logs the settings event now, as the next hook would
    return {"saved": sorted(changes), "settings": {"preset": cfg["preset"], "risks": cfg["risks"],
                                                    "spot": cfg["spot"], "strict": cfg["strict"]}}


@router.post("/revoke")
async def revoke(body: RevokeBody, of: str | None = _OF, raw: bool = _RAW):
    return await asyncio.to_thread(_post, _revoke, body, of, raw)


@router.post("/flag")
async def flag(body: FlagBody, of: str | None = _OF, raw: bool = _RAW):
    return await asyncio.to_thread(_post, _flag, body, of, raw)


@router.post("/undo")
async def undo(body: UndoBody, of: str | None = _OF, raw: bool = _RAW):
    return await asyncio.to_thread(_post, _undo, body, of, raw)


@router.post("/settings")
async def settings(body: SettingsBody, of: str | None = _OF, raw: bool = _RAW):
    return await asyncio.to_thread(_post, _set_settings, body, of, raw)
