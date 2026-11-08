# Copyright 2026 Otsoa Dubief
# SPDX-License-Identifier: Apache-2.0
"""State and evidence, in one SQLite file per Hermes profile.

The CLI, the gateway and cron run in separate processes and may answer approvals at the same time: every
read-modify-write happens inside ``transaction()`` (BEGIN IMMEDIATE), so no update is lost. The ledger lives in the
same database, written in the same transaction as the state it explains, as a hash chain: each row carries the hash
of the previous one, so an exported evidence file can be checked line by line (``verify``). The ledger records
action types, stakes, outcomes and generations, never commands, paths or message contents.
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
SCHEMA_VERSION = "2"
TABLES = ("types", "pending", "sessions", "undo", "stats", "meta", "ledger")
SCHEMA = """
CREATE TABLE IF NOT EXISTS types (agent TEXT NOT NULL, key TEXT NOT NULL, state TEXT NOT NULL,
                                  PRIMARY KEY (agent, key));
CREATE TABLE IF NOT EXISTS pending (tool_call_id TEXT PRIMARY KEY, agent TEXT NOT NULL, type TEXT NOT NULL,
                                    stakes TEXT NOT NULL, reversible INTEGER NOT NULL, decision TEXT NOT NULL,
                                    phase TEXT NOT NULL, rule_key TEXT NOT NULL, session TEXT NOT NULL,
                                    snap_id TEXT, at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS pending_at ON pending (at);
CREATE TABLE IF NOT EXISTS sessions (session TEXT PRIMARY KEY, tainted INTEGER NOT NULL DEFAULT 0, at REAL);
CREATE TABLE IF NOT EXISTS undo (id INTEGER PRIMARY KEY AUTOINCREMENT, agent TEXT NOT NULL, type TEXT NOT NULL,
                                 snap_id TEXT, at REAL NOT NULL, undone INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS stats (agent TEXT NOT NULL, day TEXT NOT NULL, actions INTEGER NOT NULL DEFAULT 0,
                                  checked INTEGER NOT NULL DEFAULT 0, alone INTEGER NOT NULL DEFAULT 0,
                                  faults INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (agent, day));
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS ledger (seq INTEGER PRIMARY KEY AUTOINCREMENT, at REAL, event TEXT, prev TEXT, hash TEXT);
"""
STAT_FIELDS = ("actions", "checked", "alone", "faults")
PENDING_COLS = ("tool_call_id", "agent", "type", "stakes", "reversible", "decision", "phase", "rule_key",
                "session", "snap_id", "at")

# Ledger input events: the only ones a replay reads. Derived events (tier, trial, confirmed, revoked) are display only.
#   {"event": "settings", "risks": {...}, "spot": float, "strict": bool, "rule": str}
#   {"event": "outcome", "agent", "type", "stakes", "reversible", "result": success|fault|neutral,
#    "source": approval|refusal|check|notify|spot|undo|flag|timeout|nobody|expired, "session"}
#   {"event": "agent", "old": str, "new": str, "mode": carry|strict, "vetoed": [type, ...]}
#   {"event": "revoke", "agent", "type"}


def _canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def chain_hash(prev: str, seq: int, at: float, event: dict) -> str:
    return hashlib.sha256(f"{prev}|{seq}|{at!r}|{_canon(event)}".encode("utf-8")).hexdigest()


class Store:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        new = not os.path.exists(path)
        self.db = sqlite3.connect(path, timeout=30, isolation_level=None, check_same_thread=False)
        self.db.execute("PRAGMA busy_timeout = 30000")
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
        self.db = sqlite3.connect(uri, uri=True, timeout=30, isolation_level=None, check_same_thread=False)
        self.db.execute("PRAGMA busy_timeout = 30000")
        return self

    def _ensure_schema(self) -> None:
        """Create the v2 tables; a file from an older schema is dropped and recreated (there are no v1 users)."""
        def current() -> bool:
            try:
                row = self.db.execute("SELECT value FROM meta WHERE key = 'schema'").fetchone()
            except sqlite3.OperationalError:
                return False
            return row is not None and row[0] == SCHEMA_VERSION
        if current():
            return
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
    def get_state(self, agent: str, key: str, stakes: str, reversible: bool = False) -> TypeState:
        row = self.db.execute("SELECT state FROM types WHERE agent = ? AND key = ?", (agent, key)).fetchone()
        if row is None:
            return TypeState(key=key, stakes=stakes, reversible=bool(reversible))
        s = TypeState.from_dict(json.loads(row[0]))
        s.stakes = stakes                     # the owner may have reclassified the type since
        s.reversible = bool(reversible)
        return s

    def put_state(self, agent: str, s: TypeState) -> None:
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

    def add_pending(self, tool_call_id: str, *, agent: str, type: str, stakes: str, reversible: bool,
                    decision: str, phase: str, rule_key: str, session: str, snap_id: str | None = None,
                    at: float | None = None) -> None:
        self.db.execute("INSERT OR REPLACE INTO pending (%s) VALUES (%s)"
                        % (", ".join(PENDING_COLS), ", ".join("?" * len(PENDING_COLS))),
                        (tool_call_id, agent, type, stakes, int(bool(reversible)), decision, phase, rule_key,
                         session, snap_id, time.time() if at is None else at))

    def get_pending(self, tool_call_id: str) -> dict | None:
        row = self.db.execute("SELECT %s FROM pending WHERE tool_call_id = ?" % ", ".join(PENDING_COLS),
                              (tool_call_id,)).fetchone()
        return None if row is None else self._pending(row)

    def set_phase(self, tool_call_id: str, phase: str) -> None:
        self.db.execute("UPDATE pending SET phase = ? WHERE tool_call_id = ?", (phase, tool_call_id))

    def pop_pending(self, tool_call_id: str) -> dict | None:
        p = self.get_pending(tool_call_id)
        if p is not None:
            self.db.execute("DELETE FROM pending WHERE tool_call_id = ?", (tool_call_id,))
        return p

    def expire_pending(self, older_than: float = 24 * 3600) -> list[dict]:
        """Delete and return the rows older than ``older_than`` seconds, so the caller logs them as neutral."""
        cutoff = time.time() - older_than
        rows = self.db.execute("SELECT %s FROM pending WHERE at < ? ORDER BY at" % ", ".join(PENDING_COLS),
                               (cutoff,)).fetchall()
        if rows:
            self.db.execute("DELETE FROM pending WHERE at < ?", (cutoff,))
        return [self._pending(r) for r in rows]

    # ----------------------------------------------------------------------------------------------- sessions
    def taint(self, session: str) -> None:
        self.db.execute("INSERT INTO sessions (session, tainted, at) VALUES (?, 1, ?) "
                        "ON CONFLICT(session) DO UPDATE SET tainted = 1", (session, time.time()))

    def is_tainted(self, session: str) -> bool:
        row = self.db.execute("SELECT tainted FROM sessions WHERE session = ?", (session,)).fetchone()
        return bool(row and row[0])

    # --------------------------------------------------------------------------------------------------- undo
    def add_undo(self, agent: str, type: str, snap_id: str | None, at: float | None = None) -> int:
        cur = self.db.execute("INSERT INTO undo (agent, type, snap_id, at) VALUES (?, ?, ?, ?)",
                              (agent, type, snap_id, time.time() if at is None else at))
        return int(cur.lastrowid)

    def get_undo(self, id: int) -> dict | None:
        r = self.db.execute("SELECT id, agent, type, snap_id, at, undone FROM undo WHERE id = ?", (id,)).fetchone()
        return None if r is None else dict(id=r[0], agent=r[1], type=r[2], snap_id=r[3], at=r[4], undone=bool(r[5]))

    def mark_undone(self, id: int) -> None:
        self.db.execute("UPDATE undo SET undone = 1 WHERE id = ?", (id,))

    # --------------------------------------------------------------------------------------------------- stats
    def bump(self, agent: str, field: str, n: int = 1, at: float | None = None) -> None:
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
        self.db.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value))

    # ------------------------------------------------------------------------------------------------- ledger
    def log(self, event: dict) -> None:
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
