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
from contextlib import contextmanager

from .rule import TypeState

GENESIS = "0" * 64
SCHEMA = """
CREATE TABLE IF NOT EXISTS types (model TEXT NOT NULL, key TEXT NOT NULL, state TEXT NOT NULL,
                                  PRIMARY KEY (model, key));
CREATE TABLE IF NOT EXISTS pending (tool_call_id TEXT PRIMARY KEY, model TEXT, type TEXT, generation INTEGER,
                                    spot INTEGER, rule_key TEXT, at REAL, stakes TEXT);
CREATE INDEX IF NOT EXISTS pending_rule ON pending (rule_key);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS ledger (seq INTEGER PRIMARY KEY AUTOINCREMENT, at REAL, event TEXT, prev TEXT, hash TEXT);
"""


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
        self.db.executescript(SCHEMA)
        if new and os.name == "posix":
            os.chmod(path, 0o600)

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
    def get_state(self, model: str, key: str, stakes: str) -> TypeState:
        row = self.db.execute("SELECT state FROM types WHERE model = ? AND key = ?", (model, key)).fetchone()
        if row is None:
            return TypeState(key=key, stakes=stakes)
        s = TypeState.from_dict(json.loads(row[0]))
        s.stakes = stakes                     # the owner may have reclassified the type since
        return s

    def put_state(self, model: str, s: TypeState) -> None:
        self.db.execute("INSERT OR REPLACE INTO types (model, key, state) VALUES (?, ?, ?)",
                        (model, s.key, _canon(s.to_dict())))

    def states(self, model: str | None = None) -> list[tuple[str, TypeState]]:
        q = "SELECT model, state FROM types" + (" WHERE model = ?" if model else "") + " ORDER BY model, key"
        rows = self.db.execute(q, (model,) if model else ()).fetchall()
        return [(m, TypeState.from_dict(json.loads(s))) for m, s in rows]

    # ------------------------------------------------------------------------------------------------ pending
    def add_pending(self, tool_call_id: str, model: str, type_key: str, generation: int, *, spot: bool,
                    rule_key: str, at: float | None = None, stakes: str = "") -> None:
        self.db.execute("INSERT OR REPLACE INTO pending VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (tool_call_id, model, type_key, generation, int(spot), rule_key,
                         time.time() if at is None else at, stakes))

    def pop_pending(self, *, tool_call_id: str = "", rule_key: str = "") -> dict | None:
        row = None
        if tool_call_id:
            row = self.db.execute("SELECT * FROM pending WHERE tool_call_id = ?", (tool_call_id,)).fetchone()
        if row is None and rule_key:
            row = self.db.execute("SELECT * FROM pending WHERE rule_key = ? ORDER BY at DESC LIMIT 1",
                                  (rule_key,)).fetchone()
        if row is None:
            return None
        self.db.execute("DELETE FROM pending WHERE tool_call_id = ?", (row[0],))
        return dict(tool_call_id=row[0], model=row[1], type=row[2], generation=row[3], spot=bool(row[4]),
                    rule_key=row[5], at=row[6], stakes=row[7] or "")

    def expire_pending(self, older_than: float = 24 * 3600) -> None:
        self.db.execute("DELETE FROM pending WHERE at < ?", (time.time() - older_than,))

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
