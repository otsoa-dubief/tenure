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
import re
import logging
import os
import random
import secrets
import threading
import time
import unicodedata
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
MAX_SUMMARIES = 500              # numbered actions whose summary this process remembers (spec 4.4)
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
        self.lifted: OrderedDict[str, float] = OrderedDict()   # simple mode: suspensions a person lifted -> when
        self.acted: dict = {}           # (session, type) -> {"ids", "handle", "at"}: this turn's acted message
        self.turn: dict = {}            # session -> {"items", "at"}: simple mode's watched actions of this turn
        self.cwds: OrderedDict[str, str] = OrderedDict()       # session id -> terminal cwd its last command reported
        # (store path, action number) -> (its time, the call's summary): `flag` shows the target of an action this
        # process ran; never stored anywhere
        self.summaries: OrderedDict[tuple[str, int], tuple[float, str]] = OrderedDict()
        # (session, call id) -> files that already failed the automatic check before the call: never its fault
        self.broken: OrderedDict[tuple[str, str], frozenset] = OrderedDict()
        self.touched: OrderedDict[str, set] = OrderedDict()    # session -> files its calls wrote (real paths)
        # (session, call id) -> scripts the agent wrote that this asked call runs: forgotten once approved
        self.fresh: OrderedDict[tuple[str, str], list] = OrderedDict()
        # a call (_call_key) -> the files saved before it (and those its writing segments change)
        self.saved: OrderedDict[tuple, tuple] = OrderedDict()
        # a call (_call_key) -> the type it was classified as before it ran: outside any session, it is settled by
        # it, never by a reading of the disk after the command changed it
        self.kinds: OrderedDict[tuple, str] = OrderedDict()
        self.taint_from: OrderedDict[str, list] = OrderedDict()  # session -> the calls that brought outside content in
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
    series, provisional; strict mode: empty), the original's undo snapshots, pending asks, numbered actions, keys
    and exported files are dropped, and the copy gets ids of its own. A different file that no other profile claims
    moved (a restored backup): nothing changes. Raises when it cannot conclude (CopyCheckFailed, or any error: the
    transaction rolls back, file removals included); store_() then makes every action ask and tries again."""
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
                st.put_state(agent, passport._carry(s, cfg, mode(cfg), veto=False, strict=strict))
            st.db.execute("UPDATE undo SET undone = 1 WHERE undone = 0")
            st.db.execute("DELETE FROM pending")
            st.clear_recent()
            st.db.execute("DELETE FROM meta WHERE key IN (?, ?)", (UNDO_KEY, store.EXCUSE_NUMBERS))
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
    1, else the default), strict mode, type overrides, enabled, mode (simple or study)."""
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
    mode = str(_get("mode", params.DEFAULT_MODE) or params.DEFAULT_MODE).strip().lower()
    mode = mode if mode in params.MODES else params.DEFAULT_MODE
    typed = _get("fields")                              # a mistyped block is reported by the vocabulary, then ignored
    raw_fields = typed if isinstance(typed, dict) else {}
    vocabulary = fields.load(raw_fields or (typed if typed not in (None, "") else None))
    return dict(vocabulary=vocabulary, fields=raw_fields, preset=preset, risks=risks,
                spot=params.DEFAULT_SPOT if spot is None else spot,
                strict=_truthy(_get("strict", False)), overrides=overrides if isinstance(overrides, dict) else {},
                enabled=_truthy(_get("enabled", True)), mode=mode,
                # simple mode starts every type free: the trusted start, whatever the start setting says
                start="trusted" if mode == rule.SIMPLE else start if start in params.STARTS else params.DEFAULT_START)


def mode(cfg: dict | None = None) -> str:
    """The mode in force: simple or study."""
    return (cfg if cfg is not None else settings()).get("mode") or rule.STUDY


def simple(cfg: dict | None = None) -> bool:
    return mode(cfg) == rule.SIMPLE


def settings_event(cfg: dict) -> dict:
    """The settings as the ledger records them: what a replay needs to recompute the tiers. The rule version tells
    the mode (simple mode: ``rule.SIMPLE_VERSION``)."""
    return {"event": "settings", "risks": dict(cfg["risks"]), "spot": cfg["spot"], "strict": bool(cfg["strict"]),
            "start": cfg.get("start", "probation"), "rule": rule.SIMPLE_VERSION if simple(cfg) else RULE}


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


def _migrate_b2(st: store.Store) -> None:
    """Once, on the first settings of rule B/2: every record is rebuilt from the ledger, so the sessions of each
    series (kept since B/2) are the replay's, and the live record never trusts more than the passport would."""
    if st.get_meta("rule:b2") or not st.states():
        st.set_meta("rule:b2", "1")
        return
    try:
        replayed, _ = passport._replay(st.ledger())
    except Exception:                                   # a ledger that does not replay: states stay as they are,
        log.warning("tenure: records kept as they are for rule B/2 (the ledger does not replay)")   # T3 included
        st.set_meta("rule:b2", "1")
        return
    for (agent, key), s in replayed.items():
        live = st.recorded(agent, key)
        if live is not None:
            s.changed_at = live.changed_at
        st.put_state(agent, s)
    st.set_meta("rule:b2", "1")


def _rebuild(st: store.Store, new_mode: str) -> None:
    """The mode changed: every record is rebuilt from the ledger, replayed whole under the new mode, so the same
    ledger always gives the same records in a mode, whatever was switched before. A ledger that does not replay
    keeps its records as they are."""
    try:
        replayed, _ = passport._replay(st.ledger(), new_mode)
    except Exception:
        log.warning("tenure: records kept as they are for mode %s (the ledger does not replay)", new_mode)
        replayed = {}
    for (agent, key), s in replayed.items():
        live = st.recorded(agent, key)
        if live is None or {**live.to_dict(), "changed_at": 0} != {**s.to_dict(), "changed_at": 0}:
            s.changed_at = time.time()
            st.put_state(agent, s)
    st.set_meta("rule:mode", new_mode)


def sync_settings(st: store.Store, cfg: dict) -> list[dict]:
    """In a transaction, before any outcome: settings that differ from the last ones in the ledger are logged, then
    every type of every agent is re-evaluated under them (stricter settings can take a T3 back). Returns the derived
    events."""
    fp = settings_fingerprint(cfg)
    if st.get_meta("settings:fingerprint") == fp:
        return []
    st.log(settings_event(cfg))
    st.set_meta("settings:fingerprint", fp)
    _migrate_b2(st)
    if (st.get_meta("rule:mode") or rule.STUDY) != mode(cfg):
        _rebuild(st, mode(cfg))                         # another mode: every record replayed under it
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


_LINEAGE: "OrderedDict[str, str]" = OrderedDict()     # session id -> its conversation's root, found in Hermes' state
_LINEAGE_LOCK = threading.Lock()


def _lineage_root(sid: str) -> str:
    """The first session of a compressed conversation, from Hermes' own ``state.db``: compression can rotate a
    conversation to a new session id whose parent ended with ``end_reason = 'compression'``
    (``hermes_state_mutation_compress``). Only those edges are followed, with the test Hermes uses for a
    continuation (``_non_continuation_child_sql``: a fork marker naming the parent, or a tool session, is not one): a branch, a reset, ``/new``, a delegate or a tool session also carries
    ``parent_session_id`` but is its own conversation (subagents are joined to their parent by ``subagent_start``).
    Read-only and bounded. A full read is kept for the process, a missing row included, so one id never changes
    identity between the two hooks of a call; a read that failed (a lock) is not kept, and tried again."""
    with _LINEAGE_LOCK:
        if sid in _LINEAGE:
            return _LINEAGE[sid]
    root, sure = _read_lineage(sid)
    if not sure:
        return root                                 # a read that failed is tried again next time, never kept
    with _LINEAGE_LOCK:
        root = _LINEAGE.setdefault(sid, root)
        while len(_LINEAGE) > 10_000:
            _LINEAGE.popitem(last=False)
    return root


def _read_lineage(sid: str) -> tuple[str, bool]:
    """(root, read in full): False when the state could not be read, so the answer is not kept."""
    path = os.path.join(_hermes_home(), "state.db")
    if not os.path.isfile(path):
        return sid, True
    import sqlite3
    current, seen = sid, {sid}
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=0.2)
        try:
            for _ in range(100):
                row = conn.execute("SELECT c.parent_session_id, c.model_config, COALESCE(c.source, ''), p.end_reason "
                                   "FROM sessions c LEFT JOIN sessions p ON p.id = c.parent_session_id "
                                   "WHERE c.id = ?", (current,)).fetchone()
                if row is None or not row[0] or row[3] != "compression" or row[2] == "tool" or row[0] in seen:
                    break
                try:
                    marks = json.loads(row[1] or "{}")
                except ValueError:
                    marks = {}
                if isinstance(marks, dict) and any(marks.get(m) == row[0] for m in
                                                   ("_branched_from", "_delegate_from", "_reset_from")):
                    break                                   # a fork that inherited nothing but its parent's id
                current = row[0]
                seen.add(current)
        finally:
            conn.close()
    except Exception:
        log.debug("tenure: Hermes' session lineage could not be read", exc_info=True)
        return current, False
    return current, True


def anon(session_id) -> str:
    """A session as stored: sha256(the root of its conversation)[:12]; "" without a session id, which counts as no
    session."""
    sid = str(session_id or "")
    return hashlib.sha256(_lineage_root(sid).encode("utf-8")).hexdigest()[:12] if sid else ""


def agent_name(model, provider) -> str:
    return f"{model}@{provider or 'unknown'}"


def _call_key(session: str, call: str, tool: str, args: dict) -> tuple:
    """One call in the in-memory maps that pre_tool_call fills and post_tool_call reads: outside any session, call ids
    recur, so the tool and its target are part of it."""
    return session, call, tool, str(args.get("command") or args.get("path") or "")


def _remember(cache: OrderedDict, key: str, value) -> None:
    """Under ST.mem: one entry of a bounded in-memory map, the oldest dropped first."""
    cache[key] = value
    cache.move_to_end(key)
    while len(cache) > MAX_SESSIONS:
        cache.popitem(last=False)


def _touch(session: str, paths) -> None:
    """The files a call of this session wrote, ran or failed (real paths): a file broken by the session itself is
    never excused later as broken before (audit 19/11)."""
    real = {proofs._real(p) for p in paths or []}
    if not real:
        return
    session = store.Store.roots.get(session) or session     # a subagent's files are its root conversation's
    with ST.mem:
        seen = ST.touched.get(session) or set()
        if len(seen) < 10_000:
            seen |= real
        _remember(ST.touched, session, seen)


def _touched(session: str) -> frozenset:
    session = store.Store.roots.get(session) or session
    with ST.mem:
        return frozenset(ST.touched.get(session) or ())


def _remember_summary(path: str, n: int, at: float, summary: str) -> None:
    """Under ST.mem: the summary of numbered action ``n`` of the store at ``path``, the oldest of 500 dropped first."""
    ST.summaries[(path, n)] = (at, summary)
    ST.summaries.move_to_end((path, n))
    while len(ST.summaries) > MAX_SUMMARIES:
        ST.summaries.popitem(last=False)


def summary_of(path: str, n: int, at: float) -> str:
    """The remembered summary of action ``n``, only when its time matches the numbered row: else ""."""
    with ST.mem:
        hit = ST.summaries.get((path, n))
    return hit[1] if hit and hit[0] == at else ""


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


_SAFE = re.compile(r"[a-z0-9.-]{1,63}")
_URL_KEYS = ("url", "urls", "href", "link", "links", "uri")


def _host_of(url: str) -> str | None:
    """The host of one URL, if it is plain and unambiguous: never one with a backslash or an @ left in its authority
    (``evil.com\\@docs.example.com`` is not shown as docs.example.com), never a non-ASCII or odd name; a private or
    loopback address reads "local network"."""
    import ipaddress
    import urllib.parse
    try:
        parts = urllib.parse.urlsplit(str(url).strip())
        authority = parts.netloc.rsplit("@", 1)[-1]
        host = (parts.hostname or "").lower()
    except ValueError:
        return None
    if not host or "\\" in parts.netloc or "@" in authority or not _SAFE.fullmatch(host):
        return None
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            return "local network"
    except ValueError:
        if host == "localhost" or host.endswith((".local", ".internal", ".lan", ".localhost")):
            return "local network"
    return host


def _source_label(tool: str, args: dict) -> str:
    """What suspended a session, as the owner reads it: the tool (bounded, plain characters) and the host of the URL
    it was given under a URL argument, never a path, a query, credentials or a URL found elsewhere in the arguments."""
    name = re.sub(r"[^A-Za-z0-9_.:-]", "", str(tool))[:40] or "tool"
    for key in _URL_KEYS:
        value = args.get(key) if isinstance(args, dict) else None
        url = value[0] if isinstance(value, list) and value else value
        if isinstance(url, str):
            host = _host_of(url)
            return f"{name} {host}" if host else name
    return name


def _taint_label(session: str) -> str:
    """The last call that brought outside content into the session, and how many before it: the latest source is
    the one the owner must weigh, never only the first, which may be a harmless page."""
    with ST.mem:
        seen = ST.taint_from.get(session) or []
    if not seen:
        return ""
    return seen[-1] if len(seen) == 1 else tr("ask.why.suspended_more", source=seen[-1], n=len(seen) - 1)


def _lifted(session: str, st: store.Store | None = None) -> bool:
    """Simple mode: a person lifted this session's suspension (``_lift``). Never the empty session (calls outside any
    session): nothing is lifted for the whole process."""
    if not session:
        return False
    with ST.mem:
        if session in ST.lifted:
            return True
    if st is not None:
        return st.lifted(session)
    with _locked():
        return store_().lifted(session)


def _lift(st: store.Store, session: str) -> None:
    """Simple mode: a person approved the question a suspension asked. The session works as before for the rest of
    its life: the next commands follow the simple rule, and a later outside read does not suspend it again (``_taint``).
    What 1.3 asks after outside content whatever the suspension stays (``_outside``): a file that runs code, written
    after outside content, and a script written then run. Never the empty session."""
    if not session:
        return
    with ST.mem:
        ST.tainted.pop(session, None)
        _remember(ST.lifted, session, time.time())
    st.lift(session)


def _outside(st: store.Store, session: str, suspended: bool) -> bool:
    """The session read outside content, suspended or lifted since."""
    return suspended or _lifted(session, st)


def _taint(session: str) -> None:
    """Suspend a session: in this process at once, then in the store in a transaction of its own, so that nothing
    that fails later (or a busy store) can take it back. The empty session (calls outside any session) is never
    suspended as a whole: only in this process, for an hour. Simple mode: a session whose suspension a person lifted
    is not suspended again."""
    try:
        if session and simple() and _lifted(session):
            return
    except Exception:
        log.debug("tenure: could not read whether the suspension was lifted; suspending", exc_info=True)
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


AGENT_CHILD = "TENURE_AGENT_CHILD"     # set by Hermes in every tool subprocess of a session (register_session_env)
# Hermes starts execute_code's Python with a scrubbed environment (tools/code_execution_env.py, _build_child_env):
# the marker above does not reach it, but its tool RPC endpoint and token always do, local kernel or remote sandbox.
EXEC_CODE_ENV = ("HERMES_RPC_TOKEN", "HERMES_RPC_SOCKET", "HERMES_RPC_DIR", "HERMES_KERNEL_SENTINEL")


def agent_process() -> str | None:
    """Why this process is one of the agent's own, or None: a child of Hermes' tools in a session (``AGENT_CHILD``,
    which tenure registers for every terminal command, ``execute_code``'s ``terminal()`` included), or the Python of
    ``execute_code`` itself (``EXEC_CODE_ENV``), where code may import tenure. A person's word (trust, ok, excuse) is
    never taken from there, even through the slash command's entry point. Defence in depth: code that deletes these
    variables in its own process first can still write the store directly; the approval of a command that names
    Hermes (capped) and of code naming tenure's data (capped) remain the walls."""
    if os.environ.get(AGENT_CHILD):
        return AGENT_CHILD
    for name in EXEC_CODE_ENV:
        if os.environ.get(name):
            return name
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
    """An "acted, then told you" line: actions of one type in one turn share one message, edited in place. It carries
    the shown paths of the action (display text, kept in memory only, never in the ledger or a push)."""
    def __new__(cls, text: str, session: str, type_key: str, undo_id: int, shown: list[str] | None = None):
        obj = super().__new__(cls, text)
        obj.session, obj.type_key, obj.undo_id, obj.shown = session, type_key, undo_id, list(shown or [])
        return obj


WHAT_SHOWN = 3                  # files named in a message: the first three, then "+N"


SHOWN_CAP = 120                 # one shown path: whole up to here, then its start (80), "…" and its end (39)


def _show(path: str, cwd: str, home: str) -> str:
    """One written path as the owner reads it: relative to the call's folder, else ``~/...``, else absolute (also
    when the path and the folder are on different Windows drives). Control and format characters (a bidi override, a
    newline) become U+FFFD. A path longer than 120 characters keeps its start and its end, as a prompt's target."""
    text = str(path)
    if os.path.isabs(text):
        for base, prefix in ((cwd, ""), (home, "~/")):
            if base and os.path.isabs(base):
                try:
                    rel = os.path.relpath(text, base)
                except ValueError:                      # another drive: no relative form
                    continue
                if rel != "." and rel != ".." and not rel.startswith(".." + os.sep):
                    text = prefix + rel
                    break
    text = text.replace(os.sep, "/").replace("\\", "/")     # one display on every system
    text = "".join("\ufffd" if unicodedata.category(c) in ("Cc", "Cf") else c for c in text)
    return text if len(text) <= SHOWN_CAP else text[:80] + "\u2026" + text[-39:]


def _join_shown(shown: list[str]) -> str:
    """The first three shown paths, then ``+N`` for the others."""
    uniq = list(dict.fromkeys(shown))
    head = ", ".join(uniq[:WHAT_SHOWN])
    return f"{head} +{len(uniq) - WHAT_SHOWN}" if len(uniq) > WHAT_SHOWN else head


def _what(paths: list[str], cwd: str, home: str) -> str:
    """The files an action changed, for the owner's message: ``a.py, b.py, c.py +1``; "" when there are none."""
    return _join_shown([_show(x, cwd, home) for x in paths or []])


def _with_what(files: str) -> str:
    """The ``{what}`` of a message: a leading space and the files in brackets, or nothing."""
    return " " + tr("settle.what", files=files) if files else ""


ACTED_WINDOW = 600.0            # seconds: without an end-of-turn signal, a later action starts a new message
LABEL_CAP = 60                  # characters of a command shown in the end-of-turn line


class Watched:
    """Simple mode: one watched action of this turn (acted, then shown, with an undo), kept in memory until the turn
    ends (``post_llm_call``), when one line lists them all. ``more``: the lines of its command past the first one;
    ``cut``: the first line was cut; ``files``: the files it changed, as shown (both say what a harmless first line
    could hide); ``count``: the files the one undo of a chained line holds."""
    def __init__(self, session: str, undo_id: int, label: str, more: int = 0, cut: bool = False, files: str = "",
                 count: int = 0):
        self.session, self.undo_id, self.label = session, undo_id, label
        self.more, self.cut, self.files, self.count = more, cut, files, count

    def text(self) -> str:
        """``#14 npm run build``, then ``(+2 lines, files: a.py, b.py)`` when the command has more lines or was cut;
        a chained line says how many files its undo holds instead: ``(+6 files)``."""
        parts = []
        if self.more:
            parts.append(tr("simple.turn.lines", n=self.more))
        if self.count:
            parts.append(tr("simple.turn.count", n=self.count))
        elif (self.more or self.cut) and self.files:
            parts.append(tr("simple.turn.files", files=self.files))
        return f"#{self.undo_id} {self.label}" + (f" ({', '.join(parts)})" if parts else "")


def _label(tool: str, args: dict, vocabulary=None) -> str:
    """A watched action in the end-of-turn line: a terminal command's first line (60 characters at most), secrets
    masked as in a prompt (``fields.mask_command``), else "" (the files it changed are shown instead). Control and
    format characters become U+FFFD."""
    if tool != "terminal" or not isinstance(args.get("command"), str):
        return ""
    command = fields.mask_command(args["command"], vocabulary)
    text = command.strip().splitlines()[0] if command.strip() else ""
    text = "".join("\ufffd" if unicodedata.category(c) in ("Cc", "Cf") else c for c in text)
    return text if len(text) <= LABEL_CAP else text[:LABEL_CAP - 1] + "\u2026"


def _more_lines(tool: str, args: dict) -> tuple[int, bool]:
    """A terminal command in the end-of-turn line: (its non-empty lines past the first, whether the first is cut at
    ``LABEL_CAP``)."""
    if tool != "terminal" or not isinstance(args.get("command"), str):
        return 0, False
    lines = [x for x in args["command"].strip().splitlines() if x.strip()]
    return max(len(lines) - 1, 0), bool(lines) and len(lines[0].strip()) > LABEL_CAP


def _turn_line(items: list) -> str:
    return tr("simple.turn", n=len(items), actions=", ".join(w.text() for w in items), command="/tenure undo")


def _flush_turn(session: str | None) -> None:
    """Post the line of the watched actions of the turn that ended (of every session when ``session`` is None)."""
    with ST.mem:
        keys = [k for k in ST.turn if session is None or k == session]
        batches = [ST.turn.pop(k)["items"] for k in keys]
    for items in batches:
        if items:
            _post(_turn_line(items))


def _post(text: str) -> None:
    try:
        if ST.ctx is not None and hasattr(ST.ctx, "post_message"):
            ST.ctx.post_message(text)
    except Exception:
        log.debug("tenure: post_message failed", exc_info=True)


def _ids(ids: list[int]) -> str:
    return f"{ids[0]}–{ids[-1]}" if ids == list(range(ids[0], ids[-1] + 1)) else ", ".join(map(str, ids))


def _with_ok(text: str, ids: list[int]) -> str:
    """The "seen and fine?" hint, naming the actions' numbers, before the undo command, which stays last."""
    i = text.rfind(" · ")
    hint = (tr("settle.acted_ok", command=f"/tenure ok {ids[0]}") if len(ids) == 1   # one gesture per action:
            else tr("settle.acted_ok_each", command="/tenure ok"))              # never a ready-made list to paste
    return text + " · " + hint if i < 0 else text[:i] + " · " + hint + text[i:]


def _announce(text) -> None:
    if isinstance(text, Watched):                       # said once, at the end of the turn
        now = time.time()
        with ST.mem:
            entry = ST.turn.get(text.session)
            stale = entry is not None and now - entry["at"] >= ACTED_WINDOW   # no end-of-turn signal came
            old = ST.turn.pop(text.session)["items"] if stale else None
            entry = ST.turn.setdefault(text.session, {"items": [], "at": now})
            entry["items"].append(text)
            entry["at"] = now
        if old:
            _post(_turn_line(old))
        return
    try:
        if ST.ctx is None or not hasattr(ST.ctx, "post_message"):
            return
        if isinstance(text, Acted):
            key, now = (text.session, text.type_key), time.time()
            with ST.mem:
                entry = ST.acted.get(key)
                if entry and now - entry["at"] < ACTED_WINDOW and callable(getattr(entry["handle"], "edit", None)):
                    entry["ids"].append(text.undo_id)
                    if getattr(text, "ok_hint", False):
                        entry.setdefault("ok_ids", []).append(text.undo_id)
                    entry["shown"].extend(text.shown)
                    entry["at"] = now
                    ids = entry["ids"]
                    grouped = tr("settle.acted_many", type=text.type_key, n=len(ids), command="/tenure undo",
                                 id=ids[-1], ids=_ids(ids), what=_with_what(_join_shown(entry["shown"])))
                    if getattr(text, "ok_hint", False) or entry.get("ok"):
                        entry["ok"] = True
                        grouped = _with_ok(grouped, [i for i in ids if i in entry.get("ok_ids", ids)])
                    entry["handle"].edit(grouped)
                    return
            handle = ST.ctx.post_message(str(text))
            with ST.mem:
                ST.acted[key] = {"ids": [text.undo_id], "handle": handle, "at": now, "shown": list(text.shown),
                                 "ok": getattr(text, "ok_hint", False),
                                 "ok_ids": [text.undo_id] if getattr(text, "ok_hint", False) else []}
            return
        ST.ctx.post_message(text)
    except Exception:
        log.debug("tenure: post_message failed", exc_info=True)


def post_llm_call(session_id="", **kwargs):
    """The turn ended: the next acted action of a type starts a new message; in simple mode, the watched actions of
    the turn are listed in one line."""
    try:
        session = anon(session_id or kwargs.get("task_id") or "")
        with ST.mem:
            for key in [k for k in ST.acted if k[0] == session or not session_id]:
                del ST.acted[key]
        _flush_turn(session if (session_id or kwargs.get("task_id")) else None)
    except Exception:
        log.debug("tenure: post_llm_call failed", exc_info=True)
    return None


def _purge() -> bool:
    """Delete undo snapshots past their 24-hour window, at most once an hour per process. True when it ran: the
    caller then drops the meta keys of those undo entries in its transaction."""
    now = time.time()
    if now - ST.purged_at < PURGE_EVERY:
        return False
    ST.purged_at = now
    try:
        undo.purge(data_dir())
    except Exception:
        log.debug("tenure: undo purge failed", exc_info=True)
    return True


def state_name(cfg: dict, s: rule.TypeState | None, n=None) -> str:
    """Simple mode: where a type stands, in plain words (free, watched, asks first); study mode: its tier."""
    if s is None:
        return ""
    if not simple(cfg):
        return tier_name(s.tier)
    n = params.required_n(cfg["risks"], s.stakes) if n is None else n
    if trusted(cfg, s, n, s.stakes):
        return tr("simple.state.free")
    if rule.decide(s, n, cfg["spot"], suspended=False, rng=_NoSpot, mode=rule.SIMPLE) == rule.NOTIFY:
        return tr("simple.state.watched")
    return tr("simple.state.ask")


def _say_simple(events: list[dict]) -> list[str]:
    """Simple mode's announcements, in plain words: no tiers, no trials, no spot checks."""
    out = []
    for ev in events:
        t, kind, reason, to = ev.get("type"), ev.get("event"), ev.get("reason"), ev.get("to")
        if kind == "tier" and reason == "fault" and ev.get("from") in ("trusted", rule.T3):
            out.append(tr("simple.notice.first_watched" if to == rule.T2 else "simple.notice.first_ask", type=t))
        elif kind == "tier" and reason == "fault" and to == rule.T1:
            out.append(tr("simple.notice.second", type=t))
        elif kind == "tier" and reason == "wald":
            out.append(tr("simple.notice.watched_again", type=t))
        elif kind == "tier" and reason == "series":
            out.append(tr("simple.notice.free_again", type=t, n=ev.get("required")))
        elif kind == "tier" and reason == "settings":
            out.append(tr("simple.notice.now", type=t,
                          state=tr({rule.T3: "simple.state.free", rule.T2: "simple.state.watched"}.get(
                              to, "simple.state.ask"))))
    return out


def _say(events: list[dict], spot: float, mode: str = rule.STUDY) -> list[str]:
    """Plain announcements for the owner: tier changes, trials, confirmed carry-overs."""
    if mode == rule.SIMPLE:
        return _say_simple(events)
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
                   result: str, source: str, session: str = "", number: int | None = None) -> list[dict]:
    """Apply one outcome to an agent's type and log it, in a transaction, after ``sync_settings``: first the input
    event a replay reads, then the rule's derived events. The one way an outcome reaches the record (hooks, CLI,
    dashboard). After the outcome of an action that ran, the wait after a failed trial counts it (``store.COUNTED``),
    except for the fault that failed the trial. A fault a person may excuse gets the number they excuse it by
    (``Store.number_fault``): ``number``, the undo number of an undone action, else a new one. Returns the derived
    events."""
    if source not in store.OUTCOME_SOURCES.get(result, ()):
        raise ValueError(f"tenure: unknown outcome {result!r} from {source!r}")
    recorded = st.recorded(agent, type_key)
    s = st.get_state(agent, type_key, stakes, reversible)
    n = params.required_n(cfg["risks"], stakes)
    rebased = rule.rebase(s) if recorded is not None and recorded.stakes != stakes else []
    was_trusted = trusted(cfg, s, n, stakes)
    events = rule.outcome(s, n, result, source, session=session, start=cfg.get("start"), mode=mode(cfg))
    failed_trial = any(ev["event"] == "trial" and ev.get("reason") == "failed" for ev in events)
    if was_trusted and result == "fault" and not any(ev["event"] == "tier" for ev in events):
        events.insert(0, {"event": "tier", "type": type_key, "stakes": stakes, "from": "trusted", "to": s.tier,
                          "reason": "fault"})                # the trusted start ends: the study rule applies now
    events = rebased + events
    if (result, source) in store.COUNTED and not failed_trial:
        events += rule.count_action(s)
    st.put_state(agent, s)
    if source in ("approval", "refusal"):
        st.clear_doubt(agent, type_key)                 # the owner answered: a verifier's doubt is settled
    if source == "spot" and st.get_meta(_due_key(agent, type_key)):
        st.set_meta(_due_key(agent, type_key), "")     # a person answered a check: the due one is done
    if result == "fault":
        st.distrust(type_key)
    session = st.root_of(session)                        # a subagent's outcome counts in its root conversation
    st.last_outcome_seq = st.log({"event": "outcome", "agent": agent, "type": type_key, "stakes": stakes,
                                  "reversible": bool(reversible), "result": result, "source": source,
                                  "session": session})
    if result == "fault" and source in store.EXCUSABLE:
        st.number_fault(st.last_outcome_seq, number)
    for ev in events:
        st.log({**ev, "agent": agent})
    _push("changed", {"agent": agent, "type": type_key})      # sent when the transaction commits
    return events


UNDO_WINDOW = 24 * 3600          # seconds an act-then-notify action can be undone
UNDO_FAILED = "undo_failed:"     # meta key prefix: the undo entry of a call that failed after its files were saved
UNDO_FILES = "undo_files:"       # meta key prefix: the undo entry of a chained line, and how many files it holds
INDEX_PENDING = "index_pending:"  # meta key prefix: an undo whose files came back but not git's index (retried)
UNKNOWN_WHY = "unknown_why"      # meta key: why the last file:unknown command was unknown (glob, variable, path)
NOUNDO = "noundo:"               # meta key prefix: a kind whose last free call asked because tenure could not undo it


def _credit_due(st: store.Store, cfg: dict, now: float | None = None) -> list[dict]:
    """Credit the earned act-then-tell actions whose undo window closed (audit 19/11): a success nobody saw counts
    only once it could no longer be undone. Undone, flagged or followed by a fault on its type: no credit (a later
    fault restarted the series, and an action from before it must not join the new one). Returns the derived events."""
    now = time.time() if now is None else now
    events = []
    for c in st.due_credits(now - UNDO_WINDOW):
        st.drop_credit(c["undo_id"])
        if c["agent"] is None or c["undone"] or c["fault"]:
            continue
        try:
            recorded = st.recorded(c["agent"], c["type"])
            if (st.fault_since(c["agent"], c["type"], c["seq"]) or st.doubted(c["agent"], c["type"])
                    or recorded is None or recorded.stakes != c["stakes"]):
                result, source = "neutral", "expired"    # a later fault, revoke, doubt or other stakes: no credit
            else:
                result, source = "neutral", "unseen"     # rule B/2: silence is not a check (only a person's "seen")
            stakes, reversible = ((recorded.stakes, recorded.reversible) if recorded is not None and result == "neutral"
                                  else (c["stakes"], bool(c["reversible"])))   # a neutral never rebases the record
            sync_settings(st, cfg)
            events += record_outcome(st, cfg, agent=c["agent"], type_key=c["type"], stakes=stakes,
                                     reversible=reversible, result=result, source=source,
                                     session=c["session"] or "")
        except Exception:                               # one bad credit never blocks the others, nor the decision
            log.exception("tenure: a deferred credit could not be recorded; dropped")
    return events


def excusable(st: store.Store, now: float | None = None, limit: bool = True) -> list[dict]:
    """The fault outcomes of the last ``store.EXCUSE_WINDOW`` seconds not excused yet, newest first: ``n`` (the number
    a person excuses it by, ``Store.number_fault``), ``seq`` (its ledger row), ``at``, ``agent``, ``type``,
    ``source``. A fault without a number (logged by an older tenure) is not listed: no number could name it."""
    now = time.time() if now is None else now
    rows = st.ledger()
    numbers = st.fault_numbers()
    done = {(r["event"] or {}).get("seq") for r in rows if (r["event"] or {}).get("event") == "excuse"}
    by_seq = {r["seq"]: r for r in rows}
    recent: dict = {}                                # excuses per type over the last EXCUSE_PERIOD: at most LIMIT
    for r in rows:
        e = r["event"] or {}
        if e.get("event") == "excuse" and now - r["at"] <= store.EXCUSE_PERIOD:
            k = ((by_seq.get(e.get("seq")) or {}).get("event") or {}).get("type")
            recent[k] = recent.get(k, 0) + 1
    out = []
    for r in reversed(rows):
        if now - r["at"] > store.EXCUSE_WINDOW:
            break
        e = r["event"] or {}
        if (e.get("event") == "outcome" and e.get("result") == "fault" and e.get("source") in store.EXCUSABLE
                and r["seq"] not in done and r["seq"] in numbers
                and (not limit or recent.get(e.get("type"), 0) < store.EXCUSE_LIMIT)):
            out.append({"n": numbers[r["seq"]], "seq": r["seq"], "at": r["at"], "agent": e["agent"],
                        "type": e["type"], "source": e["source"]})
    return out


def excuse(st: store.Store, number: int) -> str:
    """The owner takes back one fault of the last ``store.EXCUSE_WINDOW`` seconds (protocol 0.2), named by the number
    they saw: the undo number of the action they undid, or the number the notice gave after a refusal (one namespace,
    ``Store.number_fault``). An ``excuse`` event names its ledger row, and every state is replayed from the ledger,
    where that fault now counts as neutral. Its effects go with it: the tier drop, the trial, the lost trusted start
    (unless another fault or a revoke keeps it lost). Call it inside ``txn()``. Raises ValueError with the owner's
    message when it is not excusable."""
    if agent_process():                             # code or a command the agent runs: never its own excuse
        raise ValueError(tr("ask.person_only"))
    plain = simple()
    why = nobody_answers()
    if why:                                         # the agent's own command, approved by nobody: never
        raise ValueError(tr("simple.excuse.nobody" if plain else "cli.excuse.nobody", why=why))
    row = next((r for r in excusable(st) if r["n"] == number), None)
    if row is None:
        if number in {r["n"] for r in excusable(st, limit=False)}:     # it would be, but for the weekly limit
            raise ValueError(tr("simple.excuse.limit" if plain else "cli.excuse.limit", n=number,
                                limit=store.EXCUSE_LIMIT, days=store.EXCUSE_PERIOD // 86400))
        raise ValueError(tr("simple.excuse.unknown" if plain else "cli.excuse.unknown", n=number,
                            minutes=store.EXCUSE_WINDOW // 60))
    seq = row["seq"]
    rows = st.ledger()
    head = rows[-1] if rows else {"seq": 0, "at": 0}
    replayed, _ = passport._replay(rows + [{"seq": head["seq"] + 1, "at": time.time(),   # dry run first: a ledger
                                             "event": {"event": "excuse", "seq": seq}}])  # that cannot replay logs none
    st.log({"event": "excuse", "seq": seq})
    now, key = time.time(), row["type"]
    for (agent, k), s in replayed.items():           # only the excused type: other records are left as they are
        if k != key:
            continue
        live = st.recorded(agent, k)
        if live is None or {**live.to_dict(), "changed_at": 0} != {**s.to_dict(), "changed_at": 0}:
            s.changed_at = now
            st.put_state(agent, s)
    if not any(s.distrusted for (a, k), s in replayed.items() if k == key):
        st.trust_again(key)
    st.bump(row["agent"], "faults", -1, at=row["at"])
    s = replayed.get((row["agent"], row["type"]))
    _push("changed", {"agent": row["agent"], "type": row["type"]})
    cfg = settings()
    if simple(cfg):
        return tr("simple.excuse.done", n=number, type=row["type"], state=state_name(cfg, s))
    tier = (tr("cli.excuse.trusted") if s is not None and trusted(cfg, s, params.required_n(cfg["risks"], s.stakes),
                                                                  s.stakes) else tier_name(s.tier) if s is not None
            else "")
    return tr("cli.excuse.done", n=number, type=row["type"], agent=row["agent"], tier=tier)


def seen(st: store.Store, undo_ids: list[int]) -> str:
    """The owner looked at these act-then-tell actions, named one by one by their undo numbers, and they are fine
    (rule B/2): each counts as a success now, source ``seen``. Never a blanket "all of them": a person names what
    they saw. Only a person: never while nobody answers. Raises ValueError with the owner's message when none of the
    numbers is open."""
    if agent_process():                             # code or a command the agent runs: never its own "seen"
        raise ValueError(tr("ask.person_only"))
    why = nobody_answers()
    if why:
        raise ValueError(tr("cli.ok.nobody", why=why))
    if simple():                                    # harmless, and not needed: silence already counts there
        return tr("simple.ok")
    wanted = set(undo_ids)
    rows = [r for r in st.open_credits(time.time() - UNDO_WINDOW) if r["undo_id"] in wanted]
    if not rows:
        raise ValueError(tr("cli.ok.none"))
    cfg = settings()
    done: list[dict] = []
    events = _see(st, cfg, rows, done)
    if not done:                                    # they expired now (a later fault...): say so, it is recorded
        return tr("cli.ok.expired", which=", ".join(str(r["undo_id"]) for r in rows))
    marked = ", ".join(f"{r['undo_id']} ({r['type']})" for r in done)
    return "\n\n".join([tr("cli.ok.done", n=len(done), which=marked)] + _say(events, cfg["spot"], mode(cfg)))


def owner_trust(st: store.Store, cfg: dict, agent: str, s: rule.TypeState, to: str, undo: bool = True) -> list[dict]:
    """A person's word on a kind, simple mode only (``/tenure trust``): ``rule.FREE`` gives it its freedom back now,
    ``rule.PIN`` makes it ask first until freed again. Logged as a ``trust`` input event, then the rule's derived
    events, so a replay gives the same record. The caller checks the kind may take it (``cli.trust_set``); this only
    refuses in one of the agent's own processes (``agent_process``), when nobody answers approvals (never the agent's
    own command) and outside simple mode. Call it inside ``txn()``."""
    if agent_process():
        raise ValueError(tr("ask.person_only"))
    why = nobody_answers()
    if why:
        raise ValueError(tr("trust.nobody", why=why))
    if not simple(cfg) or to not in (rule.FREE, rule.PIN):
        raise ValueError(tr("trust.study", command="hermes tenure mode simple"))
    sync_settings(st, cfg)
    s = st.recorded(agent, s.key) or s                  # the settings just synced may have re-evaluated it
    n = params.required_n(cfg["risks"], s.stakes)
    undo = undo or to != rule.FREE                      # undo False: a kind tenure cannot undo, freed without one
    events = rule.owner_free(s, n, undo=undo) if to == rule.FREE else rule.owner_pin(s)
    s.changed_at = time.time()
    st.put_state(agent, s)
    st.log({"event": "trust", "agent": agent, "type": s.key, "to": to, **({} if undo else {"undo": False})})
    for ev in events:
        st.log({**ev, "agent": agent})
    _push("changed", {"agent": agent, "type": s.key})
    return events


def _see(st: store.Store, cfg: dict, rows: list[dict], done: list | None = None) -> list[dict]:
    """Credit these open act-then-tell actions as seen by a person; returns the derived events."""
    sync_settings(st, cfg)
    events = []
    for r in rows:
        st.drop_credit(r["undo_id"])
        recorded = st.recorded(r["agent"], r["type"])
        if (st.fault_since(r["agent"], r["type"], r["seq"]) or st.doubted(r["agent"], r["type"]) or recorded is None
                or recorded.stakes != r["stakes"]):
            if recorded is not None:                     # a later fault, revoke, doubt or other stakes: neutral
                events += record_outcome(st, cfg, agent=r["agent"], type_key=r["type"], stakes=recorded.stakes,
                                         reversible=recorded.reversible, result="neutral", source="expired",
                                         session=r["session"] or "")
            continue
        events += record_outcome(st, cfg, agent=r["agent"], type_key=r["type"], stakes=r["stakes"],
                                 reversible=bool(r["reversible"]), result="success", source="seen",
                                 session=r["session"] or "")
        if done is not None:
            done.append(r)
    return events


def _excuse_hint(st: store.Store, events: list[dict]) -> list[str]:
    """After a fault the owner caused (a refusal, an undo) that cost something (a tier, the trusted start): how to
    take it back if the error was the owner's. Said neutrally, and only then: never an invitation after every no.
    It names the fault by the number the owner excuses it by: the undo number they just typed, after an undo."""
    seq = getattr(st, "last_outcome_seq", None)
    if not seq or not any(ev.get("event") in ("tier", "trial") for ev in events):
        return []
    key = next((ev.get("type") for ev in events if ev.get("type")), "")
    day = time.strftime("%Y-%m-%d")                 # once a day per type: a reminder, never a reflex after every no
    if st.get_meta("excuse_hint:" + key) == day:
        return []                                   # first: the hook's transaction reads no ledger for nothing
    n = st.fault_numbers().get(seq)
    if n is None or not any(r["seq"] == seq for r in excusable(st)):   # the ledger only for the weekly limit
        return []
    st.set_meta("excuse_hint:" + key, day)
    return [tr("simple.notice.excuse_hint" if simple() else "notice.excuse.hint", n=n,
               minutes=store.EXCUSE_WINDOW // 60)]


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
    """Revert one act-then-notify action (files back to their snapshot) and count it as a fault of its type, unless its
    automatic check or a flag already did; undone, its numbered action counts as flagged. The one implementation,
    used by the CLI, the slash command and the dashboard. Call it inside ``txn()``, then call ``cleanup()`` on the
    result once the transaction has committed: the snapshot is only deleted then, so a failure before the commit
    leaves the action retryable. Returns a message (a ``str`` whose ``ok`` is False when nothing was undone). A
    partial restore marks nothing undone and records no fault: the snapshot is kept, so the owner can try again. The
    settings are the configured ones, synced into the ledger."""
    entry = st.get_undo(id)
    if entry is None:
        return UndoMessage(tr("undo.missing", id=id), False)
    st.drop_credit(id)                                    # the owner tried to undo it: never a success, even if it fails
    if entry["undone"]:
        if st.get_meta(INDEX_PENDING + str(id)):            # its files came back, git's index did not
            if (not entry["snap_id"] or time.time() - entry["at"] > UNDO_WINDOW
                    or not undo.exists(entry["snap_id"], data_dir())):
                st.set_meta(INDEX_PENDING + str(id), "")
                return UndoMessage(tr("undo.index_expired", id=id), False)
            index = undo.restore_index(entry["snap_id"], data_dir(), key=undo_key())
            if index:
                return UndoMessage(tr("undo.index_failed", error=index, id=id, command="/tenure undo"), False)
            st.set_meta(INDEX_PENDING + str(id), "")
            return UndoMessage(tr("undo.index_done", id=id), True, entry["snap_id"])
        return UndoMessage(tr("undo.already", id=id), False)
    if time.time() - entry["at"] > UNDO_WINDOW:
        return UndoMessage(tr("undo.expired", id=id, n=UNDO_WINDOW // 3600), False)
    cfg = settings()
    plain = simple(cfg)                                   # simple mode's words: no fault, no snapshot
    if not entry["snap_id"]:
        return _undo_failed(st, entry, tr("simple.undo.no_snapshot" if plain else "undo.no_snapshot", id=id))
    after_failure = bool(st.get_meta(UNDO_FAILED + str(id)))
    try:
        untouched = after_failure and undo.unchanged(entry["snap_id"], data_dir(), key=undo_key())
        restored, failed = undo.restore(entry["snap_id"], data_dir(), keep=True, key=undo_key())
    except undo.Refused as e:
        return _undo_failed(st, entry, tr("simple.undo.refused" if plain else "undo.refused", id=id, reason=e))
    if failed:
        return _undo_failed(st, entry, tr("simple.undo.partial" if plain else "undo.partial", id=id, n=failed,
                                          restored=restored))
    if restored == 0:
        return _undo_failed(st, entry, tr("simple.undo.gone" if plain else "undo.gone", id=id))
    index = undo.restore_index(entry["snap_id"], data_dir(), key=undo_key())   # git rm / git mv: the index too
    note = ("\n" + tr("undo.index_failed", error=index, id=id, command="/tenure undo")) if index else ""
    keep = None if index else entry["snap_id"]          # the index failed: its snapshot stays, for a retry
    if index:
        st.set_meta(INDEX_PENDING + str(id), "1")
    agent, key = entry["agent"], entry["type"]
    st.mark_undone(id)
    st.flag_by_undo(id)                                   # undone: it cannot be flagged afterwards
    if entry["fault"]:
        return UndoMessage(tr("simple.undo.done_already_fault" if plain else "undo.done_already_fault", id=id,
                              type=key) + note, True, keep)
    if untouched:                                         # a failed call that changed nothing: restored, no fault
        return UndoMessage(tr("simple.undo.done_unchanged" if plain else "undo.done_unchanged", id=id, type=key)
                           + note, True, keep)
    recorded = st.recorded(agent, key)
    stakes, reversible = (recorded.stakes, recorded.reversible) if recorded else ("medium", True)
    sync_settings(st, cfg)
    events = record_outcome(st, cfg, agent=agent, type_key=key, stakes=stakes, reversible=reversible,
                            result="fault", source="undo", number=id)   # excused by the number just undone
    st.bump(agent, "faults")
    s = st.get_state(agent, key, stakes, reversible)
    if plain:                                             # two short lines at most: what happened and what now,
        line = " ".join(x for x in [tr("simple.undo.done", id=id, type=key), _undo_now(events)] if x)
        return UndoMessage("\n".join([line] + _excuse_hint(st, events)) + note, True, keep)   # hint
    text = "\n\n".join([tr("undo.done", id=id, type=key, agent=agent, tier=state_name(cfg, s))]
                       + _say(events, cfg["spot"], mode(cfg))   # e.g. "On probation" when it ends the trusted start
                       + _excuse_hint(st, events))
    return UndoMessage(text + note, True, keep)


def _undo_now(events: list[dict]) -> str:
    """Simple mode, after an undo or a refusal: where the kind stands now, in one short sentence ("" when unchanged)."""
    for ev in events:
        if ev.get("event") == "tier" and ev.get("reason") == "fault":
            first = ev.get("from") in ("trusted", rule.T3)
            if ev.get("to") == rule.T2:
                return tr("simple.undo.watched", type=ev.get("type"))
            return tr("simple.undo.asks" if first else "simple.undo.second", type=ev.get("type"))
    return ""


def _undo_failed(st: store.Store, entry: dict, text: str) -> UndoMessage:
    """An undo a person asked for that put nothing back, or not all of it. Simple mode: asking to undo is the
    person's judgment of the action, so it counts as a fault all the same, once (a retry counts no second one). Study
    mode: nothing is recorded, as in 1.3."""
    cfg = settings()
    if not simple(cfg) or entry["fault"]:
        return UndoMessage(text, False)
    agent, key = entry["agent"], entry["type"]
    recorded = st.recorded(agent, key)
    stakes, reversible = (recorded.stakes, recorded.reversible) if recorded else ("medium", True)
    sync_settings(st, cfg)
    events = record_outcome(st, cfg, agent=agent, type_key=key, stakes=stakes, reversible=reversible,
                            result="fault", source="undo", number=entry["id"])
    st.bump(agent, "faults")
    st.mark_undo_fault(entry["id"])                       # a retry of the undo counts no second fault
    now = " ".join(x for x in [tr("simple.undo.fault_anyway", type=key), _undo_now(events)] if x)
    return UndoMessage("\n".join([text, now]), False)


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
        veto = eligible and not simple(cfg) and benchmarks.veto(old_model, new_model, s.key)
        made = passport._carry(s, cfg, mode(cfg), veto=veto, strict=strict)
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
    return n is not None and s.series >= rule.required(s, n) and (s.tier == rule.T3 or rule.sessions_met(s))


def trusted(cfg: dict, s: rule.TypeState, n, stakes: str) -> bool:
    """The trusted start covers the type (``rule.trusted``) at these stakes. Such a type asks nothing Hermes alone
    would not ask; its first fault puts it under the study rule."""
    return s.stakes == stakes and rule.trusted(s, n, cfg.get("start"), mode(cfg))


def _due_key(agent: str, type_key: str) -> str:
    return f"spot_due:{agent}:{type_key}"


def _decide(st: store.Store, agent: str, act, n, cfg: dict, session: str, nobody, rng, local_ok: bool = False,
            runs: bool = False):
    """(recorded state, state at today's stakes, decision, suspended) for one call. ``local_ok``: ``_local_ok`` for
    the call; ``runs``: a chained line with a segment that asks on its own after outside content (``_chain_runs``)."""
    recorded = st.recorded(agent, act.type)
    s = st.get_state(agent, act.type, act.stakes, act.reversible)
    suspended = _suspended(st, session)
    decision = rule.decide(s, n, cfg["spot"], suspended=suspended, rng=rng, mode=mode(cfg))
    if not _earned(recorded, act, s, n, decision) or ST.copy_unchecked:
        decision = rule.ASK                             # copy_unchecked: this record may be a copy, not yet settled
    # A check drawn while nobody could answer stays due (sticky): every action of the type is that check until a
    # person answers one. Under cron or --yolo it is blocked (pre_tool_call); retrying never draws past it.
    if decision in (rule.ALLOW, rule.SPOT) and st.get_meta(_due_key(agent, act.type)):
        decision = rule.SPOT
    free = trusted(cfg, s, n, act.stakes)
    if free and simple(cfg) and s.distrusted and (recorded is None or recorded.stakes != act.stakes):
        free = False                                    # freedom earned back counts at the stakes it was earned at
    if (decision == rule.ASK and not ST.copy_unchecked and free
            and (not suspended or (act.reversible and act.type.startswith("file:") and not runs) or local_ok)):
        # trusted start: run as Hermes would, with an undo if possible; after outside content, undoable file writes only
        decision = rule.WATCH
    if decision != rule.ASK and _held_by(st, agent, act.type):
        decision = rule.ASK                             # a sensitive kind waits while its tool's fault is unredeemed
    if decision != rule.ASK and st.doubted(agent, act.type):
        decision = rule.ASK                             # a verifier doubted an action of this kind (#6)
    return recorded, s, decision, suspended


def _local_ok(cfg: dict, act, tool: str, args: dict, cwd: str) -> bool:
    """Simple mode: a local command that changes nothing outside the project and can be taken back, allowed after
    outside content too: every segment of the line is mkdir, git add, or git commit without -c in a repository with
    no active hook (``_git_hooks``); no substitution, redirect or variable."""
    if not simple(cfg) or act.type not in params.SUSPENDED_LOCAL or tool != "terminal":
        return False
    command = str(args.get("command", ""))
    if any(c in command for c in "$`<>\n\r"):
        return False
    segments = classify._segments(command)
    if not segments:
        return False
    for words in segments:
        prog, sub = os.path.basename(words[0]), words[1:2]
        if prog == "mkdir" or (prog == "git" and sub == ["add"]):
            continue
        if prog == "git" and sub == ["commit"] and "-c" not in words and not _git_hooks(cwd):
            continue
        return False
    return True


def _chain_held(cfg: dict, chain, agent: str, args: dict, deadline: float):
    """Simple mode: the first kind of a chained line that would not be free on its own now, for this agent: one of
    its programs, its ``git rm`` or ``git mv``, or ``file:shell`` for its writing segments beside an rm. Read as
    ``_decide`` reads it: the owner's setting, the series length for those stakes (none when they are capped), the
    trusted start (``trusted``: pinned, on trial, distrusted...), a mistake not yet redeemed (watched or asking),
    a verifier's doubt, a parent's hold. Returned as the action the whole line is then asked as, with that kind's
    type, stakes and reason; None when every kind is free."""
    with _locked(deadline):
        st = store_()
        for raw, stakes, reversible in chain.checks:
            t = classify.same_program(raw)
            ruled = classify._override(t, stakes, cfg["overrides"], raw=raw)
            if ruled == classify.FREE:
                continue                                    # the owner set it free
            seg = classify.Action(type=t, stakes=ruled, reversible=reversible,
                                  summary=classify._summary("terminal", args, t, cfg["vocabulary"]))
            n = params.required_n(cfg["risks"], ruled) if ruled in params.LEVELS else None
            if n is None or classify.RANK[ruled] > classify.RANK[classify.MEDIUM]:
                return seg
            recorded, s = st.recorded(agent, t), st.get_state(agent, t, ruled, reversible)
            free = trusted(cfg, s, n, ruled)
            if free and s.distrusted and (recorded is None or recorded.stakes != ruled):
                free = False                                # freedom earned back counts at its own stakes
            if (not free or _marked(recorded) or (recorded is not None and recorded.pinned)
                    or st.doubted(agent, t) or _held_by(st, agent, t)):
                return seg
    return None


HOOK_FILES = (".husky", ".pre-commit-config.yaml", "lefthook.yml", ".lefthook.yml")


def _git_hooks(cwd: str) -> bool:
    """A commit here could run code: a hook in .git/hooks (anything but a .sample), a core.hooksPath in the
    repository's or the user's git config, a hook manager's file at the root (.husky/, pre-commit, lefthook), or a
    repository Tenure cannot read plainly (a .git file, no repository). Read only."""
    d = os.path.abspath(cwd or ".")
    while True:
        git = os.path.join(d, ".git")
        if os.path.lexists(git):
            break
        parent = os.path.dirname(d)
        if parent == d:
            return True
        d = parent
    if os.path.islink(git) or not os.path.isdir(git):
        return True                                     # a worktree or a submodule: its hooks live elsewhere
    try:
        if any(not n.endswith(".sample") for n in os.listdir(os.path.join(git, "hooks"))):
            return True
    except FileNotFoundError:
        pass
    except OSError:
        return True
    for config in (os.path.join(git, "config"), os.path.join(os.path.expanduser("~"), ".gitconfig")):
        try:
            with open(config, encoding="utf-8", errors="replace") as f:
                if "hookspath" in f.read(1_000_000).lower():
                    return True
        except FileNotFoundError:
            continue
        except OSError:
            return True
    return any(os.path.lexists(os.path.join(d, name)) for name in HOOK_FILES)


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


FILE_PROGRAMS = frozenset({"rm", "rmdir", "mv", "cp"})   # their targets are files tenure reads, saved first or not


def _file_program(type_key: str) -> bool:
    """A plain file command whose files tenure could not save (a folder too large, a special file): it can tell what
    it changes, it cannot keep a copy."""
    parts = type_key.split(":")
    return len(parts) == 2 and parts[0] == "shell" and parts[1] in FILE_PROGRAMS


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
                 unsaved_listed: bool = False,
                 held: str | None = None, doubted: bool = False, fresh: list | None = None,
                 exec_files: list | None = None, taint_from: str = "", simple: bool = False,
                 lifts: bool = False, segments: int = 0, unknown: str = "") -> str:
    stakes = stakes_name(act.stakes)
    if decision == rule.SPOT:
        return tr("ask.spot", summary=act.summary, type=act.type, spot=round(1 / spot))
    if doubted:                                         # a verifier's doubt (#6): the reason for this question
        why = tr("ask.why.doubt", type=act.type)
    elif fresh:                                         # write then run (audit 19/11)
        why = tr("ask.why.fresh_script", files=", ".join(fresh[:3]))
    elif exec_files:
        why = tr("ask.why.exec_file", files=", ".join(exec_files[:3]))
    elif n is None and simple and unknown:              # files it could not identify: say what it could not read
        why = tr("simple.ask.unknown", type=act.type, reason=tr(f"unknown.why.{unknown}"))
    elif n is None:                                     # simple mode: high stakes, or capped by the owner's settings
        why = ((tr("simple.ask.always", type=act.type) if act.stakes == "high" or not params.simple_covers(act.type)
                else tr("simple.ask.settings", type=act.type)) if simple else
               tr("ask.why.capped", type=act.type, stakes=stakes, n=s.successes))
    elif suspended:
        why = tr("simple.ask.suspended" if simple else
                 "ask.why.suspended_trusted" if trusted_start else "ask.why.suspended")
        if taint_from:                                  # which call suspended it: a tool, and a host if any
            why += " " + tr("simple.ask.suspended_from" if simple else "ask.why.suspended_from", source=taint_from)
    elif s.trial_left:
        why = tr("ask.why.trial", type=act.type, n=s.trial_left)
    elif s.trial_wait:
        why = tr("ask.why.trial_wait", type=act.type, n=s.trial_wait)
    elif earned_at and earned_at != act.stakes:
        why = (tr("simple.ask.other_stakes", type=act.type) if simple else
               tr("ask.why.other_stakes", type=act.type, earned=stakes_name(earned_at), stakes=stakes))
    elif unsaved:
        why = tr(("simple.ask.unsaved_files" if unsaved_listed else "simple.ask.unsaved") if simple
                 else "ask.why.unsaved", type=act.type)
    elif held:                                          # before the trusted start's own reasons: name what holds it
        why = tr("ask.why.held", type=act.type, held=held)
    elif simple and s.pinned:                           # the owner's word: it asks until the owner frees it
        why = tr("trust.ask.pinned", type=act.type, command=f"/tenure trust {act.type}")
    elif simple and not rule.simple_eligible(s, n):     # what leaves the machine, high stakes: always asked
        why = tr("simple.ask.always", type=act.type)
    elif simple and s.tier != rule.T2 and act.reversible and act.stakes in params.WALD:
        why = tr("simple.ask.mistakes", type=act.type, n=_to_t2(s))
    elif simple:
        why = tr("simple.ask.mistake", type=act.type, n=max(n - s.series, 1))
    elif trusted_start and _uncovered_local(act, s, n):
        why = tr("ask.why.untrusted", type=act.type, stakes=stakes)
    elif s.tier == rule.T1 and s.faults and act.reversible and act.stakes in params.WALD:
        why = tr("ask.why.climb", type=act.type, stakes=stakes, n=_to_t2(s))   # the next step, not the far one
    else:
        why = tr("ask.why.series", type=act.type, stakes=stakes, series=s.series, required=rule.required(s, n),
                 sessions=len(rule.session_counts(s)), needed=rule.sessions_needed(s.stakes))
        if s.provisional:
            why += " " + tr("ask.why.provisional", n=s.provisional)
    if per_session:
        return tr("simple.ask.prompt_session" if simple else "ask.prompt_session", summary=act.summary, why=why)
    if lifts:                                           # a no doubts the content, not the agent: no fault
        summary = act.summary + (" " + tr("simple.ask.more_segments", n=segments) if segments else "")
        return tr("simple.ask.prompt_lift", summary=summary, why=why)   # a long chained line: what the cut hides
    if simple:
        return tr("simple.ask.prompt", summary=act.summary, why=why) + "\n" + tr("simple.ask.always_button")
    return tr("ask.prompt", summary=act.summary, why=why) + "\n" + tr("ask.always")


# Seconds: Hermes runs a longer terminal call in the background (its TERMINAL_MAX_FOREGROUND_TIMEOUT default).
FOREGROUND_MAX = 600


BACKGROUND_KEYS = ("auto_backgrounded", "promoted_from_foreground")   # Hermes' markers in a terminal result
# Hermes stopped the call before it ran (tools/terminal_tool.py, _error_json): its own approval refused, timed out,
# undelivered (status "blocked"), or left pending (status "pending_approval", approval_pending); an action gate's
# "approval_required". The hook's own status then says only "error".
NOT_RUN = frozenset({"blocked", "pending_approval", "approval_required"})


def _not_run(tool: str, result) -> bool:
    """The result of a terminal call Hermes did not run: an error result whose ``status`` is in ``NOT_RUN``. Only
    the terminal tool's result is read: another tool (an MCP server, the code execute_code runs) writes that field
    itself."""
    if tool != "terminal":
        return False
    try:
        data = json.loads(result) if isinstance(result, (str, bytes)) else result
    except ValueError:
        return False
    return (isinstance(data, dict) and str(data.get("status") or "").strip().lower() in NOT_RUN
            and bool(data.get("error") or data.get("approval_pending")))


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
            launched: bool = False, written: list[str] | None = None, cwd: str = "", unjudged: bool = False,
            label: str = "", more: int = 0, cut: bool = False, untouched: bool = False,
            count: int = 0, fault_type: str | None = None, hidden: bool = False) -> list[str]:
    """The verified outcome of one pending decision, from facts gathered before the transaction: was the call stopped
    (``blocked``), did the tool fail, what did the automatic check of the written files say. The check judges every
    action that ran, even one nobody answered. A background launch (``launched``) is neutral: the command's own
    outcome is not known when the call returns. ``written`` (absolute paths) only names the files in the owner's
    messages: it is stored nowhere. An action that ran gets a number in ``recent`` (a fault is born flagged), handed
    on as ``p["n"]`` and ``p["n_at"]``; its undo entry, if any, as ``p["undo_id"]``. ``untouched``: a failed call whose
    saved files are all as they were, or that Hermes did not run: it keeps no undo, no notice and no end-of-turn line
    (its outcome is unchanged). ``count``: the files the undo of a chained line holds, shown as "(+N files)" (end of
    turn, /tenure). ``fault_type``: the kind a broken file of a chained line is blamed on (the segment that wrote it,
    ``file:shell``), not the line's own. ``hidden``: a terminal line that exited 0 but whose code may hide an earlier
    program's failure (``classify.hides_failure``): no verified success, neutral, except an act-then-tell credit,
    which comes from the action kept through its undo window, not from the code. Returns the owner's messages."""
    try:                                                    # display only: it never aborts a settlement
        home = os.path.expanduser("~")
        shown = [_show(x, cwd, home) for x in written or []]
        what = _with_what(_join_shown(shown))
    except Exception:
        log.debug("tenure: the written files could not be shown", exc_info=True)
        shown, what = [], ""
    phase, agent, key = p["phase"], p["agent"], p["type"]
    blamed = fault_type if reason and fault_type and fault_type != key else key   # the check's fault: its writer
    acted = phase in ("notify", "unwatched")                # T2 acted, then told the owner (who may not be there)
    decided = acted or phase in ("approved", "alone")       # approved by a person, or run by an earned tier
    spot = phase == "approved" and p["decision"] == rule.SPOT
    if blocked:                                             # never ran
        result_source = ("neutral", "blocked" if decided else "nobody")
    elif reason:                                            # a file it broke, even if the call then failed
        result_source = ("fault", "spot" if spot else "check")
    elif failed:
        result_source = ("neutral", "error" if decided else "nobody")
    elif launched:
        result_source = ("neutral", "background")
    elif unjudged:                                          # a file broken before is still broken: proves nothing
        result_source = ("neutral", "ambiguous")
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
    deferred = phase == "notify" and p["decision"] == rule.NOTIFY and result_source == ("success", "notify")
    if hidden and result_source[0] == "success" and not deferred:
        result_source = ("neutral", "ambiguous")            # exit 0 is the last program's: proves nothing before it
    if p["decision"] == rule.WATCH and result_source[0] == "success":
        now = st.get_state(agent, key, p["stakes"], p["reversible"])
        if not trusted(cfg, now, params.required_n(cfg["risks"], p["stakes"]), p["stakes"]):
            result_source = ("neutral", "alone")            # trusted when it ran, not now (start changed): no credit
    if deferred:                                            # earned T2: credited when its undo window closes unused
        events = []
        _bump(st, agent, "neutral", alone=True)
    else:
        moved = blamed != key and result_source[0] == "fault"
        events = record_outcome(st, cfg, agent=agent, type_key=blamed if moved else key, stakes=p["stakes"],
                                reversible=True if moved else p["reversible"], result=result_source[0],
                                source=result_source[1], session=st.root_of(p["session"]))
        _bump(st, agent, result_source[0], checked=phase == "approved",
              alone=not blocked and (acted or phase == "alone"))
    posts = []
    undo_id = None
    broke = acted and not blocked and failed and bool(p.get("snap_id")) and not reason and not untouched
    p["undo_id"] = None
    if acted and not blocked and (not failed or broke or (reason and p.get("snap_id"))):   # files saved: revertible,
        undo_id = st.add_undo(agent, key, p["snap_id"], fault=bool(reason) and blamed == key)   # a person undoing
        p["undo_id"] = undo_id                              # the line blames the line, even after a failure
        if count and simple(cfg):
            st.set_meta(UNDO_FILES + str(undo_id), str(count))     # a chained line: /tenure says "(+N files)"
        if broke:
            st.set_meta(UNDO_FAILED + str(undo_id), "1")    # undoing a failed call that changed nothing is no fault
        if deferred:
            st.add_credit(undo_id, st.root_of(p["session"]), p["stakes"], p["reversible"])
        # ``watched``: simple mode lists it in the line at the end of the turn (a free action says nothing there, and
        # the desktop half shows no toast for it either). ``shown``: the type as the pages show it with names hidden.
        _push("acted", {"agent": agent, "type": key, "shown": passport.redact_type(key), "undo_id": undo_id,
                        "fault": bool(reason), "profile": _profile_name(), "simple": simple(cfg),
                        "watched": bool(simple(cfg) and not reason and (deferred or broke))})
        if reason:
            posts.append(tr("simple.settle.acted_fault" if simple(cfg) else "settle.acted_fault", type=blamed,
                            reason=reason, what=what, command="/tenure undo", id=undo_id))
        elif broke and not simple(cfg):
            posts.append(tr("settle.acted_failed", type=key, what=what, command="/tenure undo", id=undo_id))
        elif simple(cfg):                       # simple mode: a free action says nothing, a watched one joins the
            if deferred or broke:               # line said at the end of the turn, and so does a failed one
                posts.append(Watched(p["session"], undo_id, label or _join_shown(shown) or key, more=more, cut=cut,
                                     files=_join_shown(shown) if label else "", count=count))
        else:
            text = tr("settle.acted", type=key, what=what, command="/tenure undo", id=undo_id)
            if deferred:                                # rule B/2: only a person's "seen" counts toward acting alone
                text = _with_ok(text, [undo_id])
            posts.append(Acted(text, p["session"], key, undo_id, shown))
            posts[-1].ok_hint = deferred
    elif reason:
        posts.append(tr("simple.settle.check_failed" if simple(cfg) else "settle.check_failed", type=blamed,
                        reason=reason, what=what))
    if not blocked:                             # it ran: numbered, so the owner can flag it (a fault is born flagged)
        at = time.time()
        p["n"], p["n_at"] = st.add_recent(p["session"], agent, key, at=at, flagged=result_source[0] == "fault",
                                          undo_id=undo_id, call=anon(p.get("call"))), at
    return posts + _say(events, cfg["spot"], mode(cfg))


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
                    posts += _say(sync_settings(st, cfg), cfg["spot"], mode(cfg))
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


# A person's word, run or called: ``ok``, ``excuse`` or ``trust`` after Hermes' CLI (its options, long ones included,
# before ``tenure``), ``python -m tenure`` or the slash command; the core and CLI functions that record it.
_WORD_FUNCS = r"seen|excuse|_see|owner_trust|owner_free|owner_pin|trust_set|slash|_slash|excuse_cmd|execute"
# The word itself: ok or excuse (alone they list, and the CLI refuses them to the agent anyway), trust with a kind
# (alone it lists, read only), after a command line that runs tenure or Hermes.
_WORD = r"\s+['\"]?(?:ok|excuse|trust[ \t]+['\"]?(?!-)[^\s'\";&|])"
_HERMES_CLI = r"(?:\bhermes\b|-m[ \t]+hermes_cli(?:\.main)?\b)"           # hermes, or python -m hermes_cli.main
_PERSON_ONLY = re.compile(
    rf"(?:{_HERMES_CLI}(?:[ \t]+--?[^\s-]\S{{0,40}}(?:[ \t]+[^\s-]\S{{0,80}})?){{0,6}}[ \t]+['\"]?tenure['\"]?"
    rf"|-m[ \t]+tenure(?:\.cli)?){_WORD}"
    rf"|\btenure\.(?:cli\.|rule\.)?(?:{_WORD_FUNCS})\s*\("
    r"|\bcore\.(?:seen|excuse|_see|owner_trust)\s*\("
    rf"|\bfrom[ \t]+tenure\b[^\n]{{0,80}}?\bimport\b[^\n]{{0,200}}?\b(?:{_WORD_FUNCS})\b", re.I)
# The chat's slash command: typed into a chat (computer_use), or handed to Hermes by a command line that runs it
# (``hermes chat -q "/tenure trust X"``). A shell alone cannot run it: a commit message or a grep naming it is left
# alone.
_SLASH_WORD = re.compile(rf"(?:^|\s|['\"])/tenure{_WORD}", re.I)
_RUNS_HERMES = re.compile(r"(?:^|[\s;&|(`'\"])(?:hermes|-m[ \t]+hermes_cli(?:\.main)?)(?=[\s'\",)]|$)", re.I)
# The same functions through a module name that is not tenure's (``cli.slash(``, ``rule.owner_free(``): only in a
# text that names tenure somewhere, so another project's ``cli.execute(`` is left alone.
_PERSON_ONLY_CALL = re.compile(rf"\b(?:core|cli|rule)\.(?:{_WORD_FUNCS})\s*\(")
_NAMES_TENURE = re.compile(r"tenure", re.I)
# The arguments that run, or are typed: a terminal command, execute_code's code, the text computer_use types or sets
# in a field (``type``, ``set_value``; tools/computer_use/schema.py). Never a file's text or a message.
_RUNS = {"terminal": ("command",), "execute_code": ("code",), "computer_use": ("text", "value")}
_TYPED = frozenset({"computer_use"})          # keys typed into a window, maybe the chat: the slash command counts


def _person_only(tool: str, args: dict) -> bool:
    """A tool call that would run ``tenure ok``, ``tenure excuse`` or ``tenure trust`` (or their functions): those are a
    person's word on the agent's work, never the agent's own, whatever terminal or approval it could get. Blocked
    outright, in what a call runs or types (a terminal command, ``execute_code``'s code, ``computer_use``'s text),
    never a file being written or a message: tenure's own source and docs name these commands. Defence in depth, not
    a wall: the CLI and the core functions also refuse them in one of the agent's own processes (``agent_process``)
    and the CLI without a real terminal; an agent that builds the name at run time, unsets the markers and opens a pty
    still needs an approval of a command that names Hermes (capped)."""
    try:
        for name in _RUNS.get(tool, ()):
            text = args.get(name)
            if not isinstance(text, str):
                continue
            if _PERSON_ONLY.search(text) or (_PERSON_ONLY_CALL.search(text) and _NAMES_TENURE.search(text)):
                return True
            if _SLASH_WORD.search(text) and (tool in _TYPED or _RUNS_HERMES.search(text)):
                return True
        return False
    except Exception:
        return False


def pre_tool_call(tool_name="", args=None, session_id="", tool_call_id="", task_id="", **kwargs):
    """The decision for one call: None to let it run (free, acting alone, or acting then notifying with its files
    saved), else Hermes' approval gate with a rule key that ends with a fresh uuid. Any internal error, a busy store
    included, asks, unless the call was already classified free. Every call that reaches the record first expires
    stale pending rows. Files are saved before the transaction, and the decision is checked again inside it. A
    command line's files are read once per call (``classify.one_reading``)."""
    with classify.one_reading():
        return _pre_tool_call(tool_name, args, session_id, tool_call_id, task_id)


def _pre_tool_call(tool_name, args, session_id, tool_call_id, task_id):
    act, taken = None, None
    deadline = time.monotonic() + HOOK_BUDGET
    try:
        cfg = settings()
        if not cfg["enabled"]:
            return None
        tool, args = str(tool_name or ""), (args if isinstance(args, dict) else {})
        if _person_only(tool, args):                              # the agent marking its own work seen, or excusing it
            return {"action": "block", "message": tr("ask.person_only")}
        cwd = call_cwd(tool, args, session_id, task_id)
        wide = simple(cfg)                                  # simple mode: rm -r of a folder and rm globs can be saved
        act = classify.classify(tool, args, cwd=cwd, overrides=cfg["overrides"], vocabulary=cfg["vocabulary"],
                                wide=wide)
        chain = (classify.undo_chain(str(args.get("command", "")), cwd)
                 if wide and tool == "terminal" and act.reversible else None)
        runs, held = bool(chain and chain.runs), None
        if chain and chain.checks:                          # every kind of the line must be free now, even when the
            held = _chain_held(cfg, chain, agent_of(str(session_id or task_id or ""), deadline), args, deadline)
            if held is not None:                            # owner set the line's own kind free
                act, runs = held, False                     # the line is asked as that kind, for its reason
        local_ok = _local_ok(cfg, act, tool, args, cwd)
        if act.stakes == classify.FREE:
            return None
        purged = _purge()
        uid = uuid.uuid4().hex
        if act.stakes == classify.CAP:                      # a key of its own each time: never "for this session"
            key = (("simple.ask.net_code" if wide else "ask.net_code") if act.type == classify.NET_CODE[0]
                   else "simple.ask.capped" if wide else "ask.capped")      # downloaded code is said plainly
            return {"action": "approve", "rule_key": f"{PREFIX}:cap:{act.type}:{uid}",
                    "message": tr(key, summary=act.summary, type=act.type)}
        call, sid = str(tool_call_id or ""), str(session_id or task_id or "")
        session, agent, nobody = anon(sid), agent_of(sid, deadline), nobody_answers()
        n = params.required_n(cfg["risks"], act.stakes)
        if call:
            with ST.mem:
                _remember(ST.kinds, _call_key(session, call, tool, args), act.type)
        if call:                                            # files that do not parse yet: the check skips them after
            written = classify.files_written(tool, args, cwd, wide=wide)
            bad = (proofs.broken(written) - _touched(session)) if written else frozenset()
            with ST.mem:                                    # set or cleared: a reused call id never inherits it
                if bad:
                    ST.broken[(session, call)] = bad
                    ST.broken.move_to_end((session, call))
                    while len(ST.broken) > MAX_SUMMARIES:
                        ST.broken.popitem(last=False)
                else:
                    ST.broken.pop((session, call), None)
        if call:                                            # an undo is only wired through a call id
            with _locked(deadline):
                preview = _decide(store_(), agent, act, n, cfg, session, nobody, _NoSpot, local_ok, runs)[2]
            if held is not None:
                preview = rule.ASK
            if preview in (rule.NOTIFY, rule.WATCH):
                paths = classify.files_written(tool, args, cwd, wide=wide)
                taken = (undo.snapshot(paths, data_dir(), key=undo_key(deadline), cwd=cwd,
                                       home=os.path.expanduser("~"), git=list(chain.git) if chain else None,
                                       git_specs=list(chain.git_specs) if chain else None)
                         if paths else None)
            with ST.mem:                                    # a reused call id never inherits older files
                if taken:
                    _remember(ST.saved, _call_key(session, call, tool, args),
                              (list(paths), list(chain.writes) if chain else []))
                else:
                    ST.saved.pop(_call_key(session, call, tool, args), None)
        posts, directive, snap = [], None, taken
        with txn(deadline) as st:
            posts += _say(sync_settings(st, cfg), cfg["spot"], mode(cfg))
            posts += _say(_expire(st, cfg), cfg["spot"], mode(cfg))
            posts += _say(_credit_due(st, cfg), cfg["spot"], mode(cfg))
            recorded, s, decision, suspended = _decide(st, agent, act, n, cfg, session, nobody, ST.rng, local_ok,
                                                              runs)
            if held is not None:
                decision = rule.ASK                         # a program of the line is not free now: it asks
            unknown = (classify.unknown_reason(str(args.get("command", "")))
                       if wide and tool == "terminal" and act.type == "file:unknown" else "")
            if unknown and st.get_meta(UNKNOWN_WHY) != unknown:
                st.set_meta(UNKNOWN_WHY, unknown)           # /tenure trust says it too
            if purged:
                st.drop_undo_meta((UNDO_FILES, INDEX_PENDING), time.time() - UNDO_WINDOW)
            fresh, exec_files = [], []                      # computed even when it asks anyway: never a session key
            if tool == "terminal":                              # a script the agent wrote, run now: asked once
                fresh = st.written_recently(classify.scripts_run(str(args.get("command", "")), cwd, wide=wide))
            outside = _outside(st, session, suspended)
            if outside:                                         # after outside content, writing code is code
                exec_files = [x for x in classify.files_written(tool, args, cwd, wide=wide)
                              if classify.runs_on_execution(x)]
                if wide and tool == "terminal":                 # git apply / git am: the files the patch names
                    targets = classify.patch_targets(str(args.get("command", "")), cwd)
                    exec_files += ([x for x in targets if classify.runs_on_execution(x)] if targets is not None
                                   else [os.path.join(cwd, "(patch)")])     # a patch it cannot read: asked
            only_fresh = bool(fresh) and not exec_files and decision != rule.ASK   # it would not have asked otherwise
            if fresh or exec_files:
                decision = rule.ASK
            with ST.mem:                                    # a reused call id never carries an older script
                if fresh:
                    _remember(ST.fresh, (session, call), fresh)
                else:
                    ST.fresh.pop((session, call), None)
            watched = decision == rule.WATCH
            # Simple mode frees kinds the trusted start leaves out (rm, mv...) only with their files saved first, unless
            # a person freed the kind by hand (/tenure trust KIND): then it runs even when no undo can be prepared.
            needs_undo = watched and simple(cfg) and not rule.trust_covers(act.type) and not s.owner_freed
            listed = False                                  # the call names files it changes (they may not be saved)
            if watched:                                     # files saved: act then tell, with an undo; else run alone
                listed = bool(classify.files_written(tool, args, cwd, wide=wide))
                files = bool(snap) or listed
                # files that could not be saved: ask (below), unless a person freed the kind without an undo
                decision = (rule.NOTIFY if snap else rule.ASK if (suspended and not local_ok) or needs_undo
                            else rule.ALLOW if s.owner_freed and simple(cfg) else rule.NOTIFY if files else rule.ALLOW)
                if needs_undo and not suspended:            # /tenure trust names a kind tenure cannot undo (display)
                    noundo = not snap
                    if noundo != bool(st.get_meta(NOUNDO + act.type)):
                        st.set_meta(NOUNDO + act.type, "1" if noundo else "")
            if decision != rule.NOTIFY:
                snap = None                                 # the record changed since the preview: no undo needed
            unsaved = (decision == rule.NOTIFY and snap is None) or (needs_undo and not snap and not suspended)
            if unsaved:
                decision = rule.ASK                         # no undo can be prepared: ask instead
            row = dict(call=call, agent=agent, type=act.type, stakes=act.stakes, reversible=act.reversible,
                       decision=rule.WATCH if watched and decision in (rule.ALLOW, rule.NOTIFY) else decision,
                       session=session)
            if decision in (rule.ALLOW, rule.NOTIFY):
                st.add_pending(uid, phase="alone" if decision == rule.ALLOW else "unwatched" if nobody else "notify",
                               rule_key="",
                               snap_id=snap, **row)
            elif nobody and decision == rule.SPOT:     # a check nobody can answer: blocked, neutral, never unchecked
                st.add_pending(uid, phase="nobody", rule_key="", **row)
                directive = {"action": "block", "message": tr("ask.spot_nobody", type=act.type, why=nobody)}
                if not st.get_meta(_due_key(agent, act.type)):
                    st.set_meta(_due_key(agent, act.type), "1")
                    posts.append(tr("notice.spot_due", type=act.type, why=nobody))
            else:
                kind = ("ask" if nobody else "spot" if decision == rule.SPOT else "capped" if n is None
                        else "trial" if s.trial_left or s.trial_wait else "ask")
                # Under the trusted start, an ask for inline code, or one only the suspension causes, has a key stable
                # for the session: "Allow for this session" then covers that type until the session ends.
                # A file change whose files could not be saved is asked about each time: a session answer must
                # never let a write run without its undo.
                no_undo = act.reversible and not snap and bool(classify.files_written(tool, args, cwd, wide=wide))
                per_session = (cfg.get("start") == "trusted" and not nobody and decision == rule.ASK and not no_undo
                               and not s.pinned                                 # the person said: every time
                               and fields.parent_of(act.type) is None           # never for a category kind
                               and not st.doubted(agent, act.type)              # a doubt is asked, whatever the grant
                               and not exec_files and not (fresh and outside)    # code written after outside content
                               and (act.type in params.SESSION_TYPES or (suspended and trusted(cfg, s, n, act.stakes))
                                    or _uncovered_local(act, s, n) or only_fresh)
                               and (only_fresh or not fresh))                   # another reason asks each time
                # After outside content, one session answer covers every covered type (one key for the session);
                # inline code and uncovered local commands are allowed one type at a time.
                scope = ("fresh" if only_fresh else
                         "suspended" if suspended and trusted(cfg, s, n, act.stakes) and act.type not in params.SESSION_TYPES
                         else act.type)
                # Simple mode: a question only the suspension asks lifts it once a person approves it (even once).
                lifts = (simple(cfg) and suspended and not nobody and not fresh and not exec_files
                         and not st.doubted(agent, act.type) and not _held_by(st, agent, act.type)
                         and (trusted(cfg, s, n, act.stakes)
                              or rule.decide(s, n, cfg["spot"], suspended=False, rng=_NoSpot,
                                             mode=rule.SIMPLE) == rule.NOTIFY))
                if lifts:
                    per_session, kind = False, "lift"
                key = f"{PREFIX}:session:{scope}:{session}" if per_session else f"{PREFIX}:{kind}:{act.type}:{uid}"
                st.add_pending(uid, phase="nobody" if nobody else "asked", rule_key=key, **row)
                directive = {"action": "approve", "rule_key": key,
                             "message": _ask_message(act, s, n, cfg["spot"], decision=decision, suspended=suspended,
                                                     taint_from=_taint_label(session),
                                                     unsaved=unsaved,
                                                     unsaved_listed=listed or _file_program(act.type) or (
                                                         unsaved and bool(classify.files_written(tool, args, cwd,
                                                                                                 wide=wide))),
                                                     per_session=per_session, trusted_start=cfg.get("start") == "trusted",
                                                     doubted=st.doubted(agent, act.type),
                                                     fresh=[_show(x, cwd, os.path.expanduser("~")) for x in fresh],
                                                     exec_files=[_show(x, cwd, os.path.expanduser("~"))
                                                                 for x in exec_files],
                                                     earned_at=recorded.stakes if recorded else None,
                                                     held=_held_by(st, agent, act.type), simple=simple(cfg),
                                                     lifts=lifts,
                                                     segments=classify.hidden_segments(str(args.get("command", "")))
                                                     if tool == "terminal" else 0, unknown=unknown)}
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
                posts += _say(sync_settings(st, cfg), cfg["spot"], mode(cfg))
                # A refused action of an earned T3 is what a spot check is: detection, never excusable.
                checked = p["phase"] == "alone" and p["decision"] == rule.ALLOW
                evs = record_outcome(st, cfg, agent=p["agent"], type_key=p["type"], stakes=p["stakes"],
                                     reversible=p["reversible"], result="fault",
                                     source="spot" if checked else "refusal", session=p["session"])
                posts += _say(evs, cfg["spot"], mode(cfg)) + ([] if checked else _excuse_hint(st, evs))
                _bump(st, p["agent"], "fault")
                p = None
            if p is None or p["phase"] != "asked" or (key and p["rule_key"] != key):
                pass                                        # not one of our open asks
            elif verdict == "approved":
                st.set_phase(p["id"], "approved")
                if p["rule_key"].startswith(f"{PREFIX}:lift:") and simple(cfg):
                    _lift(st, p["session"])                 # a person's yes, even once: the session works as before
                with ST.mem:
                    ran = ST.fresh.pop((p["session"], p["call"]), None)
                st.forget_written(ran)                      # approved once: it runs without asking until rewritten
            else:
                st.pop_pending(p["id"])
                with ST.mem:                                # refused or unanswered: its fresh scripts stay fresh
                    ST.fresh.pop((p["session"], p["call"]), None)
                posts += _say(sync_settings(st, cfg), cfg["spot"], mode(cfg))
                if verdict == "refused" and p["rule_key"].startswith(f"{PREFIX}:lift:") and simple(cfg):
                    result, source = "neutral", "blocked"   # the person doubts the content, not the agent
                elif verdict == "refused":
                    result, source = "fault", ("spot" if p["decision"] == rule.SPOT else "refusal")
                else:
                    result, source = "neutral", "timeout"
                evs = record_outcome(st, cfg, agent=p["agent"], type_key=p["type"], stakes=p["stakes"],
                                     reversible=p["reversible"], result=result, source=source, session=p["session"])
                posts += _say(evs, cfg["spot"], mode(cfg))
                if source == "refusal":                     # a refused spot check is detection: not excusable
                    posts += _excuse_hint(st, evs)
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
    automatic check of the written files, both gathered before the transaction. The disk is read
    afresh, once (``classify.one_reading``)."""
    with classify.one_reading():
        return _post_tool_call(tool_name, args, result, session_id, tool_call_id, status, error_type, task_id)


def _post_tool_call(tool_name, args, result, session_id, tool_call_id, status, error_type, task_id):
    try:
        tool, args = str(tool_name or ""), (args if isinstance(args, dict) else {})
        cwd = call_cwd(tool, args, session_id, task_id)
        _follow_cwd(tool, args, result, session_id, task_id)
        session = anon(session_id or task_id)
        wide = simple()
        ran = str(status or "").strip().lower() != "blocked" and not _not_run(tool, result)
        with ST.mem:                                        # what was saved before it ran and is still there
            saved, writes = ST.saved.pop(_call_key(session, str(tool_call_id or ""), tool, args), None) or ([], [])
            kind = ST.kinds.pop(_call_key(session, str(tool_call_id or ""), tool, args), None)
        saved = [x for x in saved if os.path.lexists(x)]    # a deleted file can be neither judged nor run
        wrote = (classify.files_written(tool, args, cwd, wide=wide) or saved) if ran else []   # never ran: none
        _touch(session, wrote)                              # every call that ran, failed or not: its files are its own
        if wrote:                                           # running one of them later asks once (24 hours)
            try:
                with txn() as wst:
                    wst.add_written(wrote)
            except LockTimeout:
                log.warning("tenure: the files this call wrote could not be recorded: the store stayed busy")
        if tool == "execute_code" or classify.reads_external(tool, args, cwd):
            with ST.mem:
                first = session not in ST.tainted
            _taint(session)                                 # first: a label that fails never undoes a suspension
            try:
                label = _source_label(tool, args)
                with ST.mem:
                    seen = ST.taint_from.get(session)
                if seen is None:                            # suspended earlier (another process, before a restart):
                    with _locked():                         # that first call is unknown here, but it counts
                        earlier = not first or store_().is_tainted(session)
                    seen = ["?"] if earlier and not first else []
                with ST.mem:
                    _remember(ST.taint_from, session, (seen + [label])[-20:])
            except Exception:
                log.debug("tenure: the source of a suspension could not be named", exc_info=True)
            if first and settings().get("start") == "trusted" and not simple():
                _announce(tr("notice.suspended"))           # said once: the asks that follow stay short
        call = str(tool_call_id or "")
        if not call:
            return None
        with ST.mem:                                        # taken once, whatever happens to this call next
            before = ST.broken.pop((session, call), frozenset())
        with _locked():
            rows = store_().pending_rows(session, call)
        if not session and rows:            # outside any session, call ids recur: the type must match too
            cfg2 = settings()                 # the type it had before it ran: the disk has changed since
            kind = kind or classify.classify(tool, args, cwd=cwd, overrides=cfg2["overrides"],
                                             vocabulary=cfg2["vocabulary"], wide=wide).type
            rows = [r for r in rows if r["type"] == kind]
            if len(rows) > 1:
                _ambiguous(rows)
                return None
        if not rows:
            return None
        p = rows[0]
        # Hermes' own refusal is in the result (a call its approval stopped never ran). Simple mode reads it as
        # blocked; study mode keeps the outcome it had (neutral, error: the ledger and its replay do not change).
        not_run = not ran and str(status or "").strip().lower() != "blocked"
        blocked = str(status or "").strip().lower() == "blocked" or (wide and not_run)
        failed = not blocked and proofs.execution(tool, status, error_type, result) == "failed"
        untouched = False                   # a failed call that changed none of its saved files, or never ran: no undo
        if failed and p.get("snap_id"):
            try:
                untouched = not_run or undo.unchanged(p["snap_id"], data_dir(), key=undo_key())
            except Exception:               # a snapshot it cannot read: kept, the undo says why
                untouched = False
        launched = not blocked and not failed and _background(tool, args, result)
        hidden = (tool == "terminal" and not blocked and not failed
                  and classify.hides_failure(str(args.get("command", ""))))
        reason, paths, unjudged = None, [], False
        if not blocked and not launched:    # a failed call is judged too: "...; false" never hides a broken file
            paths = classify.files_written(tool, args, cwd, wide=wide) or saved
            reason, unjudged = proofs.judge_files(paths, before) if paths else (None, False)
        fault_type = None                   # a file a writing segment of a chain broke: that segment's fault
        if reason and writes:
            bad = next((x for x in paths if proofs.judge_files([x], before)[0]), None)
            mine = {os.path.realpath(w) for w in writes}
            fault_type = "file:shell" if bad and os.path.realpath(bad) in mine else None
        count = 0                           # a chained line: the files its one undo brings back, "(+N files)"
        if wide and tool == "terminal" and p.get("snap_id") and classify.chain_parts(str(args.get("command", ""))):
            count = undo.describe(p["snap_id"], data_dir()).get("existed", 0)
        cfg = settings()
        posts = []
        with txn() as st:
            path = st.path
            p = st.pop_pending(p["id"])                         # settled once, by whoever comes first
            if p is not None:
                posts += _say(sync_settings(st, cfg), cfg["spot"], mode(cfg))
                more, cut = _more_lines(tool, args)
                posts += _settle(st, cfg, p, blocked=blocked, failed=failed, reason=reason, launched=launched,
                                written=paths, cwd=cwd, unjudged=unjudged,
                                label=_label(tool, args, cfg["vocabulary"]), more=more, cut=cut, untouched=untouched,
                                hidden=hidden,
                                count=count, fault_type=fault_type)
        if p is not None and p.get("snap_id") and p.get("undo_id") is None:
            undo.discard(p["snap_id"], data_dir())          # committed, and no undo entry holds it: nothing to keep
        for text in posts:
            _announce(text)
        if p is not None and p.get("n") is not None:            # committed: remember what it did, in memory only
            try:
                summary = classify._summary(tool, args, p["type"], cfg["vocabulary"])
                with ST.mem:
                    _remember_summary(path, p["n"], p["n_at"], summary)
            except Exception:
                log.debug("tenure: the summary of action %s was not remembered", p["n"], exc_info=True)
    except LockTimeout:
        log.warning("tenure: post_tool_call skipped: the store stayed busy")
    except Exception:
        log.exception("tenure: post_tool_call failed")
    return None


def _ambiguous(rows: list[dict]) -> None:
    """Several live rows outside any session for one call id and type: none can be told apart, so none is settled as
    a success; each is recorded as neutral. One that acted with its files saved keeps an undo of its own snapshot."""
    cfg, posts = settings(), []
    with txn() as st:
        posts += _say(sync_settings(st, cfg), cfg["spot"], mode(cfg))
        for r in rows:
            p = st.pop_pending(r["id"])
            if p is not None:
                record_outcome(st, cfg, agent=r["agent"], type_key=r["type"], stakes=r["stakes"],
                               reversible=r["reversible"], result="neutral", source="ambiguous", session=r["session"])
                _bump(st, r["agent"], "neutral")
                if p.get("snap_id") and p["phase"] in ("notify", "unwatched"):     # it acted: each keeps its own
                    st.add_undo(p["agent"], p["type"], p["snap_id"], fault=False)  # snapshot, as its undo
    for text in posts:
        _announce(text)


def subagent_start(parent_session_id="", child_session_id="", **kwargs):
    """A child agent works from its parent's context: the child of a suspended parent starts suspended."""
    try:
        parent, child = anon(parent_session_id), anon(child_session_id)
        if not parent or not child or parent == child:
            return None
        try:
            with txn() as st:                               # its successes count in the root session (audit 19/11)
                st.set_root(child, parent)
        except LockTimeout:                             # kept in memory: the child never counts as a session of its own
            store.Store.roots[child] = store.Store.roots.get(parent, parent)
            log.warning("tenure: the subagent's root session is kept in memory only: the store stayed busy")
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
        if not tainted and simple():                    # a child that read outside content, even lifted since
            tainted = _lifted(child)
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
    if hasattr(ctx, "register_session_env"):           # mark the agent's own subprocesses: ok and excuse refuse them
        try:
            ctx.register_session_env([AGENT_CHILD], lambda _sid: {AGENT_CHILD: "1"})
        except Exception:
            log.warning("tenure: the agent-child marker could not be registered", exc_info=True)
    ctx.register_hook("post_approval_response", post_approval_response)
    ctx.register_hook("post_tool_call", post_tool_call)
    ctx.register_hook("post_llm_call", post_llm_call)
    ctx.register_hook("subagent_start", subagent_start)
    ctx.register_hook("subagent_stop", subagent_stop)
    from . import cli
    ctx.register_cli_command(name="tenure", help="What the agent did and what can be undone; undo, trust "
                                                     "(more: hermes tenure advanced)",
                             setup_fn=cli.setup, handler_fn=cli.run)
    ctx.register_command("tenure", handler=_slash,
                         description="What the agent did and what can be undone; undo, trust (more: /tenure advanced)")
