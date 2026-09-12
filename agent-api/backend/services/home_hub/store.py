from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from backend.config import resolve_api_path


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class HubStore:
    def __init__(self, path: str | Path = "data/home_hub/home_hub.db") -> None:
        self.path = resolve_api_path(path, "data/home_hub/home_hub.db")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS inventory (
                    kind TEXT NOT NULL, id TEXT NOT NULL, payload TEXT NOT NULL,
                    observed_at TEXT NOT NULL, PRIMARY KEY(kind, id));
                CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL,
                    subject TEXT NOT NULL, payload TEXT NOT NULL, observed_at TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS events_subject ON events(subject, id);
                CREATE TABLE IF NOT EXISTS conversation (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, principal TEXT NOT NULL,
                    role TEXT NOT NULL, text TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS conversation_principal ON conversation(principal, id);
                CREATE TABLE IF NOT EXISTS actions (
                    id TEXT PRIMARY KEY, principal TEXT NOT NULL, status TEXT NOT NULL,
                    payload TEXT NOT NULL, result TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL, expires_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS rules (
                    id TEXT PRIMARY KEY, principal TEXT NOT NULL, payload TEXT NOT NULL,
                    created_at TEXT NOT NULL, mode TEXT NOT NULL DEFAULT 'observe',
                    last_run REAL NOT NULL DEFAULT 0, hold_until REAL NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS deliveries (
                    id TEXT PRIMARY KEY, channel TEXT NOT NULL, target TEXT NOT NULL,
                    payload TEXT NOT NULL, status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
                    next_attempt REAL NOT NULL DEFAULT 0, error TEXT, created_at TEXT NOT NULL);
            """)
            columns = {row[1] for row in db.execute("PRAGMA table_info(rules)")}
            for column, definition in {"mode": "TEXT NOT NULL DEFAULT 'observe'", "last_run": "REAL NOT NULL DEFAULT 0", "hold_until": "REAL NOT NULL DEFAULT 0"}.items():
                if column not in columns:
                    db.execute(f"ALTER TABLE rules ADD COLUMN {column} {definition}")

    def recover(self) -> None:
        with self.connect() as db:
            # A crash after dispatch has an unknown outcome; never replay physical commands.
            db.execute("UPDATE actions SET status = 'unknown' WHERE status = 'executing'")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def meta(self, key: str, value: Any = None) -> Any:
        with self.connect() as db:
            if value is not None:
                db.execute("INSERT OR REPLACE INTO metadata VALUES (?, ?)", (key, json.dumps(value)))
                return value
            row = db.execute("SELECT payload FROM metadata WHERE key = ?", (key,)).fetchone()
        return json.loads(row[0]) if row else {}

    def replace(self, kind: str, items: list[dict], key: str) -> None:
        timestamp = now()
        with self.connect() as db:
            db.execute("DELETE FROM inventory WHERE kind = ?", (kind,))
            db.executemany("INSERT OR REPLACE INTO inventory VALUES (?, ?, ?, ?)",
                           [(kind, str(item[key]), json.dumps(item), timestamp) for item in items if item.get(key)])

    def items(self, kind: str) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("SELECT payload FROM inventory WHERE kind = ? ORDER BY id", (kind,)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def item(self, kind: str, item_id: str) -> dict | None:
        with self.connect() as db:
            row = db.execute("SELECT payload FROM inventory WHERE kind = ? AND id = ?", (kind, item_id)).fetchone()
        return json.loads(row[0]) if row else None

    def counts(self) -> dict:
        with self.connect() as db:
            rows = db.execute("SELECT kind, count(*) AS count FROM inventory GROUP BY kind").fetchall()
        return {row["kind"]: row["count"] for row in rows}

    def state_event(self, entity_id: str, state: dict | None, event: dict) -> None:
        with self.connect() as db:
            if state is None:
                db.execute("DELETE FROM inventory WHERE kind = 'states' AND id = ?", (entity_id,))
            else:
                db.execute("INSERT OR REPLACE INTO inventory VALUES ('states', ?, ?, ?)",
                           (entity_id, json.dumps(state), now()))
            db.execute("INSERT INTO events(kind, subject, payload, observed_at) VALUES ('state_changed', ?, ?, ?)",
                       (entity_id, json.dumps(event), now()))

    def event(self, kind: str, subject: str, payload: dict) -> None:
        with self.connect() as db:
            db.execute("INSERT INTO events(kind, subject, payload, observed_at) VALUES (?, ?, ?, ?)",
                       (kind, subject, json.dumps(payload), now()))

    def history(self, subject: str = "", limit: int = 50, before: int | None = None) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM events WHERE (? = '' OR subject = ?) AND (? IS NULL OR id < ?) ORDER BY id DESC LIMIT ?",
                              (subject, subject, before, before, max(1, min(limit, 200)))).fetchall()
        return [{**dict(row), "payload": json.loads(row["payload"])} for row in rows]

    def remember(self, principal: str, role: str, text: str) -> None:
        with self.connect() as db:
            db.execute("INSERT INTO conversation(principal, role, text, created_at) VALUES (?, ?, ?, ?)",
                       (principal, role, text[:16000], now()))
            db.execute("DELETE FROM conversation WHERE principal = ? AND id NOT IN (SELECT id FROM conversation WHERE principal = ? ORDER BY id DESC LIMIT 40)", (principal, principal))

    def conversation(self, principal: str) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("SELECT role, text FROM conversation WHERE principal = ? ORDER BY id DESC LIMIT 12", (principal,)).fetchall()
        return [dict(row) for row in reversed(rows)]

    def forget(self, principal: str) -> None:
        with self.connect() as db:
            db.execute("DELETE FROM conversation WHERE principal = ?", (principal,))

    def propose(self, principal: str, payload: dict) -> dict:
        action_id = uuid.uuid4().hex
        expires = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(timespec="milliseconds")
        with self.connect() as db:
            db.execute("INSERT INTO actions(id, principal, status, payload, created_at, expires_at) VALUES (?, ?, 'pending', ?, ?, ?)",
                       (action_id, principal, json.dumps(payload), now(), expires))
        return self.action(action_id, principal)

    def action(self, action_id: str, principal: str) -> dict:
        with self.connect() as db:
            row = db.execute("SELECT * FROM actions WHERE id = ? AND principal = ?", (action_id, principal)).fetchone()
        if not row:
            raise ValueError("Aktion nicht gefunden.")
        return {**dict(row), "payload": json.loads(row["payload"]), "result": json.loads(row["result"])}

    def claim(self, action_id: str, principal: str) -> dict:
        with self.connect() as db:
            changed = db.execute("UPDATE actions SET status = 'executing' WHERE id = ? AND principal = ? AND status = 'pending' AND expires_at > ?",
                                 (action_id, principal, now())).rowcount
        if not changed:
            raise ValueError("Aktion abgelaufen, bereits verarbeitet oder nicht freigegeben.")
        return self.action(action_id, principal)

    def finish(self, action_id: str, status: str, result: dict) -> None:
        with self.connect() as db:
            db.execute("UPDATE actions SET status = ?, result = ? WHERE id = ?", (status, json.dumps(result), action_id))
        self.event("action", action_id, {"status": status, "result": result})

    def add_rule(self, principal: str, payload: dict) -> dict:
        rule_id = uuid.uuid4().hex
        with self.connect() as db:
            db.execute("INSERT INTO rules(id, principal, payload, created_at) VALUES (?, ?, ?, ?)", (rule_id, principal, json.dumps(payload), now()))
        return {"id": rule_id, "mode": "observe", **payload}

    def rules(self, principal: str | None = None) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM rules WHERE (? IS NULL OR principal = ?)", (principal, principal)).fetchall()
        return [{**dict(row), "payload": json.loads(row["payload"])} for row in rows]

    def rule(self, rule_id: str, principal: str) -> dict:
        rule = next((item for item in self.rules(principal) if item["id"] == rule_id), None)
        if rule is None:
            raise ValueError("Regel nicht gefunden.")
        return rule

    def set_rule_mode(self, rule_id: str, principal: str, mode: str) -> dict:
        if mode not in {"active", "observe"}:
            raise ValueError("Unbekannter Regelmodus.")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT payload FROM rules WHERE id = ? AND principal = ?", (rule_id, principal)).fetchone()
            if not row:
                raise ValueError("Regel nicht gefunden.")
            target = json.loads(row[0])["action"].get("entity_id")
            if mode == "active":
                for other in db.execute("SELECT payload FROM rules WHERE mode = 'active' AND id != ?", (rule_id,)):
                    if json.loads(other[0])["action"].get("entity_id") == target:
                        raise ValueError("Eine aktive Regel steuert dieses Ziel bereits.")
            db.execute("UPDATE rules SET mode = ? WHERE id = ?", (mode, rule_id))
        self.event("automation_mode", rule_id, {"mode": mode})
        return self.rule(rule_id, principal)

    def claim_rule(self, rule_id: str, principal: str, cooldown: int) -> bool:
        timestamp = time.time()
        with self.connect() as db:
            changed = db.execute("UPDATE rules SET last_run = ? WHERE id = ? AND principal = ? AND mode = 'active' AND hold_until <= ? AND last_run <= ?",
                                 (timestamp, rule_id, principal, timestamp, timestamp - cooldown)).rowcount
        return bool(changed)

    def hold_rule(self, rule_id: str, seconds: int = 1800) -> None:
        with self.connect() as db:
            db.execute("UPDATE rules SET hold_until = ? WHERE id = ? AND mode = 'active'", (time.time() + seconds, rule_id))
        self.event("automation_hold", rule_id, {"reason": "external_target_change", "seconds": seconds})

    def prune(self, days: int = 30) -> None:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=max(1, days))).isoformat(timespec="milliseconds")
        with self.connect() as db:
            db.execute("DELETE FROM events WHERE observed_at < ?", (cutoff,))
            db.execute("DELETE FROM conversation WHERE created_at < ?", (cutoff,))
            db.execute("DELETE FROM actions WHERE created_at < ? AND status != 'executing'", (cutoff,))
