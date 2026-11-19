# Copyright 2026 Otsoa Dubief
# SPDX-License-Identifier: Apache-2.0
"""State and evidence, in one SQLite file per Hermes profile.

The CLI, the gateway and cron run in separate processes and may answer approvals at the same time: every
read-modify-write happens inside ``transaction()`` (BEGIN IMMEDIATE), so no update is lost. The ledger lives in the
same database, written in the same transaction as the state it explains, as a hash chain: each row carries the hash
of the previous one, so an exported evidence file can be checked line by line (``verify``). The ledger records
agents, action types, stakes, outcomes and anonymised sessions, never a whole command, a path or a message. A type
name can include a script, target or alias name taken from the command; the passport and the dashboard redact it.

A pending decision waits for its outcome under its own unique id. Providers reuse tool call ids across sessions
(``call_0`` every turn), so a row is found by (anonymised session, tool call id), and a live row is never replaced.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import time
import urllib.parse
from contextlib import contextmanager

from .rule import TypeState

log = logging.getLogger("tenure")

GENESIS = "0" * 64
SCHEMA_VERSION = "3"
BUSY_TIMEOUT = 5.0             # seconds a writer waits for another process's transaction, well under a hook's limit
TABLES = ("types", "pending", "sessions", "undo", "stats", "meta", "ledger", "recent")
RECENT_WINDOW = 24 * 3600      # seconds a numbered action stays in ``recent``
EXCUSE_WINDOW = 10 * 60        # seconds the owner has to excuse a fault (protocol 0.2)
EXCUSABLE = frozenset({"refusal", "undo"})   # faults a person caused: never a check, a spot check or a flag
SCHEMA = """
CREATE TABLE IF NOT EXISTS types (agent TEXT NOT NULL, key TEXT NOT NULL, state TEXT NOT NULL,
                                  PRIMARY KEY (agent, key));
CREATE TABLE IF NOT EXISTS pending (id TEXT PRIMARY KEY, session TEXT NOT NULL, call TEXT NOT NULL,
                                    agent TEXT NOT NULL, type TEXT NOT NULL, stakes TEXT NOT NULL,
                                    reversible INTEGER NOT NULL, decision TEXT NOT NULL, phase TEXT NOT NULL,
                                    rule_key TEXT NOT NULL, snap_id TEXT, at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS pending_at ON pending (at);
CREATE INDEX IF NOT EXISTS pending_call ON pending (session, call);
CREATE TABLE IF NOT EXISTS sessions (session TEXT PRIMARY KEY, tainted INTEGER NOT NULL DEFAULT 0, at REAL);
CREATE TABLE IF NOT EXISTS undo (id INTEGER PRIMARY KEY AUTOINCREMENT, agent TEXT NOT NULL, type TEXT NOT NULL,
                                 snap_id TEXT, at REAL NOT NULL, undone INTEGER NOT NULL DEFAULT 0,
                                 fault INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS stats (agent TEXT NOT NULL, day TEXT NOT NULL, actions INTEGER NOT NULL DEFAULT 0,
                                  checked INTEGER NOT NULL DEFAULT 0, alone INTEGER NOT NULL DEFAULT 0,
                                  faults INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (agent, day));
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS ledger (seq INTEGER PRIMARY KEY AUTOINCREMENT, at REAL, event TEXT, prev TEXT, hash TEXT);
"""
# Added to a schema 3 database without changing its version (``Store._ensure_recent``). Its shape is fixed: a future
# column comes through a guarded ``ALTER TABLE ADD COLUMN``. No argument, path or summary is ever stored in it.
RECENT_SCHEMA = """
CREATE TABLE IF NOT EXISTS recent (n INTEGER PRIMARY KEY AUTOINCREMENT, session TEXT, agent TEXT, type TEXT, at REAL,
                                   flagged INTEGER DEFAULT 0, undo_id INTEGER, call TEXT);
CREATE INDEX IF NOT EXISTS recent_session ON recent (session);
CREATE INDEX IF NOT EXISTS recent_at ON recent (at);
"""
RECENT_COLS = ("n", "session", "agent", "type", "at", "flagged", "undo_id", "call")
# Files the agent wrote in the last 24 hours, as sha256 of their real path (no path is stored): running one asks once.
WRITTEN_SCHEMA = "CREATE TABLE IF NOT EXISTS written (h TEXT PRIMARY KEY, at REAL)"
WRITTEN_WINDOW = 24 * 3600
DOUBT = "doubt:"           # meta key prefix: a kind whose next action asks first (a verifier's doubt, #6)
INPUT_KINDS = frozenset({"settings", "outcome", "agent", "revoke", "copy", "excuse"})
DISTRUST = "distrust:"     # meta key prefix: a type that lost the trusted start in this profile
DERIVED_KINDS = frozenset({"tier", "trial", "confirmed", "revoked", "neutral_expired"})   # display only
STAT_FIELDS = ("actions", "checked", "alone", "faults")
PENDING_COLS = ("id", "session", "call", "agent", "type", "stakes", "reversible", "decision", "phase", "rule_key",
                "snap_id", "at")

# Ledger input events: the only ones a replay reads, in ledger order. Derived events (tier, trial, confirmed, revoked)
# are display only.
#   {"event": "settings", "risks": {...}, "spot": float, "strict": bool, "rule": str}
#       The settings in force from here on: logged before the first outcome, then whenever they change. Replay:
#       rule.reevaluate(state, params.required_n(risks, state.stakes)) on every type of every agent known so far.
#   {"event": "outcome", "agent", "type", "stakes", "reversible", "result": success|fault|neutral, "source", "session"}
#       Replay: the agent's type (a new one is TypeState(type, stakes, reversible)); when its stakes differ from the
#       event's, rule.rebase first (evidence counts only at the stakes it was earned at); it takes the event's stakes
#       and reversibility, then on_success / on_fault(n from the settings, session, source) or on_neutral(source), then
#       rule.count_action when (result, source) is in COUNTED, unless that fault failed the trial (the rule returned
#       a "trial" event with the reason "failed"). Sources (OUTCOME_SOURCES):
#         success: approval (an approved ask ran cleanly), spot (an approved spot check ran cleanly), notify (a T2
#                  action ran cleanly);
#         fault:   refusal (an ask refused), spot (a spot check refused, or approved but failing its automatic
#                  check), check (an action that ran failed its automatic check, whoever let it run: a person, an
#                  earned tier, or nobody), undo, flag (after the fact);
#         neutral: ambiguous (several live rows of one tool call id and type outside any session: none is
#                  settled as a success), error (an action a person or an earned tier let run, whose tool failed), alone (a T3 action
#                  ran, unverified), blocked (stopped by another guard after our decision, never ran), timeout (no
#                  answer from a person: timeout, cancellation, smart approval), nobody (nobody answered: cron,
#                  yolo, approvals off, another plugin's approval; the action did not fail its automatic check, or
#                  did not run, or its tool failed), expired (no outcome within 24 h), background (a terminal call
#                  Hermes ran in the background: its result is the launch, not the command's outcome).
#   {"event": "agent", "old": str, "new": str, "mode": carry|strict, "vetoed": [type, ...]}
#       Replay: every type of `old` that `new` has no state for yet becomes rule.carry_over(old state,
#       n_new=params.required_n(risks, stakes), veto=type in vetoed, strict=mode == "strict").
#   {"event": "revoke", "agent", "type"}
#       Replay: rule.revoke on that type.
#   {"event": "excuse", "seq": int}  (protocol 0.2)
#       The owner says the fault outcome at ledger row `seq` was not the agent's mistake (a refusal for another
#       reason, an undo of a correct change), within EXCUSE_WINDOW of it. Only sources in EXCUSABLE (refusal, undo):
#       never the automatic check, a spot check or a flag, which are the detection the guarantee rests on. Replay: that earlier outcome is replayed
#       as ("neutral", "excused"), as if it had been neutral from the start; the excuse row itself changes nothing.
OUTCOME_SOURCES = {
    "success": frozenset({"approval", "spot", "notify"}),
    "fault": frozenset({"refusal", "spot", "check", "undo", "flag"}),
    "neutral": frozenset({"error", "alone", "blocked", "timeout", "nobody", "expired", "ambiguous", "background",
                          "excused"}),
}
# Outcomes of an action that ran: the wait after a failed trial counts them (rule.count_action). A failed automatic
# check counts even when nobody answered: the action ran and the check judged it. A refused spot check never ran; an
# approved one failing its check shares its source ("spot") and is not counted either, which changes nothing in
# practice: a spot check is only drawn while no trial and no wait are open.
COUNTED = frozenset({("success", "approval"), ("success", "spot"), ("success", "notify"), ("fault", "check"),
                     ("neutral", "error"), ("neutral", "alone")})


def _canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def chain_hash(prev: str, seq: int, at: float, event: dict) -> str:
    return hashlib.sha256(f"{prev}|{seq}|{at!r}|{_canon(event)}".encode("utf-8")).hexdigest()


class Store:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        new = not os.path.exists(path)
        self.db = sqlite3.connect(path, timeout=BUSY_TIMEOUT, isolation_level=None, check_same_thread=False)
        self.db.execute(f"PRAGMA busy_timeout = {int(BUSY_TIMEOUT * 1000)}")
        try:
            self.db.execute("PRAGMA journal_mode = WAL")
        except sqlite3.DatabaseError:
            pass
        self._ensure_schema()
        self._ensure_recent()
        if new and os.name == "posix":
            os.chmod(path, 0o600)

    @classmethod
    def open_readonly(cls, path: str) -> "Store":
        """Read-only connection (dashboard). Never creates a file or a table; raises if the file is missing."""
        if not os.path.exists(path):
            raise FileNotFoundError(path)
        self = cls.__new__(cls)
        self.path = path
        uri = "file:" + urllib.parse.quote(os.path.abspath(path)) + "?mode=ro"
        self.db = sqlite3.connect(uri, uri=True, timeout=BUSY_TIMEOUT, isolation_level=None, check_same_thread=False)
        self.db.execute(f"PRAGMA busy_timeout = {int(BUSY_TIMEOUT * 1000)}")
        try:
            version = self.get_meta("schema")
        except sqlite3.DatabaseError:
            version = None
        if version != SCHEMA_VERSION:
            self.db.close()
            raise RuntimeError(f"tenure store: {path} is not a schema {SCHEMA_VERSION} database "
                               f"(found {version!r}); open it once with the plugin first")
        self.has_recent = self._recent_exists()
        self.has_call = self.has_recent and self._call_exists()
        return self

    def _ensure_schema(self) -> None:
        """Create the current tables. A file from an older schema (v1, v2: never released) is copied to
        ``<file>.bak-<version>`` (``unknown`` without a version), then its tables are dropped and recreated; a newer
        schema raises instead of being downgraded."""
        def stored() -> str | None:
            try:
                row = self.db.execute("SELECT value FROM meta WHERE key = 'schema'").fetchone()
            except sqlite3.OperationalError:
                return None
            return None if row is None else row[0]

        def current() -> bool:
            v = stored()
            if v is not None and v.isdigit() and int(v) > int(SCHEMA_VERSION):
                raise RuntimeError(f"tenure store: database schema {v} is newer than this plugin's "
                                   f"{SCHEMA_VERSION}; refusing to downgrade it")
            return v == SCHEMA_VERSION
        if current():
            return
        self._backup(stored())
        self.db.execute("BEGIN IMMEDIATE")
        try:
            if not current():
                for t in TABLES:
                    self.db.execute(f"DROP TABLE IF EXISTS {t}")
                for stmt in SCHEMA.split(";"):
                    if stmt.strip():
                        self.db.execute(stmt)
                self.db.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('schema', ?)", (SCHEMA_VERSION,))
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        self.db.execute("COMMIT")

    def _recent_exists(self) -> bool:
        return self.db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'recent'").fetchone() \
            is not None

    def _call_exists(self) -> bool:
        return any(r[1] == "call" for r in self.db.execute("PRAGMA table_info(recent)").fetchall())

    def _cols(self) -> str:
        """The columns of ``recent`` to select: a table made before the column ``call`` reads it as NULL."""
        return ", ".join(c if c != "call" or self.has_call else "NULL" for c in RECENT_COLS)

    def _ensure_recent(self) -> None:
        """Add the table ``recent`` to a schema 3 database that lacks it, without touching the version, the ledger
        or any other table. Reads first: a database that has it takes no write lock. When another process holds the
        write lock past the timeout, the store opens without the table (every ``recent`` method is then empty or does
        nothing until another process or this store's next write adds it): an action never fails because of it."""
        self.has_recent = self._recent_exists()
        self.has_call = self.has_recent and self._call_exists()
        if self.has_recent:
            return
        try:
            self.db.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError as e:            # database is locked: the first write adds it instead
            log.warning("tenure: could not add the table of numbered actions yet (%s); retried at the next write", e)
            return
        try:
            for stmt in RECENT_SCHEMA.split(";"):
                if stmt.strip():
                    self.db.execute(stmt)
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        self.db.execute("COMMIT")
        self.has_recent = self.has_call = True

    def _backup(self, version: str | None) -> None:
        """Copy a database about to be dropped, when it holds any table, before anything is lost."""
        if not self.db.execute("SELECT COUNT(*) FROM sqlite_master WHERE type = 'table'").fetchone()[0]:
            return
        target = sqlite3.connect(f"{self.path}.bak-{version or 'unknown'}")
        try:
            self.db.backup(target)
        finally:
            target.close()
        if os.name == "posix":
            os.chmod(f"{self.path}.bak-{version or 'unknown'}", 0o600)

    def _write(self) -> None:
        if not self.db.in_transaction:
            raise RuntimeError("tenure store: write outside a transaction")

    @contextmanager
    def transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield self
        except BaseException:
            self.db.execute("ROLLBACK")
            self.has_recent = self._recent_exists()        # a table added in this transaction is gone again
            self.has_call = self.has_recent and self._call_exists()
            raise
        else:
            self.db.execute("COMMIT")

    # ------------------------------------------------------------------------------------------------- states
    def recorded(self, agent: str, key: str) -> TypeState | None:
        """The state exactly as last recorded, with the stakes and reversibility of its last outcome; None if none."""
        row = self.db.execute("SELECT state FROM types WHERE agent = ? AND key = ?", (agent, key)).fetchone()
        return None if row is None else TypeState.from_dict(json.loads(row[0]))

    def get_state(self, agent: str, key: str, stakes: str, reversible: bool = False) -> TypeState:
        """The state with today's stakes and reversibility (the owner may have reclassified the type since)."""
        s = self.recorded(agent, key)
        if s is None:                       # a type faulted under another model of this profile is not trusted
            return TypeState(key=key, stakes=stakes, reversible=bool(reversible),
                             distrusted=bool(self.get_meta(DISTRUST + key)))
        s.stakes = stakes
        s.reversible = bool(reversible)
        return s

    def trust_again(self, key: str) -> None:
        """An excuse took back the only fault or revoke of a type: it is under the trusted start again."""
        if self.get_meta(DISTRUST + key):
            self._write()
            self.db.execute("DELETE FROM meta WHERE key = ?", (DISTRUST + key,))

    def distrust(self, key: str) -> None:
        """A fault or a revoke on a type ends the trusted start for that type in this profile, for every model: the
        ones that have a record now, and the ones that come later (``get_state``)."""
        if self.get_meta(DISTRUST + key):
            return                          # already ended: every state of the type carries it
        self.set_meta(DISTRUST + key, "1")
        for agent, s in self.states():
            if s.key == key and not s.distrusted:
                s.distrusted = True
                self.put_state(agent, s)

    def put_state(self, agent: str, s: TypeState) -> None:
        self._write()
        self.db.execute("INSERT OR REPLACE INTO types (agent, key, state) VALUES (?, ?, ?)",
                        (agent, s.key, _canon(s.to_dict())))

    def states(self, agent: str | None = None) -> list[tuple[str, TypeState]]:
        q = "SELECT agent, state FROM types" + (" WHERE agent = ?" if agent else "") + " ORDER BY agent, key"
        rows = self.db.execute(q, (agent,) if agent else ()).fetchall()
        return [(a, TypeState.from_dict(json.loads(s))) for a, s in rows]

    def agents(self) -> list[str]:
        return [r[0] for r in self.db.execute("SELECT DISTINCT agent FROM types ORDER BY agent")]

    # ------------------------------------------------------------------------------------------------ pending
    @staticmethod
    def _pending(row) -> dict:
        d = dict(zip(PENDING_COLS, row))
        d["reversible"] = bool(d["reversible"])
        return d

    def add_pending(self, id: str, *, call: str, agent: str, type: str, stakes: str, reversible: bool,
                    decision: str, phase: str, rule_key: str, session: str, snap_id: str | None = None,
                    at: float | None = None) -> None:
        """A new pending decision under its unique ``id``; ``call`` is the provider's tool call id. A live row is
        never replaced: a second row with the same id raises sqlite3.IntegrityError."""
        self._write()
        self.db.execute("INSERT INTO pending (%s) VALUES (%s)"
                        % (", ".join(PENDING_COLS), ", ".join("?" * len(PENDING_COLS))),
                        (id, session, call, agent, type, stakes, int(bool(reversible)), decision, phase, rule_key,
                         snap_id, time.time() if at is None else at))

    def get_pending(self, id: str) -> dict | None:
        row = self.db.execute("SELECT %s FROM pending WHERE id = ?" % ", ".join(PENDING_COLS), (id,)).fetchone()
        return None if row is None else self._pending(row)

    def find_pending(self, session: str, call: str) -> dict | None:
        """The newest pending row of a tool call id in a session."""
        rows = self.pending_rows(session, call)
        return rows[0] if rows else None

    def pending_rows(self, session: str, call: str) -> list[dict]:
        """Every live row of a tool call id in a session, newest first."""
        rows = self.db.execute("SELECT %s FROM pending WHERE session = ? AND call = ? ORDER BY at DESC, rowid DESC"
                               % ", ".join(PENDING_COLS), (session, call)).fetchall()
        return [self._pending(r) for r in rows]

    def set_phase(self, id: str, phase: str) -> None:
        self._write()
        self.db.execute("UPDATE pending SET phase = ? WHERE id = ?", (phase, id))

    def pop_pending(self, id: str) -> dict | None:
        self._write()
        p = self.get_pending(id)
        if p is not None:
            self.db.execute("DELETE FROM pending WHERE id = ?", (id,))
        return p

    def expire_pending(self, older_than: float = 24 * 3600) -> list[dict]:
        """Delete and return the rows older than ``older_than`` seconds, so the caller logs them as neutral."""
        self._write()
        cutoff = time.time() - older_than
        rows = self.db.execute("SELECT %s FROM pending WHERE at < ? ORDER BY at" % ", ".join(PENDING_COLS),
                               (cutoff,)).fetchall()
        if rows:
            self.db.execute("DELETE FROM pending WHERE at < ?", (cutoff,))
        return [self._pending(r) for r in rows]

    # ----------------------------------------------------------------------------------------------- sessions
    def taint(self, session: str) -> None:
        self._write()
        self.db.execute("INSERT INTO sessions (session, tainted, at) VALUES (?, 1, ?) "
                        "ON CONFLICT(session) DO UPDATE SET tainted = 1", (session, time.time()))

    def is_tainted(self, session: str) -> bool:
        row = self.db.execute("SELECT tainted FROM sessions WHERE session = ?", (session,)).fetchone()
        return bool(row and row[0])

    # --------------------------------------------------------------------------------------------------- undo
    def add_undo(self, agent: str, type: str, snap_id: str | None, at: float | None = None, *,
                 fault: bool = False) -> int:
        """An action that can be undone. ``fault``: its outcome already counted as a fault (a failed automatic check),
        so undoing it must not count a second one."""
        self._write()
        cur = self.db.execute("INSERT INTO undo (agent, type, snap_id, at, fault) VALUES (?, ?, ?, ?, ?)",
                              (agent, type, snap_id, time.time() if at is None else at, int(bool(fault))))
        return int(cur.lastrowid)

    def get_undo(self, id: int) -> dict | None:
        r = self.db.execute("SELECT id, agent, type, snap_id, at, undone, fault FROM undo WHERE id = ?",
                            (id,)).fetchone()
        return None if r is None else dict(id=r[0], agent=r[1], type=r[2], snap_id=r[3], at=r[4], undone=bool(r[5]),
                                           fault=bool(r[6]))

    def mark_undone(self, id: int) -> None:
        self._write()
        self.db.execute("UPDATE undo SET undone = 1 WHERE id = ?", (id,))

    def mark_undo_fault(self, id: int) -> None:
        """The action of this undo entry already counted as a fault (a flag): undoing it counts no second one."""
        self._write()
        self.db.execute("UPDATE undo SET fault = 1 WHERE id = ?", (id,))

    # ------------------------------------------------------------------------------------------------- recent
    # Numbered actions of the last 24 hours: session (anonymised), agent, type, time, already a fault, undo id.
    # Opened without the table (see _ensure_recent), a read looks again whether another process added it, else is
    # empty; a write adds it inside its own transaction (DDL rolls back with it).
    def _recent_ready(self) -> bool:
        if not self.has_recent:
            self.has_recent = self._recent_exists()
            self.has_call = self.has_recent and self._call_exists()
        return self.has_recent

    def _recent_write(self) -> None:
        self._write()
        if not self.has_recent:
            for stmt in RECENT_SCHEMA.split(";"):
                if stmt.strip():
                    self.db.execute(stmt)
            self.has_recent = self.has_call = True
        if not self.has_call:                             # a table made by 1.1: the column of the call is added
            self.has_call = self._call_exists()
            if not self.has_call:
                self.db.execute("ALTER TABLE recent ADD COLUMN call TEXT")
                self.has_call = True

    @staticmethod
    def _recent(row) -> dict:
        d = dict(zip(RECENT_COLS, row))
        d["flagged"] = bool(d["flagged"])
        return d

    def add_recent(self, session: str, agent: str, type_key: str, at: float, *, flagged: bool,
                   undo_id: int | None, call: str = "") -> int:
        """Number one settled action and purge the rows older than 24 hours, in the same write. Numbers are never
        reused (AUTOINCREMENT), even after every row is purged. ``call`` is the call id as stored (hashed, like a
        session): with the session it lets a verifier name the action (#6)."""
        self._recent_write()
        self.db.execute("DELETE FROM recent WHERE at < ?", (at - RECENT_WINDOW,))
        cur = self.db.execute("INSERT INTO recent (session, agent, type, at, flagged, undo_id, call) "
                              "VALUES (?, ?, ?, ?, ?, ?, ?)",
                              (session, agent, type_key, at, int(bool(flagged)), undo_id, call or None))
        return int(cur.lastrowid)

    def recent_by_call(self, session: str, call: str) -> list[dict]:
        """The numbered actions of the last 24 hours with this session and call id (both as stored). A call id is
        reused across sessions, so both are needed; more than one row means the pair is ambiguous."""
        if not session or not call or not self._recent_ready():
            return []
        if not self.has_call:
            self.has_call = self._call_exists()              # another process may have added it since
            if not self.has_call:
                return []
        rows = self.db.execute("SELECT %s FROM recent WHERE session = ? AND call = ? AND at >= ? ORDER BY n"
                               % self._cols(), (session, call, time.time() - RECENT_WINDOW)).fetchall()
        return [self._recent(r) for r in rows]

    def recent(self, n: int) -> dict | None:
        """Action number ``n``, when it is less than 24 hours old (a number beyond SQLite's integers is none)."""
        if not 0 < n < 2 ** 63 or not self._recent_ready():
            return None
        row = self.db.execute("SELECT %s FROM recent WHERE n = ? AND at >= ?" % self._cols(),
                              (n, time.time() - RECENT_WINDOW)).fetchone()
        return None if row is None else self._recent(row)

    def recent_rows(self, session: str | None, limit: int = 20) -> list[dict]:
        """The newest numbered actions of the last 24 hours, of one session (every session for None)."""
        if not self._recent_ready():
            return []
        q = "SELECT %s FROM recent WHERE at >= ?" % self._cols()
        args: list = [time.time() - RECENT_WINDOW]
        if session is not None:
            q += " AND session = ?"
            args.append(session)
        rows = self.db.execute(q + " ORDER BY n DESC LIMIT ?", (*args, int(limit))).fetchall()
        return [self._recent(r) for r in rows]

    def count_recent(self, exclude_session: str) -> int:
        """Numbered actions of the last 24 hours outside one session."""
        if not self._recent_ready():
            return 0
        return self.db.execute("SELECT COUNT(*) FROM recent WHERE at >= ? AND session IS NOT ?",
                               (time.time() - RECENT_WINDOW, exclude_session)).fetchone()[0]

    def mark_flagged(self, n: int) -> None:
        self._recent_write()
        self.db.execute("UPDATE recent SET flagged = 1 WHERE n = ?", (n,))

    def flag_by_undo(self, undo_id: int) -> None:
        """An undone action counts as signalled: it cannot be flagged afterwards."""
        self._recent_write()
        self.db.execute("UPDATE recent SET flagged = 1 WHERE undo_id = ?", (undo_id,))

    def clear_recent(self) -> None:
        self._recent_write()
        self.db.execute("DELETE FROM recent")

    # --------------------------------------------------------------------------------------------------- stats
    def bump(self, agent: str, field: str, n: int = 1, at: float | None = None) -> None:
        self._write()
        if field not in STAT_FIELDS:
            raise ValueError(f"unknown stat {field!r}")
        day = time.strftime("%Y-%m-%d", time.gmtime(time.time() if at is None else at))
        self.db.execute(f"INSERT INTO stats (agent, day, {field}) VALUES (?, ?, ?) "
                        f"ON CONFLICT(agent, day) DO UPDATE SET {field} = {field} + excluded.{field}",
                        (agent, day, n))

    def totals(self, agent: str | None = None, since: float = 0) -> dict:
        """Sums over days from the UTC day of ``since`` (a timestamp) on."""
        day = time.strftime("%Y-%m-%d", time.gmtime(since))
        cols = ", ".join(f"COALESCE(SUM({f}), 0)" for f in STAT_FIELDS)
        q = f"SELECT {cols} FROM stats WHERE day >= ?" + (" AND agent = ?" if agent else "")
        row = self.db.execute(q, (day, agent) if agent else (day,)).fetchone()
        return dict(zip(STAT_FIELDS, row))

    # --------------------------------------------------------------------------------------------------- meta
    # ---------------------------------------------------------------------- deferred credit of T2 (audit 19/11)
    _CREDITS = ("CREATE TABLE IF NOT EXISTS credits (undo_id INTEGER PRIMARY KEY, session TEXT, stakes TEXT, "
                "reversible INTEGER, seq INTEGER)")

    def add_credit(self, undo_id: int, session: str, stakes: str, reversible: bool) -> None:
        """An earned act-then-tell action whose success is credited only once its undo window closed unused. ``seq``:
        the ledger's last row when it ran, so what came after it is read by primary key."""
        self._write()
        self.db.execute(self._CREDITS)
        last = self.db.execute("SELECT MAX(seq) FROM ledger").fetchone()[0] or 0
        self.db.execute("INSERT OR REPLACE INTO credits (undo_id, session, stakes, reversible, seq) "
                        "VALUES (?, ?, ?, ?, ?)", (undo_id, session, stakes, int(bool(reversible)), last))

    def due_credits(self, before: float, limit: int = 50) -> list[dict]:
        """The deferred credits whose action is older than ``before``, oldest first, with their undo row."""
        if self.db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'credits'").fetchone() is None:
            return []
        rows = self.db.execute("SELECT c.undo_id, c.session, c.stakes, c.reversible, u.agent, u.type, u.at, u.undone, "
                               "u.fault, c.seq FROM credits c LEFT JOIN undo u ON u.id = c.undo_id "
                               "WHERE u.at IS NULL OR u.at < ? ORDER BY c.undo_id LIMIT ?", (before, limit)).fetchall()
        keys = ("undo_id", "session", "stakes", "reversible", "agent", "type", "at", "undone", "fault", "seq")
        return [dict(zip(keys, r)) for r in rows]

    def drop_credit(self, undo_id: int) -> None:
        self._write()
        self.db.execute(self._CREDITS)
        self.db.execute("DELETE FROM credits WHERE undo_id = ?", (undo_id,))

    def fault_since(self, agent: str, type_key: str, seq: int) -> bool:
        """A fault outcome (not excused since) or a revoke on this agent's type, after ledger row ``seq``."""
        faults, excused = set(), set()
        for s, event in self.db.execute("SELECT seq, event FROM ledger WHERE seq > ?", (seq or 0,)):
            e = json.loads(event)
            kind = e.get("event")
            if kind == "excuse":
                excused.add(e.get("seq"))
            elif (e.get("agent"), e.get("type")) == (agent, type_key) and (
                    kind == "revoke" or kind == "outcome" and e.get("result") == "fault"):
                faults.add(s)
        return bool(faults - excused)

    # ----------------------------------------------------------------------- root sessions (audit 19/11)
    def set_root(self, child: str, parent: str) -> None:
        """A subagent's session counts as its root session for the two-sessions condition."""
        root = self.root_of(parent)
        if root and root != child:
            Store.roots[child] = root
            if len(Store.roots) > 10_000:
                Store.roots.pop(next(iter(Store.roots)))
            self.set_meta("root:" + child, root)

    roots: dict = {}                     # child -> root, in memory too: a busy database never splits a conversation

    def root_of(self, session: str) -> str:
        if not session:
            return session
        return Store.roots.get(session) or self.get_meta("root:" + session) or session

    # ------------------------------------------------------------------------------- written then run (audit 19/11)
    def _path_hash(self, path: str) -> str:
        """HMAC-SHA256 of the real path with a random key of this database: a path cannot be guessed back from it."""
        import hmac
        import secrets
        key = self.get_meta("written_key")
        if key is None:
            key = secrets.token_hex(32)
            if self.db.in_transaction:
                self.set_meta("written_key", key)
        return hmac.new(bytes.fromhex(key), os.path.realpath(path).encode("utf-8", "surrogatepass"),
                        hashlib.sha256).hexdigest()

    def add_written(self, paths, at: float | None = None) -> None:
        """Remember that the agent wrote these files (hashed), and forget the ones older than 24 hours."""
        if not paths:
            return
        self._write()
        self.db.execute(WRITTEN_SCHEMA)
        now = time.time() if at is None else at
        self.db.execute("DELETE FROM written WHERE at < ?", (now - WRITTEN_WINDOW,))
        self.db.executemany("INSERT OR REPLACE INTO written (h, at) VALUES (?, ?)",
                            [(self._path_hash(p), now) for p in paths])

    def written_recently(self, paths) -> list[str]:
        """The paths among these that the agent wrote in the last 24 hours."""
        if not paths or self.get_meta("written_key") is None or self.db.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'written'").fetchone() is None:
            return []
        since = time.time() - WRITTEN_WINDOW
        return [p for p in paths if self.db.execute("SELECT 1 FROM written WHERE h = ? AND at >= ?",
                                                    (self._path_hash(p), since)).fetchone()]

    def forget_written(self, paths) -> None:
        """The owner approved running them: they do not ask again until the agent writes them again."""
        if not paths:
            return
        self._write()
        self.db.execute(WRITTEN_SCHEMA)
        self.db.executemany("DELETE FROM written WHERE h = ?", [(self._path_hash(p),) for p in paths])

    # -------------------------------------------------------------------------------------------- doubts (#6)
    @staticmethod
    def _doubt_key(agent: str, type_key: str) -> str:
        return DOUBT + json.dumps([agent, type_key], ensure_ascii=False)

    def add_doubt(self, agent: str, type_key: str) -> None:
        """A verifier doubts an action of this kind: its next action asks first. Not a ledger event: it changes no
        tier, no score and no passport, only one decision."""
        self.set_meta(self._doubt_key(agent, type_key), "1")

    def doubted(self, agent: str, type_key: str) -> bool:
        return self.get_meta(self._doubt_key(agent, type_key)) == "1"

    def clear_doubt(self, agent: str, type_key: str) -> None:
        if self.doubted(agent, type_key):
            self._write()
            self.db.execute("DELETE FROM meta WHERE key = ?", (self._doubt_key(agent, type_key),))

    def get_meta(self, key: str, default: str | None = None) -> str | None:
        row = self.db.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return default if row is None else row[0]

    def set_meta(self, key: str, value: str) -> None:
        self._write()
        self.db.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value))

    # ------------------------------------------------------------------------------------------------- ledger
    def log(self, event: dict) -> int:
        self._write()
        kind = event.get("event")
        if kind not in INPUT_KINDS and kind not in DERIVED_KINDS:
            raise ValueError(f"tenure store: unknown ledger event kind {kind!r}")
        last = self.db.execute("SELECT seq, hash FROM ledger ORDER BY seq DESC LIMIT 1").fetchone()
        seq, prev = (last[0] + 1, last[1]) if last else (1, GENESIS)
        at = float(event.get("at") or time.time())
        self.db.execute("INSERT INTO ledger (seq, at, event, prev, hash) VALUES (?, ?, ?, ?, ?)",
                        (seq, at, _canon(event), prev, chain_hash(prev, seq, at, event)))
        return seq

    def ledger(self) -> list[dict]:
        rows = self.db.execute("SELECT seq, at, event, prev, hash FROM ledger ORDER BY seq").fetchall()
        return [dict(seq=r[0], at=r[1], event=json.loads(r[2]), prev=r[3], hash=r[4]) for r in rows]

    def export(self, path: str) -> int:
        rows = self.ledger()
        with open(path, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(_canon(r) + "\n")
        return len(rows)


def verify(rows: list[dict]) -> list[str]:
    """Problems found in a ledger (empty list = intact)."""
    problems, prev = [], GENESIS
    for i, r in enumerate(rows, 1):
        if r.get("seq") != i:
            problems.append(f"row {i}: sequence {r.get('seq')} out of order")
        if r.get("prev") != prev:
            problems.append(f"row {i}: does not follow the previous row")
        if r.get("hash") != chain_hash(r.get("prev", ""), r.get("seq", 0), r.get("at", 0.0), r.get("event", {})):
            problems.append(f"row {i}: content changed after it was written")
        prev = r.get("hash", "")
    return problems
