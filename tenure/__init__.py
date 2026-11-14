# Copyright 2026 Otsoa Dubief
# SPDX-License-Identifier: Apache-2.0
"""tenure: earned autonomy for Hermes, per action type, from verified evidence.

Each action type (``classify``) of each agent (``model@provider``) has a tier (``rule``): T1 asks the owner first;
T2 acts, then notifies the owner with an undo (reversible types only); T3 acts alone, with random spot checks. A type
climbs on verified outcomes only, judged after the tool has run (``proofs``): an approved action that ran cleanly and
passed its automatic check is a success; a refusal, a failed check, an undo or a flagged error is a fault; what
nobody verified (a timeout, a failed tool, an answer from no person, an action taken alone) teaches nothing. The
automatic check judges every action that ran, whoever let it run.

Hooks:

- ``pre_api_request``: which agent acts. A new agent inherits the previous agent's record on trial (half of each
  series, provisional), unless a public benchmark vetoes it or strict mode is on.
- ``pre_tool_call``: the decision for the action's type. Asks go through Hermes' own approval gate with a rule key
  that ends with a fresh uuid, so a "session" or "always" answer never silences a later ask. A tier only lets a call
  run when it was earned at the call's stakes and meets today's requirement. T2 saves the files first (``undo``). A
  session that read external content asks for everything.
- ``post_approval_response``: a refusal is a fault; an approval waits for the execution.
- ``post_tool_call``: the verified outcome of the decision. A session that read external content, or ran code, is
  suspended first, in a transaction of its own. The cwd a terminal command reports becomes the session's: each call is
  classified in the terminal's real working directory (``call_cwd``), not the session's starting one.
- ``subagent_start``: a child agent of a suspended parent starts suspended (its task comes from that context).
- ``subagent_stop``: a child agent that read external content suspends its parent, whose context gets its summary.

Calls outside any session (Hermes passes no session id) share the empty session: their pending rows are matched by
call id and type, and an external read suspends them in this process only, for an hour, never in the store.

Every outcome, settings change, agent change and revocation is written to the hash-chained ledger as an input event
(``store``), in the transaction that applies it, so that replaying the ledger recomputes the same tiers. CLI:
``hermes tenure``. Slash command: ``/tenure``. Local only: no network, no LLM call.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import random
import secrets
import threading
import time
import uuid
from collections import OrderedDict
from contextlib import contextmanager

from . import benchmarks, classify, fields, i18n, params, passport, personal, proofs, rule, store, undo
from .i18n import tr

log = logging.getLogger("tenure")
PREFIX = "tenure"
RULE = rule.VERSION              # the rule named in settings events; the passport computes its fingerprint
PURGE_EVERY = 3600               # seconds between two clean-ups of undo snapshots past their window, per process
MAX_SESSIONS = 4096              # sessions whose agent, or suspension, this process remembers
LOCK_TIMEOUT = 10.0              # seconds a hook waits for another thread's transaction before giving up
HOOK_BUDGET = 25.0               # seconds pre_tool_call may take in all (Hermes stops waiting at 30)
SESSIONLESS_TAINT = 3600         # seconds a read outside any session suspends sessionless calls of this process
_TIERS = (rule.T1, rule.T2, rule.T3)


def tier_name(tier) -> str:
    """"T1 asks first", in the owner's language."""
    return tr(f"tier.short.{tier}") if tier in _TIERS else str(tier)


def _tier_long(tier) -> str:
    """"T1, asking first", in the owner's language."""
    return tr(f"tier.long.{tier}") if tier in _TIERS else str(tier)


def stakes_name(stakes) -> str:
    """A stakes level as the owner reads it (the level itself stays the identifier in settings)."""
    return tr(f"stakes.{stakes}") if stakes in params.LEVELS else str(stakes)


class LockTimeout(RuntimeError):
    """Another thread of this process kept the store for more than LOCK_TIMEOUT seconds."""


class _NoSpot:
    """The draw of a preview decision: never a spot check, so the real draw happens once, in the transaction."""
    @staticmethod
    def random() -> float:
        return 1.0


class _State:
    def __init__(self):
        self.ctx = None
        self.store = None
        self.store_path = ""
        self.lock = threading.RLock()            # one transaction at a time: Hermes runs tools in parallel threads
        self.mem = threading.Lock()              # the in-memory maps below; never held during I/O
        self.opening = threading.Lock()          # opening the store
        self.agents: OrderedDict[str, str] = OrderedDict()     # session id -> agent of its latest API request
        self.tainted: OrderedDict[str, float] = OrderedDict()  # suspended sessions (anonymised) -> since when
        self.acted: dict = {}           # (session, type) -> {"ids", "handle", "at"}: this turn's acted message
        self.cwds: OrderedDict[str, str] = OrderedDict()       # session id -> terminal cwd its last command reported
        self.last_agent = ""
        self.rng = random.SystemRandom()
        self.purged_at = 0.0
        self.copy_unchecked = False              # the copied-profile check has not settled yet: every action asks
        self.copy_retry_at = 0.0                 # monotonic time of the next attempt while unsettled


ST = _State()


# --------------------------------------------------------------------------------------------------- settings
def _hermes_home() -> str:
    try:
        from hermes_constants import get_hermes_home
        return str(get_hermes_home())
    except Exception:
        return os.environ.get("HERMES_HOME") or os.path.join(os.path.expanduser("~"), ".hermes")


def data_dir() -> str:
    """``<hermes home>/plugin-data/tenure``, from Hermes' ``plugin_data_dir`` when it can be imported."""
    try:
        from plugins.plugin_storage import plugin_data_dir
        return str(plugin_data_dir(PREFIX))
    except Exception:
        return os.path.join(_hermes_home(), "plugin-data", PREFIX)


def store_() -> store.Store:
    path = os.path.join(data_dir(), "tenure.db")
    with ST.opening:
        if ST.store is None or ST.store_path != path:
            ST.store, ST.store_path = store.Store(path), path
            ST.copy_unchecked, ST.copy_retry_at = True, 0.0
        if ST.copy_unchecked and time.monotonic() >= ST.copy_retry_at:
            try:
                _check_copied(ST.store)
                ST.copy_unchecked = False
            except Exception as e:                 # every action asks until the check settles; retried in a minute
                ST.copy_retry_at = time.monotonic() + COPY_RETRY
                log.warning("tenure: could not check whether this record was copied (every action asks): %s", e)
        return ST.store


HOME_META, STORE_ID_META, FILE_META = "profile:home", "store:id", "profile:file"
SALT_META, COPIED_META = "profile:salt", "profile:copied_at"
COPY_RETRY = 60.0


class CopyCheckFailed(Exception):
    """Another profile's database exists but cannot be read now: the copy check cannot conclude."""


def _home_mark(salt: str, home: str) -> str:
    """What the database keeps of its Hermes home: a salted hash, never the path, and nothing a dictionary of usual
    paths could reverse."""
    import hmac
    return hmac.new(bytes.fromhex(salt), home.encode("utf-8"), hashlib.sha256).hexdigest()[:32]


def _file_id(path: str) -> str:
    """The database file's identity on disk: a rename or move keeps it, a copy does not."""
    s = os.stat(path)
    return f"{s.st_dev}:{s.st_ino}"


def _sibling_homes(home: str) -> list[str]:
    """The other profiles of this Hermes install: the root and every ``<root>/profiles/<name>``, where a clone or a
    duplicated Bot lands."""
    parent = os.path.dirname(home)
    root = os.path.dirname(parent) if os.path.basename(parent) == "profiles" else home
    out = [root]
    try:
        out += [e.path for e in os.scandir(os.path.join(root, "profiles")) if e.is_dir()]
    except OSError:
        pass
    return [os.path.realpath(h) for h in out if os.path.realpath(h) != home]


def _store_id_at(home: str) -> str | None:
    """The store id of the tenure database of another Hermes home, read only; None when it has none (no database,
    or one from before store ids); CopyCheckFailed when it exists but cannot be read now."""
    path = os.path.join(home, "plugin-data", PREFIX, "tenure.db")
    if not os.path.exists(path):
        return None
    import sqlite3
    try:
        db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2)
        try:
            row = db.execute("SELECT value FROM meta WHERE key = ?", (STORE_ID_META,)).fetchone()
        finally:
            db.close()
    except sqlite3.OperationalError as e:
        if "no such table" in str(e):
            return None
        raise CopyCheckFailed(f"{os.path.basename(home)}: {e}")
    except sqlite3.Error as e:
        raise CopyCheckFailed(f"{os.path.basename(home)}: {e}")
    return row[0] if row else None


def copy_pending(st: store.Store, home: str, db_path: str) -> bool:
    """For a reader that does not run the check (the dashboard reading another profile): the database records a
    home or a file that are not this one, so it was copied or moved and has not started since. Its tiers are not
    to be trusted, nor signed, until that profile starts."""
    salt, mark, fid = st.get_meta(SALT_META), st.get_meta(HOME_META), st.get_meta(FILE_META)
    try:
        return bool(salt and mark and fid) and (_home_mark(salt, os.path.realpath(home)) != mark
                                                or _file_id(db_path) != fid)
    except (OSError, ValueError):
        return True


def _check_copied(st: store.Store) -> None:
    """A record copied into another profile (``hermes profile create --clone-all``, the desktop's Duplicate Bot)
    must not carry earned autonomy over silently: the copy is another agent setup (its own SOUL, skills, tools).

    The database records a salted hash of its Hermes home, the identity of its file on disk and a random store id. A
    different file (a copy, not a rename) whose store id another profile of the same install still holds is a copy:
    a ``copy`` event is logged (replayed by passports), every type restarts as after a model change (half the
    series, provisional; strict mode: empty), the original's undo snapshots, pending asks, keys and exported files
    are dropped, and the copy gets ids of its own. A different file that no other profile claims moved (a restored
    backup): nothing changes. Raises when it cannot conclude (CopyCheckFailed, or any error: the transaction rolls
    back, file removals included); store_() then makes every action ask and tries again."""
    home = os.path.realpath(_hermes_home())
    fid = _file_id(st.path)
    salt, mark, sid, recorded_fid = (st.get_meta(k) for k in (SALT_META, HOME_META, STORE_ID_META, FILE_META))
    if salt and sid and mark == _home_mark(salt, home) and recorded_fid == fid:
        return
    copied = bool(sid and recorded_fid and recorded_fid != fid
                  and any(_store_id_at(h) == sid for h in _sibling_homes(home)))
    with st.transaction():
        # Another process (gateway, CLI, dashboard) may have settled it since the first read: decide again on what
        # the write lock shows, and never apply a stale decision twice.
        if st.get_meta(STORE_ID_META) != sid or (st.get_meta(FILE_META) == fid and recorded_fid != fid):
            return
        salt = st.get_meta(SALT_META) or secrets.token_hex(16)
        if copied:
            cfg = settings()
            sync_settings(st, cfg)
            strict = bool(cfg["strict"])
            st.log({"event": "copy", "mode": "strict" if strict else "carry"})
            for agent, s in st.states():
                st.put_state(agent, rule.carry_over(s, n_new=params.required_n(cfg["risks"], s.stakes), veto=False,
                                                    strict=strict))
            st.db.execute("UPDATE undo SET undone = 1 WHERE undone = 0")
            st.db.execute("DELETE FROM pending")
            st.db.execute("DELETE FROM meta WHERE key = ?", (UNDO_KEY,))
            st.set_meta(COPIED_META, str(time.time()))
            _drop_copied_files()                         # before the commit: a failure rolls everything back
        if copied or not sid:
            st.set_meta(STORE_ID_META, secrets.token_hex(16))
        st.set_meta(SALT_META, salt)
        st.set_meta(HOME_META, _home_mark(salt, home))
        st.set_meta(FILE_META, fid)


def _drop_copied_files() -> None:
    """In a copy: the original's signing key (a new one is made at the next passport), undo snapshots, and the
    passports and ledger exports it wrote."""
    import glob
    import shutil
    d = data_dir()
    undo_dir = os.path.join(d, "undo")
    if os.path.isdir(undo_dir):
        shutil.rmtree(undo_dir)
    for f in [os.path.join(d, passport.KEY_FILE)] + glob.glob(os.path.join(d, "passport-*.json")) \
            + glob.glob(os.path.join(d, "evidence-*.jsonl")):
        try:
            os.remove(f)
        except FileNotFoundError:
            pass


UNDO_KEY = "undo:hmac-key"


def undo_key(deadline: float | None = None) -> bytes:
    """The secret that signs undo snapshots (``undo``), kept in the tenure database's meta table: created once,
    never logged, never exported."""
    with _locked(deadline):
        st = store_()
        value = st.get_meta(UNDO_KEY)
        if value is None:
            insert = ("INSERT OR IGNORE INTO meta (key, value) VALUES (?, ?)", (UNDO_KEY, secrets.token_hex(32)))
            if st.db.in_transaction:                     # called inside txn() (undo_entry)
                st.db.execute(*insert)
            else:
                with st.transaction():
                    st.db.execute(*insert)
            value = st.get_meta(UNDO_KEY)
    return bytes.fromhex(value)


@contextmanager
def _locked(deadline: float | None = None):
    """This process's store lock, waited for at most LOCK_TIMEOUT seconds, and never past ``deadline`` (a
    time.monotonic() value), else LockTimeout."""
    wait = LOCK_TIMEOUT if deadline is None else min(LOCK_TIMEOUT, deadline - time.monotonic())
    if wait <= 0 or not ST.lock.acquire(timeout=wait):
        raise LockTimeout("tenure: the store stayed busy")
    try:
        yield
    finally:
        ST.lock.release()


@contextmanager
def txn(deadline: float | None = None):
    """The store inside one write transaction, one thread at a time: every write of a hook happens here."""
    with _locked(deadline):
        st = store_()
        _DEFERRED.depth = getattr(_DEFERRED, "depth", 0) + 1
        try:
            with st.transaction():
                yield st
        except BaseException:
            _DEFERRED.events = []                       # rolled back: nothing to tell
            raise
        finally:
            _DEFERRED.depth -= 1
        if _DEFERRED.depth == 0:
            events, _DEFERRED.events = getattr(_DEFERRED, "events", []), []
            for event, payload in events:               # committed: the desktop half reads the new state
                _push(event, payload)


def _config_setting(key, default=None):
    """One of this plugin's settings read from Hermes' config (``plugins.entries.tenure.settings``), for a process
    without the plugin context (the dashboard). Hermes' public ``hermes_cli.config``; the defaults when unreadable."""
    try:
        from hermes_cli import config as hermes_config
        node = hermes_config.load_config() or {}
        for part in ("plugins", "entries", PREFIX, "settings"):
            node = node[part]
        return node.get(key, default)
    except Exception:
        return default


def _get(key, default=None):
    if ST.ctx is None:
        return _config_setting(key, default)
    try:
        return ST.ctx.get_config(key, default)
    except Exception:
        return default


def _truthy(value) -> bool:
    return value is True or str(value).strip().lower() in ("1", "true", "yes", "on")


def parse_risk(value, default):
    """A risk from the owner's settings: 0.02, "2%", "1/50", or "cap" (always ask). Kept strictly between 0 and 1."""
    if value is None or str(value).strip().lower() in ("cap", "capped", "never", "none", "null", "always ask"):
        return None
    try:
        text = str(value).strip().replace(",", ".")
        if text.endswith("%"):
            v = float(text[:-1]) / 100
        elif "/" in text:
            a, b = text.split("/", 1)
            v = float(a) / float(b)
        else:
            v = float(text)
    except (ValueError, ZeroDivisionError):
        return default
    return v if 0 < v < 1 else default


def settings() -> dict:
    """The owner's settings: preset, risk per stakes level (None = capped), spot-check rate (strictly between 0 and
    1, else the default), strict mode, type overrides, enabled."""
    preset = str(_get("preset", params.DEFAULT_PRESET) or params.DEFAULT_PRESET).strip().lower()
    if preset not in params.PRESETS:
        preset = params.DEFAULT_PRESET
    risks = dict(params.PRESETS[preset])
    custom = _get("risks")
    if isinstance(custom, dict):
        for level in params.LEVELS:
            if level in custom:
                risks[level] = parse_risk(custom[level], risks[level])
    spot = parse_risk(_get("spot_check", params.DEFAULT_SPOT), params.DEFAULT_SPOT)
    overrides = _get("types")
    start = str(_get("start", params.DEFAULT_START) or params.DEFAULT_START).strip().lower()
    typed = _get("fields")                              # a mistyped block is reported by the vocabulary, then ignored
    raw_fields = typed if isinstance(typed, dict) else {}
    vocabulary = fields.load(raw_fields or (typed if typed not in (None, "") else None))
    return dict(vocabulary=vocabulary, fields=raw_fields, preset=preset, risks=risks,
                spot=params.DEFAULT_SPOT if spot is None else spot,
                strict=_truthy(_get("strict", False)), overrides=overrides if isinstance(overrides, dict) else {},
                enabled=_truthy(_get("enabled", True)),
                start=start if start in params.STARTS else params.DEFAULT_START)


def settings_event(cfg: dict) -> dict:
    """The settings as the ledger records them: what a replay needs to recompute the tiers."""
    return {"event": "settings", "risks": dict(cfg["risks"]), "spot": cfg["spot"], "strict": bool(cfg["strict"]),
            "start": cfg.get("start", "probation"), "rule": RULE}


def settings_fingerprint(cfg: dict) -> str:
    """The settings event plus the type overrides: changing an override is a settings change too."""
    types = {str(k): str(v) for k, v in (cfg.get("overrides") or {}).items()}
    vocab = cfg.get("vocabulary") or fields.load(cfg.get("fields") or None)
    resolved = {"entries": {n: sorted(e) for n, e in sorted(vocab.entries.items())}, "active": sorted(vocab.active),
                "stakes": dict(sorted(vocab.stakes.items())), "version": vocab.version}
    vhash = hashlib.sha256(json.dumps(resolved, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    text = json.dumps({**settings_event(cfg), "types": types, "vocabulary": vhash}, sort_keys=True,
                      separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sync_settings(st: store.Store, cfg: dict) -> list[dict]:
    """In a transaction, before any outcome: settings that differ from the last ones in the ledger are logged, then
    every type of every agent is re-evaluated under them (stricter settings can take a T3 back). Returns the derived
    events."""
    fp = settings_fingerprint(cfg)
    if st.get_meta("settings:fingerprint") == fp:
        return []
    st.log(settings_event(cfg))
    st.set_meta("settings:fingerprint", fp)
    events = []
    for agent, s in st.states():
        before = s.to_dict()
        for ev in rule.reevaluate(s, params.required_n(cfg["risks"], s.stakes)):
            st.log({**ev, "agent": agent})
            events.append({**ev, "agent": agent})
        if s.to_dict() != before:
            st.put_state(agent, s)
    return events


# ---------------------------------------------------------------------------------------------------- context
def _session_cwd() -> str:
    try:
        if ST.ctx is not None and hasattr(ST.ctx, "session_cwd"):
            cwd = ST.ctx.session_cwd()
            if cwd:
                return str(cwd)
    except Exception:
        pass
    return os.environ.get("TERMINAL_CWD") or os.getcwd()


def call_cwd(tool: str, args: dict, session_id="", task_id="") -> str:
    """The working directory a call runs in (R36): a terminal call's own ``workdir``, else the one the session's last
    command reported (followed in post_tool_call), else the session's cwd (``ctx.session_cwd()``). A `cd` approved
    in one call is still in force in the next."""
    with ST.mem:
        base = ST.cwds.get(str(session_id or task_id or ""), "")
    base = base or _session_cwd()
    workdir = args.get("workdir") if tool == "terminal" else None
    if isinstance(workdir, str) and workdir.strip():
        wd = os.path.expanduser(workdir.strip())
        return wd if os.path.isabs(wd) else os.path.join(base, wd)
    return base


def _follow_cwd(tool: str, args: dict, result, session_id="", task_id="") -> None:
    """After a terminal command: the cwd it reported (Hermes adds "cwd" to its result when the command changed it)
    becomes the session's, as Hermes records it; a per-call ``workdir`` never does."""
    if tool != "terminal" or args.get("workdir"):
        return
    data = result
    if isinstance(result, str):
        try:
            data = json.loads(result)
        except ValueError:
            return
    cwd = data.get("cwd") if isinstance(data, dict) else None
    if isinstance(cwd, str) and cwd.strip():
        with ST.mem:
            _remember(ST.cwds, str(session_id or task_id or ""), cwd.strip())


def anon(session_id) -> str:
    """A session as stored: sha256(session id)[:12]; "" without a session id, which counts as no session."""
    sid = str(session_id or "")
    return hashlib.sha256(sid.encode("utf-8")).hexdigest()[:12] if sid else ""


def agent_name(model, provider) -> str:
    return f"{model}@{provider or 'unknown'}"


def _remember(cache: OrderedDict, key: str, value) -> None:
    """Under ST.mem: one entry of a bounded in-memory map, the oldest dropped first."""
    cache[key] = value
    cache.move_to_end(key)
    while len(cache) > MAX_SESSIONS:
        cache.popitem(last=False)


def agent_of(session_id="", deadline: float | None = None) -> str:
    """The agent acting in a session: the model and provider of the session's latest API request in this process,
    else of this process's latest API request, else the profile's last active agent."""
    with ST.mem:
        agent = ST.agents.get(str(session_id or "")) or ST.last_agent
    if not agent:
        try:
            with _locked(deadline):
                agent = store_().get_meta("agent:last")
        except Exception:
            agent = None
    return agent or "unknown@unknown"


def _suspended(st: store.Store, session: str) -> bool:
    with ST.mem:
        since = ST.tainted.get(session)
    if not session:                         # outside any session: this process only, for SESSIONLESS_TAINT
        return since is not None and time.time() - since < SESSIONLESS_TAINT
    return since is not None or st.is_tainted(session)


def _taint(session: str) -> None:
    """Suspend a session: in this process at once, then in the store in a transaction of its own, so that nothing
    that fails later (or a busy store) can take it back. The empty session (calls outside any session) is never
    suspended as a whole: only in this process, for an hour."""
    with ST.mem:
        _remember(ST.tainted, session, time.time())
    if not session:
        return
    try:
        with txn() as st:
            st.taint(session)
    except Exception:
        log.warning("tenure: a suspension could not be stored; it holds in this process", exc_info=True)


def nobody_answers(session_id: str = "") -> str | None:
    """Why no person will answer an approval now, or None: --yolo, or a cron job (public signals only).

    Hermes calls post_approval_response only for a person's decision (or a smart-mode verdict, which carries
    decided_by): with --yolo, /yolo, approvals.mode off, a cron or single-query run, it settles the ask itself
    without the hook. This check matters for cron, where a spot check on a type acting alone would otherwise fall to
    cron_mode and fail the job."""
    if _truthy(os.environ.get("HERMES_YOLO_MODE", "")):
        return "--yolo"
    try:
        if ST.ctx is not None and ST.ctx.current_cron_execution() is not None:
            return "cron"
    except Exception:
        pass
    return None


def _profile_name() -> str:
    """The Hermes profile this process serves: ``profiles/<name>`` in its home, else ``default``."""
    try:
        home = os.path.realpath(_hermes_home())
        parent = os.path.basename(os.path.dirname(home))
        return os.path.basename(home) if parent == "profiles" else "default"
    except Exception:
        return "default"


_DEFERRED = threading.local()      # plugin events raised inside a transaction, sent once it commits


def _push(event: str, payload: dict | None = None) -> None:
    """Tell the desktop half, live (``plugin.tenure.<event>`` on Hermes' event stream): ``changed`` after any
    outcome, ``acted`` when an act-then-notify action ran and can be undone. A process with no Desktop client
    (cron, ``hermes chat``) has nobody to tell: Hermes logs a no-op."""
    if getattr(_DEFERRED, "depth", 0) > 0:
        _DEFERRED.events = getattr(_DEFERRED, "events", []) + [(event, payload)]
        return
    try:
        from hermes_cli.plugin_events import broadcast_plugin_event
        broadcast_plugin_event("tenure", event, payload or {})
    except Exception:
        log.debug("tenure: plugin event %s not sent", event, exc_info=True)


class Acted(str):
    """An "acted, then told you" line: actions of one type in one turn share one message, edited in place."""
    def __new__(cls, text: str, session: str, type_key: str, undo_id: int):
        obj = super().__new__(cls, text)
        obj.session, obj.type_key, obj.undo_id = session, type_key, undo_id
        return obj


ACTED_WINDOW = 600.0            # seconds: without an end-of-turn signal, a later action starts a new message


def _ids(ids: list[int]) -> str:
    return f"{ids[0]}–{ids[-1]}" if ids == list(range(ids[0], ids[-1] + 1)) else ", ".join(map(str, ids))


def _announce(text: str) -> None:
    try:
        if ST.ctx is None or not hasattr(ST.ctx, "post_message"):
            return
        if isinstance(text, Acted):
            key, now = (text.session, text.type_key), time.time()
            with ST.mem:
                entry = ST.acted.get(key)
                if entry and now - entry["at"] < ACTED_WINDOW and callable(getattr(entry["handle"], "edit", None)):
                    entry["ids"].append(text.undo_id)
                    entry["at"] = now
                    ids = entry["ids"]
                    grouped = tr("settle.acted_many", type=text.type_key, n=len(ids), command="/tenure undo",
                                 id=ids[-1], ids=_ids(ids))
                    entry["handle"].edit(grouped)
                    return
            handle = ST.ctx.post_message(str(text))
            with ST.mem:
                ST.acted[key] = {"ids": [text.undo_id], "handle": handle, "at": now}
            return
        ST.ctx.post_message(text)
    except Exception:
        log.debug("tenure: post_message failed", exc_info=True)


def post_llm_call(session_id="", **kwargs):
    """The turn ended: the next acted action of a type starts a new message."""
    try:
        session = anon(session_id or kwargs.get("task_id") or "")
        with ST.mem:
            for key in [k for k in ST.acted if k[0] == session or not session_id]:
                del ST.acted[key]
    except Exception:
        log.debug("tenure: post_llm_call failed", exc_info=True)
    return None


def _purge() -> None:
    """Delete undo snapshots past their 24-hour window, at most once an hour per process."""
    now = time.time()
    if now - ST.purged_at < PURGE_EVERY:
        return
    ST.purged_at = now
    try:
        undo.purge(data_dir())
    except Exception:
        log.debug("tenure: undo purge failed", exc_info=True)


def _say(events: list[dict], spot: float) -> list[str]:
    """Plain announcements for the owner: tier changes, trials, confirmed carry-overs."""
    out = []
    for ev in events:
        t, kind, reason = ev.get("type"), ev.get("event"), ev.get("reason")
        if kind == "tier" and reason == "stakes":
            out.append(tr("notice.tier.stakes", type=t, stakes=stakes_name(ev.get("stakes"))))
        elif kind == "tier" and reason == "series":
            out.append(tr("notice.tier.series", type=t, spot=round(1 / spot),
                          successes=tr("notice.count.successes_in_a_row", n=ev.get("required")),
                          sessions=tr("notice.count.sessions", n=ev.get("sessions"))))
        elif kind == "tier" and reason == "wald":
            out.append(tr("notice.tier.wald", type=t))
        elif kind == "tier" and reason == "fault" and ev.get("from") == "trusted":
            out.append(tr("notice.trust.lost", type=t))
        elif kind == "tier" and reason == "fault" and ev.get("to") == rule.T1:
            out.append(tr("notice.tier.fault_probation", type=t))
        elif kind == "tier" and reason in ("fault", "settings"):
            out.append(tr(f"notice.tier.{reason}", type=t, tier=_tier_long(ev.get("to"))))
        elif kind == "trial" and reason == "fault":
            out.append(tr("notice.trial.fault", type=t, n=ev.get("left")))
        elif kind == "trial" and reason == "passed":
            out.append(tr("notice.trial.passed", type=t))
        elif kind == "trial" and reason == "failed":
            out.append(tr("notice.trial.failed", type=t, n=ev.get("wait")))
        elif kind == "trial" and reason == "wait over":
            out.append(tr("notice.trial.wait_over", type=t, n=ev.get("left")))
        elif kind == "confirmed":
            out.append(tr("notice.confirmed", type=t))
    return out


# ----------------------------------------------------------------------------------------------------- record
def outcome(choice, decided_by=None) -> str:
    """approved / refused / neutral. Timeouts, cancellations, transport failures and answers given by a model
    (smart approvals) are not the owner's judgement and count for nothing."""
    c = str(choice or "").strip().lower()
    if decided_by and str(decided_by).strip().lower() not in ("human", "user", "owner", "person"):
        return "neutral"
    if c.startswith("smart"):
        return "neutral"
    if c in ("once", "session", "always", "approve", "approved", "yes", "allow"):
        return "approved"
    if c in ("deny", "denied", "no", "reject", "rejected"):
        return "refused"
    return "neutral"


def record_outcome(st: store.Store, cfg: dict, *, agent: str, type_key: str, stakes: str, reversible: bool,
                   result: str, source: str, session: str = "") -> list[dict]:
    """Apply one outcome to an agent's type and log it, in a transaction, after ``sync_settings``: first the input
    event a replay reads, then the rule's derived events. The one way an outcome reaches the record (hooks, CLI,
    dashboard). After the outcome of an action that ran, the wait after a failed trial counts it (``store.COUNTED``),
    except for the fault that failed the trial. Returns the derived events."""
    if source not in store.OUTCOME_SOURCES.get(result, ()):
        raise ValueError(f"tenure: unknown outcome {result!r} from {source!r}")
    recorded = st.recorded(agent, type_key)
    s = st.get_state(agent, type_key, stakes, reversible)
    n = params.required_n(cfg["risks"], stakes)
    rebased = rule.rebase(s) if recorded is not None and recorded.stakes != stakes else []
    was_trusted = trusted(cfg, s, n, stakes)
    if result == "success" and was_trusted:
        events = rule.on_trusted_success(s, source=source)
    elif result == "success":
        events = rule.on_success(s, n, session=session, source=source)
    elif result == "fault":
        events = rule.on_fault(s, n, session=session, source=source)
    else:
        events = rule.on_neutral(s, source)
    failed_trial = any(ev["event"] == "trial" and ev.get("reason") == "failed" for ev in events)
    if was_trusted and result == "fault" and not any(ev["event"] == "tier" for ev in events):
        events.insert(0, {"event": "tier", "type": type_key, "stakes": stakes, "from": "trusted", "to": s.tier,
                          "reason": "fault"})                # the trusted start ends: the study rule applies now
    events = rebased + events
    if (result, source) in store.COUNTED and not failed_trial:
        events += rule.count_action(s)
    st.put_state(agent, s)
    if result == "fault":
        st.distrust(type_key)
    st.log({"event": "outcome", "agent": agent, "type": type_key, "stakes": stakes, "reversible": bool(reversible),
            "result": result, "source": source, "session": session})
    for ev in events:
        st.log({**ev, "agent": agent})
    _push("changed", {"agent": agent, "type": type_key})      # sent when the transaction commits
    return events


UNDO_WINDOW = 24 * 3600          # seconds an act-then-notify action can be undone


class UndoMessage(str):
    """The owner's message about an undo; ``ok`` is False when nothing was undone (a refusal or a failure).
    ``cleanup()`` deletes the restored snapshot: call it after the transaction that ran ``undo_entry`` has committed."""
    ok = True
    snap_id: str | None = None

    def __new__(cls, text: str, ok: bool = True, snap_id: str | None = None):
        self = super().__new__(cls, text)
        self.ok, self.snap_id = ok, snap_id
        return self

    def cleanup(self) -> None:
        if self.snap_id:
            undo.discard(self.snap_id, data_dir())
            self.snap_id = None


def undo_entry(st: store.Store, id: int) -> UndoMessage:
    """Revert one act-then-notify action (files back to their snapshot) and count it as a fault of its type, unless
    its automatic check already did. The one implementation, used by the CLI, the slash command and the dashboard.
    Call it inside ``txn()``, then call ``cleanup()`` on the result once the transaction has committed: the snapshot
    is only deleted then, so a failure before the commit leaves the action retryable. Returns a message (a ``str``
    whose ``ok`` is False when nothing was undone). A partial restore marks nothing undone and records no fault: the
    snapshot is kept, so the owner can try again. The settings are the configured ones, synced into the ledger."""
    entry = st.get_undo(id)
    if entry is None:
        return UndoMessage(tr("undo.missing", id=id), False)
    if entry["undone"]:
        return UndoMessage(tr("undo.already", id=id), False)
    if time.time() - entry["at"] > UNDO_WINDOW:
        return UndoMessage(tr("undo.expired", id=id, n=UNDO_WINDOW // 3600), False)
    if not entry["snap_id"]:
        return UndoMessage(tr("undo.no_snapshot", id=id), False)
    try:
        restored, failed = undo.restore(entry["snap_id"], data_dir(), keep=True, key=undo_key())
    except undo.Refused as e:
        return UndoMessage(tr("undo.refused", id=id, reason=e), False)
    if failed:
        return UndoMessage(tr("undo.partial", id=id, n=failed, restored=restored), False)
    if restored == 0:
        return UndoMessage(tr("undo.gone", id=id), False)
    agent, key = entry["agent"], entry["type"]
    st.mark_undone(id)
    if entry["fault"]:
        return UndoMessage(tr("undo.done_already_fault", id=id, type=key), True, entry["snap_id"])
    recorded = st.recorded(agent, key)
    stakes, reversible = (recorded.stakes, recorded.reversible) if recorded else ("medium", True)
    cfg = settings()
    sync_settings(st, cfg)
    events = record_outcome(st, cfg, agent=agent, type_key=key, stakes=stakes, reversible=reversible,
                            result="fault", source="undo")
    st.bump(agent, "faults")
    s = st.get_state(agent, key, stakes, reversible)
    text = "\n\n".join([tr("undo.done", id=id, type=key, agent=agent, tier=tier_name(s.tier))]
                       + _say(events, cfg["spot"]))       # e.g. "On probation" when it ends the trusted start
    return UndoMessage(text, True, entry["snap_id"])


def _bump(st: store.Store, agent: str, result: str, *, checked: bool = False, alone: bool = False) -> None:
    """Counters, one outcome at a time: every action; checked by a person; acted on its own; faults."""
    st.bump(agent, "actions")
    if checked:
        st.bump(agent, "checked")
    if alone:
        st.bump(agent, "alone")
    if result == "fault":
        st.bump(agent, "faults")


def _expire(st: store.Store, cfg: dict) -> list[dict]:
    """Pending rows older than 24 hours (an ask nobody answered, a call that never reported back): neutral, and never
    a success."""
    events = []
    for p in st.expire_pending():
        events += record_outcome(st, cfg, agent=p["agent"], type_key=p["type"], stakes=p["stakes"],
                                 reversible=p["reversible"], result="neutral", source="expired",
                                 session=p["session"])
        _bump(st, p["agent"], "neutral")
    return events


def _carry(st: store.Store, cfg: dict, old: str, new: str) -> str:
    """The new agent's record, made from the previous agent's (``rule.carry_over``), with its ``agent`` ledger event.
    Returns the announcement."""
    strict = bool(cfg["strict"])
    old_model, new_model = personal.split_agent(old)[0], personal.split_agent(new)[0]
    have = {s.key for _, s in st.states(new)}
    carried = reset = kept = trusting = 0
    vetoed = []
    for _, s in st.states(old):
        if s.key in have:                    # the new agent's own evidence on a type is never overwritten
            kept += 1
            continue
        n_new = params.required_n(cfg["risks"], s.stakes)
        eligible = not strict and s.stakes != "high" and n_new is not None
        veto = eligible and benchmarks.veto(old_model, new_model, s.key)
        made = rule.carry_over(s, n_new=n_new, veto=veto, strict=strict)
        st.put_state(new, made)
        if veto:
            vetoed.append(s.key)
        elif eligible and (made.provisional > 0 or made.wald < 0):
            carried += 1
        elif trusted(cfg, made, n_new, made.stakes):
            trusting += 1                    # nothing earned to carry: it keeps the trusted start
        else:
            reset += 1
    st.log({"event": "agent", "old": old, "new": new, "mode": "strict" if strict else "carry", "vetoed": vetoed})
    parts = [tr("carry.new_agent", new=new, old=old, carried=carried, reset=reset, vetoed=len(vetoed))]
    if kept:
        parts.append(tr("carry.kept", n=kept))
    if trusting:
        parts.append(tr("carry.trusted", n=trusting))
    if strict:
        parts.append(tr("carry.strict"))
    elif carried:
        parts.append(tr("carry.carried"))
    return " ".join(parts)


# --------------------------------------------------------------------------------------------------- decision
def _earned(recorded: rule.TypeState | None, act, s: rule.TypeState, n, decision: str) -> bool:
    """Decision-time guard; it changes no state. A decision that lets the call run (NOTIFY, ALLOW, SPOT) stands only
    when the record was earned at the call's own stakes and meets today's requirement: the series length and two
    sessions for T3, the middle tier's score at these stakes for T2. Anything else asks."""
    if decision == rule.ASK:
        return True
    if recorded is None or recorded.stakes != act.stakes:
        return False
    if decision == rule.NOTIFY:
        return bool(act.reversible and act.stakes in params.WALD
                    and s.wald <= params.wald_steps(act.stakes)[2] + rule.TOL)
    return n is not None and s.series >= rule.required(s, n) and len(s.sessions) >= rule.SESSIONS


def trusted(cfg: dict, s: rule.TypeState, n, stakes: str) -> bool:
    """The trusted start covers the type (``rule.trusted``) at these stakes. Such a type asks nothing Hermes alone
    would not ask; its first fault puts it under the study rule."""
    return s.stakes == stakes and rule.trusted(s, n, cfg.get("start"))


def _decide(st: store.Store, agent: str, act, n, cfg: dict, session: str, nobody, rng):
    """(recorded state, state at today's stakes, decision, suspended) for one call."""
    recorded = st.recorded(agent, act.type)
    s = st.get_state(agent, act.type, act.stakes, act.reversible)
    suspended = _suspended(st, session)
    decision = rule.decide(s, n, cfg["spot"], suspended=suspended, rng=rng)
    if nobody and decision == rule.SPOT:
        decision = rule.ALLOW                           # nobody can answer a spot check: the earned tier runs
    if not _earned(recorded, act, s, n, decision) or ST.copy_unchecked:
        decision = rule.ASK                             # copy_unchecked: this record may be a copy, not yet settled
    if (decision == rule.ASK and not ST.copy_unchecked and trusted(cfg, s, n, act.stakes)
            and (not suspended or (act.reversible and act.type.startswith("file:")))):
        decision = rule.WATCH                           # after outside content: undoable file writes only                           # trusted start: run as Hermes would, with an undo if possible
    if decision != rule.ASK and _held_by(st, agent, act.type):
        decision = rule.ASK                             # a sensitive kind waits while its tool's fault is unredeemed
    return recorded, s, decision, suspended


def _marked(s: rule.TypeState | None) -> bool:
    """A recorded type with a fault not yet redeemed: on trial, waiting after a failed trial, lengthened (a medium or
    high fault, cleared on the way back to T3), or faulted and not back at T3 (a low fault sets no trial, wait or
    lengthening; it clears the same way). Never the permanent marks (unresolved_fault, distrusted): those would hold a
    sensitive kind for life."""
    return s is not None and (s.trial_left > 0 or s.trial_wait > 0 or s.lengthened
                              or (s.faults > 0 and s.tier != rule.T3))


def _held_by(st: store.Store, agent: str, type_key: str) -> str | None:
    """The first marked type linked to a category type, or None: its parent first, then every other recorded type of
    the same parent whose categories overlap, in key order. Read only: nothing is written on the linked types, and
    ``st.recorded`` never fabricates a state the way ``get_state`` does."""
    parent = fields.parent_of(type_key)
    if parent is None:
        return None
    if _marked(st.recorded(agent, parent)):
        return parent
    cats = fields.categories_of(type_key)
    for k, s in sorted(((s.key, s) for a, s in st.states(agent) if a == agent), key=lambda kv: kv[0]):
        if k != type_key and fields.parent_of(k) == parent and fields.categories_of(k) & cats and _marked(s):
            return k
    return None


def _uncovered_local(act, s: rule.TypeState, n) -> bool:
    """A local action the trusted start does not cover (rm, mv, cp, a heredoc...), at low or medium stakes, never
    faulted: the owner may allow it for the session. Not what leaves the machine (high), not a type on probation."""
    return (act.stakes in ("low", "medium") and n is not None and not s.faults and not s.distrusted
            and not s.trial_left and not s.trial_wait and not rule.trust_covers(act.type))


def _to_t2(s: rule.TypeState) -> int:
    """Verified successes the type still needs to act again, then tell (the middle tier's Wald score)."""
    a, step, ln_b = params.wald_steps(s.stakes)
    w, k = s.wald, 0
    while w > ln_b + rule.TOL and k < 1000:
        w, k = max(w + step, ln_b - a), k + 1
    return max(k, 1)


def _ask_message(act, s: rule.TypeState, n, spot: float, *, decision: str, suspended: bool, unsaved: bool,
                 earned_at: str | None, per_session: bool = False, trusted_start: bool = False,
                 held: str | None = None) -> str:
    stakes = stakes_name(act.stakes)
    if decision == rule.SPOT:
        return tr("ask.spot", summary=act.summary, type=act.type, spot=round(1 / spot))
    if n is None:
        why = tr("ask.why.capped", type=act.type, stakes=stakes, n=s.successes)
    elif suspended:
        why = tr("ask.why.suspended_trusted" if trusted_start else "ask.why.suspended")
    elif s.trial_left:
        why = tr("ask.why.trial", type=act.type, n=s.trial_left)
    elif s.trial_wait:
        why = tr("ask.why.trial_wait", type=act.type, n=s.trial_wait)
    elif earned_at and earned_at != act.stakes:
        why = tr("ask.why.other_stakes", type=act.type, earned=stakes_name(earned_at), stakes=stakes)
    elif unsaved:
        why = tr("ask.why.unsaved", type=act.type)
    elif held:                                          # before the trusted start's own reasons: name what holds it
        why = tr("ask.why.held", type=act.type, held=held)
    elif trusted_start and _uncovered_local(act, s, n):
        why = tr("ask.why.untrusted", type=act.type, stakes=stakes)
    elif s.tier == rule.T1 and s.faults and act.reversible and act.stakes in params.WALD:
        why = tr("ask.why.climb", type=act.type, stakes=stakes, n=_to_t2(s))   # the next step, not the far one
    else:
        why = tr("ask.why.series", type=act.type, stakes=stakes, series=s.series, required=rule.required(s, n),
                 sessions=len(s.sessions), needed=rule.SESSIONS)
        if s.provisional:
            why += " " + tr("ask.why.provisional", n=s.provisional)
    if per_session:
        return tr("ask.prompt_session", summary=act.summary, why=why)
    return tr("ask.prompt", summary=act.summary, why=why)


# Seconds: Hermes runs a longer terminal call in the background (its TERMINAL_MAX_FOREGROUND_TIMEOUT default).
FOREGROUND_MAX = 600


BACKGROUND_KEYS = ("auto_backgrounded", "promoted_from_foreground")   # Hermes' markers in a terminal result


def _background(tool: str, args: dict, result=None) -> bool:
    """A terminal call Hermes runs in the background: its result is a launch, not the command's outcome. Asked for
    (``background``), promoted (a timeout over Hermes' foreground cap), or decided by Hermes itself (a trailing `&`
    turned into a background run): the result then carries ``auto_backgrounded`` or ``promoted_from_foreground``,
    or says "Background process started"."""
    if tool != "terminal":
        return False
    if _truthy(args.get("background")):
        return True
    try:
        data = json.loads(result) if isinstance(result, (str, bytes)) else result
    except ValueError:
        data = None
    if isinstance(data, dict) and (any(k in data for k in BACKGROUND_KEYS)
                                   or str(data.get("output") or "").startswith("Background process started")):
        return True
    try:
        limit = int(os.environ.get("TERMINAL_MAX_FOREGROUND_TIMEOUT", FOREGROUND_MAX))
        return int(args.get("timeout") or 0) > limit
    except (TypeError, ValueError):
        return False


def _settle(st: store.Store, cfg: dict, p: dict, *, blocked: bool, failed: bool, reason: str | None,
            launched: bool = False) -> list[str]:
    """The verified outcome of one pending decision, from facts gathered before the transaction: was the call stopped
    (``blocked``), did the tool fail, what did the automatic check of the written files say. The check judges every
    action that ran, even one nobody answered. A background launch (``launched``) is neutral: the command's own
    outcome is not known when the call returns. Returns the owner's messages."""
    phase, agent, key = p["phase"], p["agent"], p["type"]
    acted = phase in ("notify", "unwatched")                # T2 acted, then told the owner (who may not be there)
    decided = acted or phase in ("approved", "alone")       # approved by a person, or run by an earned tier
    spot = phase == "approved" and p["decision"] == rule.SPOT
    if blocked:                                             # never ran
        result_source = ("neutral", "blocked" if decided else "nobody")
    elif failed:
        result_source = ("neutral", "error" if decided else "nobody")
    elif launched:
        result_source = ("neutral", "background")
    elif reason:
        result_source = ("fault", "spot" if spot else "check")
    elif phase == "approved":
        result_source = ("success", "spot" if spot else "approval")
    elif phase == "notify":
        result_source = ("success", "notify")
    elif phase == "unwatched":                              # T2 acted under cron or --yolo: nobody could undo it
        result_source = ("neutral", "nobody")
    elif phase == "alone":
        result_source = ("neutral", "alone")
    else:                                                   # nobody answered (cron, yolo, approvals off), or no hook
        result_source = ("neutral", "nobody")
    if p["decision"] == rule.WATCH and result_source[0] == "success":
        now = st.get_state(agent, key, p["stakes"], p["reversible"])
        if not trusted(cfg, now, params.required_n(cfg["risks"], p["stakes"]), p["stakes"]):
            result_source = ("neutral", "alone")            # trusted when it ran, not now (start changed): no credit
    events = record_outcome(st, cfg, agent=agent, type_key=key, stakes=p["stakes"], reversible=p["reversible"],
                            result=result_source[0], source=result_source[1], session=p["session"])
    _bump(st, agent, result_source[0], checked=phase == "approved",
          alone=not blocked and (acted or phase == "alone"))
    posts = []
    if acted and not blocked and not failed:    # the files were written: the owner can revert them
        undo_id = st.add_undo(agent, key, p["snap_id"], fault=bool(reason))
        _push("acted", {"agent": agent, "type": key, "undo_id": undo_id, "fault": bool(reason),
                        "profile": _profile_name()})
        if reason:
            posts.append(tr("settle.acted_fault", type=key, reason=reason, command="/tenure undo", id=undo_id))
        else:
            posts.append(Acted(tr("settle.acted", type=key, command="/tenure undo", id=undo_id), p["session"], key,
                               undo_id))
    elif reason:
        posts.append(tr("settle.check_failed", type=key, reason=reason))
    return posts + _say(events, cfg["spot"])


# ------------------------------------------------------------------------------------------------------ hooks
def pre_api_request(model="", provider="", session_id="", **kwargs):
    """Which agent acts. An agent this profile has never seen inherits the record of the agent before it (the
    session's previous one, else the profile's last one): ``_carry``."""
    try:
        if not model:
            return None
        sid = str(session_id or kwargs.get("task_id") or "")
        agent = agent_name(model, provider)
        with ST.mem:
            prev = ST.agents.get(sid)
            _remember(ST.agents, sid, agent)
            if prev == agent and ST.last_agent == agent:
                return None
        cfg = settings()
        posts = []
        with txn() as st:
            last = st.get_meta("agent:last")
            if last != agent:
                st.set_meta("agent:last", agent)
            if st.get_meta(f"agent:known:{agent}") is None:
                st.set_meta(f"agent:known:{agent}", "1")
                old = prev if prev and prev != agent else last
                if old and old != agent and st.states(old):
                    posts += _say(sync_settings(st, cfg), cfg["spot"])
                    posts.append(_carry(st, cfg, old, agent))
        with ST.mem:
            ST.last_agent = agent
        for text in posts:
            _announce(text)
    except LockTimeout:
        log.warning("tenure: pre_api_request skipped: the store stayed busy")
    except Exception:
        log.exception("tenure: pre_api_request failed")
    return None


def pre_tool_call(tool_name="", args=None, session_id="", tool_call_id="", task_id="", **kwargs):
    """The decision for one call: None to let it run (free, acting alone, or acting then notifying with its files
    saved), else Hermes' approval gate with a rule key that ends with a fresh uuid. Any internal error, a busy store
    included, asks, unless the call was already classified free. Every call that reaches the record first expires
    stale pending rows. Files are saved before the transaction, and the decision is checked again inside it."""
    act, taken = None, None
    deadline = time.monotonic() + HOOK_BUDGET
    try:
        cfg = settings()
        if not cfg["enabled"]:
            return None
        tool, args = str(tool_name or ""), (args if isinstance(args, dict) else {})
        cwd = call_cwd(tool, args, session_id, task_id)
        act = classify.classify(tool, args, cwd=cwd, overrides=cfg["overrides"], vocabulary=cfg["vocabulary"])
        if act.stakes == classify.FREE:
            return None
        _purge()
        uid = uuid.uuid4().hex
        if act.stakes == classify.CAP:
            return {"action": "approve", "rule_key": f"{PREFIX}:cap:{act.type}:{uid}",
                    "message": tr("ask.capped", summary=act.summary, type=act.type)}
        call, sid = str(tool_call_id or ""), str(session_id or task_id or "")
        session, agent, nobody = anon(sid), agent_of(sid, deadline), nobody_answers()
        n = params.required_n(cfg["risks"], act.stakes)
        if call:                                            # an undo is only wired through a call id
            with _locked(deadline):
                preview = _decide(store_(), agent, act, n, cfg, session, nobody, _NoSpot)[2]
            if preview in (rule.NOTIFY, rule.WATCH):
                paths = classify.files_written(tool, args, cwd)
                taken = (undo.snapshot(paths, data_dir(), key=undo_key(deadline), cwd=cwd,
                                       home=os.path.expanduser("~")) if paths else None)
        posts, directive, snap = [], None, taken
        with txn(deadline) as st:
            posts += _say(sync_settings(st, cfg), cfg["spot"])
            posts += _say(_expire(st, cfg), cfg["spot"])
            recorded, s, decision, suspended = _decide(st, agent, act, n, cfg, session, nobody, ST.rng)
            watched = decision == rule.WATCH
            if watched:                                     # files saved: act then tell, with an undo; else run alone
                files = bool(snap) or bool(classify.files_written(tool, args, cwd))
                decision = (rule.NOTIFY if snap else rule.ASK if suspended   # suspended: never without an undo
                            else rule.NOTIFY if files else rule.ALLOW)    # files that could not be saved: ask (below)
            if decision != rule.NOTIFY:
                snap = None                                 # the record changed since the preview: no undo needed
            unsaved = decision == rule.NOTIFY and snap is None
            if unsaved:
                decision = rule.ASK                         # no undo can be prepared: ask instead
            row = dict(call=call, agent=agent, type=act.type, stakes=act.stakes, reversible=act.reversible,
                       decision=rule.WATCH if watched and decision in (rule.ALLOW, rule.NOTIFY) else decision,
                       session=session)
            if decision in (rule.ALLOW, rule.NOTIFY):
                st.add_pending(uid, phase="alone" if decision == rule.ALLOW else "unwatched" if nobody else "notify",
                               rule_key="",
                               snap_id=snap, **row)
            else:
                kind = ("ask" if nobody else "spot" if decision == rule.SPOT else "capped" if n is None
                        else "trial" if s.trial_left or s.trial_wait else "ask")
                # Under the trusted start, an ask for inline code, or one only the suspension causes, has a key stable
                # for the session: "Allow for this session" then covers that type until the session ends.
                # A file change whose files could not be saved is asked about each time: a session answer must
                # never let a write run without its undo.
                no_undo = act.reversible and not snap and bool(classify.files_written(tool, args, cwd))
                per_session = (cfg.get("start") == "trusted" and not nobody and decision == rule.ASK and not no_undo
                               and fields.parent_of(act.type) is None           # never for a category kind
                               and (act.type in params.SESSION_TYPES or (suspended and trusted(cfg, s, n, act.stakes))
                                    or _uncovered_local(act, s, n)))
                # After outside content, one session answer covers every covered type (one key for the session);
                # inline code and uncovered local commands are allowed one type at a time.
                scope = ("suspended" if suspended and trusted(cfg, s, n, act.stakes) and act.type not in params.SESSION_TYPES
                         else act.type)
                key = f"{PREFIX}:session:{scope}:{session}" if per_session else f"{PREFIX}:{kind}:{act.type}:{uid}"
                st.add_pending(uid, phase="nobody" if nobody else "asked", rule_key=key, **row)
                directive = {"action": "approve", "rule_key": key,
                             "message": _ask_message(act, s, n, cfg["spot"], decision=decision, suspended=suspended,
                                                     unsaved=unsaved, per_session=per_session, trusted_start=cfg.get("start") == "trusted",
                                                     earned_at=recorded.stakes if recorded else None,
                                                     held=_held_by(st, agent, act.type))}
        if taken and taken != snap:
            undo.discard(taken, data_dir())
        taken = None
        for text in posts:
            _announce(text)
        return directive
    except Exception as e:
        log.exception("tenure: pre_tool_call failed")
        if taken:
            undo.discard(taken, data_dir())
        if act is not None and act.stakes == classify.FREE:
            return None
        return {"action": "approve", "rule_key": f"{PREFIX}:ask:{act.type if act else 'unknown'}:{uuid.uuid4().hex}",
                "message": tr("ask.internal_error", error=type(e).__name__)}


def post_approval_response(pattern_key="", tool_call_id="", choice="", **kwargs):
    """The owner's answer to one of our asks, found by its rule key (which ends with the pending row's id), else by
    the session and the tool call id. A refusal is a fault; an approval waits for the execution (post_tool_call);
    anything else (a timeout, a cancellation, a model's answer) teaches nothing. Answers to other prompts, even for
    the same call, are ignored."""
    try:
        raw = str(pattern_key or "")
        mine = raw.startswith(f"plugin_rule:{PREFIX}:")
        key, call = (raw[len("plugin_rule:"):] if mine else ""), str(tool_call_id or "")
        session = anon(kwargs.get("session_id") or kwargs.get("session_key"))
        if not key and not (call and session):
            return None
        cfg = settings()
        posts = []
        with txn() as st:
            p = (st.get_pending(key.rsplit(":", 1)[1]) if key and not key.startswith(f"{PREFIX}:session:")
                 else st.find_pending(session, call))
            verdict = outcome(choice, kwargs.get("decided_by"))
            if raw and not mine:
                # Hermes' own prompt on a call tenure let through (trusted start or an earned tier): a person's
                # refusal is a fault of the type; anything else stays with the call's own outcome.
                if p is None or p["phase"] not in ("alone", "notify") or verdict != "refused":
                    return None
                st.pop_pending(p["id"])
                if p.get("snap_id"):
                    undo.discard(p["snap_id"], data_dir())
                posts += _say(sync_settings(st, cfg), cfg["spot"])
                posts += _say(record_outcome(st, cfg, agent=p["agent"], type_key=p["type"], stakes=p["stakes"],
                                             reversible=p["reversible"], result="fault", source="refusal",
                                             session=p["session"]), cfg["spot"])
                _bump(st, p["agent"], "fault")
                p = None
            if p is None or p["phase"] != "asked" or (key and p["rule_key"] != key):
                pass                                        # not one of our open asks
            elif verdict == "approved":
                st.set_phase(p["id"], "approved")
            else:
                st.pop_pending(p["id"])
                posts += _say(sync_settings(st, cfg), cfg["spot"])
                if verdict == "refused":
                    result, source = "fault", ("spot" if p["decision"] == rule.SPOT else "refusal")
                else:
                    result, source = "neutral", "timeout"
                posts += _say(record_outcome(st, cfg, agent=p["agent"], type_key=p["type"], stakes=p["stakes"],
                                             reversible=p["reversible"], result=result, source=source,
                                             session=p["session"]), cfg["spot"])
                _bump(st, p["agent"], result)
        for text in posts:
            _announce(text)
    except LockTimeout:
        log.warning("tenure: post_approval_response skipped: the store stayed busy")
    except Exception:
        log.exception("tenure: post_approval_response failed")
    return None


def post_tool_call(tool_name="", args=None, result=None, session_id="", tool_call_id="", status=None,
                   error_type=None, task_id="", **kwargs):
    """After the call. A session that read external content, or ran code, is suspended first, in a transaction of its
    own. Then the pending decision of this call in this session is settled once, from the execution status and the
    automatic check of the written files, both gathered before the transaction."""
    try:
        tool, args = str(tool_name or ""), (args if isinstance(args, dict) else {})
        cwd = call_cwd(tool, args, session_id, task_id)
        _follow_cwd(tool, args, result, session_id, task_id)
        session = anon(session_id or task_id)
        if tool == "execute_code" or classify.reads_external(tool, args, cwd):
            with ST.mem:
                first = session not in ST.tainted
            _taint(session)
            if first and settings().get("start") == "trusted":
                _announce(tr("notice.suspended"))           # said once: the asks that follow stay short
        call = str(tool_call_id or "")
        if not call:
            return None
        with _locked():
            rows = store_().pending_rows(session, call)
        if not session and rows:            # outside any session, call ids recur: the type must match too
            cfg2 = settings()
            kind = classify.classify(tool, args, cwd=cwd, overrides=cfg2["overrides"],
                                     vocabulary=cfg2["vocabulary"]).type
            rows = [r for r in rows if r["type"] == kind]
            if len(rows) > 1:
                _ambiguous(rows)
                return None
        if not rows:
            return None
        p = rows[0]
        blocked = str(status or "").strip().lower() == "blocked"
        failed = not blocked and proofs.execution(tool, status, error_type, result) == "failed"
        launched = not blocked and not failed and _background(tool, args, result)
        reason = None
        if not blocked and not failed and not launched:
            paths = classify.files_written(tool, args, cwd)
            reason = proofs.check_files(paths) if paths else None
        cfg = settings()
        posts = []
        with txn() as st:
            p = st.pop_pending(p["id"])                         # settled once, by whoever comes first
            if p is not None:
                posts += _say(sync_settings(st, cfg), cfg["spot"])
                posts += _settle(st, cfg, p, blocked=blocked, failed=failed, reason=reason, launched=launched)
        for text in posts:
            _announce(text)
    except LockTimeout:
        log.warning("tenure: post_tool_call skipped: the store stayed busy")
    except Exception:
        log.exception("tenure: post_tool_call failed")
    return None


def _ambiguous(rows: list[dict]) -> None:
    """Several live rows outside any session for one call id and type: none can be told apart, so none is settled as
    a success; each is recorded as neutral."""
    cfg, posts = settings(), []
    with txn() as st:
        posts += _say(sync_settings(st, cfg), cfg["spot"])
        for r in rows:
            if st.pop_pending(r["id"]) is not None:
                record_outcome(st, cfg, agent=r["agent"], type_key=r["type"], stakes=r["stakes"],
                               reversible=r["reversible"], result="neutral", source="ambiguous", session=r["session"])
                _bump(st, r["agent"], "neutral")
    for text in posts:
        _announce(text)


def subagent_start(parent_session_id="", child_session_id="", **kwargs):
    """A child agent works from its parent's context: the child of a suspended parent starts suspended."""
    try:
        parent, child = anon(parent_session_id), anon(child_session_id)
        if not parent or not child or parent == child:
            return None
        with ST.mem:
            tainted = parent in ST.tainted
        if not tainted:
            with _locked():
                tainted = store_().is_tainted(parent)
        if tainted:
            _taint(child)
    except LockTimeout:
        log.warning("tenure: subagent_start skipped: the store stayed busy")
    except Exception:
        log.exception("tenure: subagent_start failed")
    return None


def subagent_stop(parent_session_id="", child_session_id="", **kwargs):
    """A child agent's summary returns to its parent's context: a child that read external content suspends the
    parent too."""
    try:
        parent, child = anon(parent_session_id), anon(child_session_id)
        if not parent or not child or parent == child:
            return None
        with ST.mem:
            tainted = child in ST.tainted
        if not tainted:
            with _locked():
                tainted = store_().is_tainted(child)
        if tainted:
            _taint(parent)
    except LockTimeout:
        log.warning("tenure: subagent_stop skipped: the store stayed busy")
    except Exception:
        log.exception("tenure: subagent_stop failed")
    return None


# --------------------------------------------------------------------------------------------------- commands
def _slash(raw_args="", **kwargs):
    from . import cli
    return cli.slash(raw_args, **kwargs)


def register(ctx):
    ST.ctx = ctx
    ctx.register_hook("pre_api_request", pre_api_request)
    ctx.register_hook("pre_tool_call", pre_tool_call)
    ctx.register_hook("post_approval_response", post_approval_response)
    ctx.register_hook("post_tool_call", post_tool_call)
    ctx.register_hook("post_llm_call", post_llm_call)
    ctx.register_hook("subagent_start", subagent_start)
    ctx.register_hook("subagent_stop", subagent_stop)
    from . import cli
    ctx.register_cli_command(name="tenure", help="Earned autonomy per action type: status, models, undo, flag, "
                                                     "revoke, passport, verify, export",
                             setup_fn=cli.setup, handler_fn=cli.run)
    ctx.register_command("tenure", handler=_slash,
                         description="What the agent has earned, per action type; models, undo, flag, revoke, passport, verify")
