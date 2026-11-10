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
import os
import sqlite3
import time
import urllib.parse
from contextlib import contextmanager

from .rule import TypeState

GENESIS = "0" * 64
SCHEMA_VERSION = "3"
BUSY_TIMEOUT = 5.0             # seconds a writer waits for another process's transaction, well under a hook's limit
TABLES = ("types", "pending", "sessions", "undo", "stats", "meta", "ledger")
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
INPUT_KINDS = frozenset({"settings", "outcome", "agent", "revoke"})
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
OUTCOME_SOURCES = {
    "success": frozenset({"approval", "spot", "notify"}),
    "fault": frozenset({"refusal", "spot", "check", "undo", "flag"}),
    "neutral": frozenset({"error", "alone", "blocked", "timeout", "nobody", "expired", "ambiguous", "background"}),
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
        if s is None:
            return TypeState(key=key, stakes=stakes, reversible=bool(reversible))
        s.stakes = stakes
        s.reversible = bool(reversible)
        return s

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
    def get_meta(self, key: str, default: str | None = None) -> str | None:
        row = self.db.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return default if row is None else row[0]

    def set_meta(self, key: str, value: str) -> None:
        self._write()
        self.db.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value))

    # ------------------------------------------------------------------------------------------------- ledger
    def log(self, event: dict) -> None:
        self._write()
        kind = event.get("event")
        if kind not in INPUT_KINDS and kind not in DERIVED_KINDS:
            raise ValueError(f"tenure store: unknown ledger event kind {kind!r}")
        last = self.db.execute("SELECT seq, hash FROM ledger ORDER BY seq DESC LIMIT 1").fetchone()
        seq, prev = (last[0] + 1, last[1]) if last else (1, GENESIS)
        at = float(event.get("at") or time.time())
        self.db.execute("INSERT INTO ledger (seq, at, event, prev, hash) VALUES (?, ?, ?, ?, ?)",
                        (seq, at, _canon(event), prev, chain_hash(prev, seq, at, event)))

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
