from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from backend.config import resolve_api_path


class ContextStore:
    def __init__(self, database_path: str | Path = "data/context/context.db") -> None:
        self.path = resolve_api_path(database_path, "data/context/context.db")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=20)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=20000")
        return connection

    def _ensure_schema(self) -> None:
        with closing(self.connect()) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS context_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    presence_state TEXT NOT NULL,
                    garage_state TEXT NOT NULL,
                    house_state TEXT NOT NULL,
                    vacation_state TEXT NOT NULL,
                    transition_state TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            connection.execute("CREATE INDEX IF NOT EXISTS idx_context_history_created_at ON context_history(created_at)")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS presence_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    presence_state TEXT NOT NULL,
                    departure_state TEXT NOT NULL,
                    person_state TEXT NOT NULL DEFAULT '',
                    details_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            connection.execute("CREATE INDEX IF NOT EXISTS idx_presence_history_created_at ON presence_history(created_at)")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS house_state_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    house_state TEXT NOT NULL,
                    sleep_state TEXT NOT NULL,
                    guest INTEGER NOT NULL DEFAULT 0,
                    details_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            connection.execute("CREATE INDEX IF NOT EXISTS idx_house_state_history_created_at ON house_state_history(created_at)")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS garage_context (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    garage_state TEXT NOT NULL,
                    door_state TEXT NOT NULL DEFAULT '',
                    details_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            connection.execute("CREATE INDEX IF NOT EXISTS idx_garage_context_created_at ON garage_context(created_at)")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS sleep_context (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    sleep_state TEXT NOT NULL,
                    house_state TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    details_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            connection.execute("CREATE INDEX IF NOT EXISTS idx_sleep_context_created_at ON sleep_context(created_at)")
            self._drop_column_if_exists(connection, "presence_history", "vehicle_state")
            self._drop_column_if_exists(connection, "garage_context", "vehicle_state")
            connection.commit()

    def save_snapshot(self, snapshot: dict[str, Any]) -> None:
        created_at = str(snapshot.get("updated_at") or "")
        with closing(self.connect()) as connection:
            connection.execute(
                """
                INSERT INTO context_history (
                    created_at, presence_state, garage_state, house_state, vacation_state,
                    transition_state, confidence, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    created_at,
                    str(snapshot.get("presence") or "UNKNOWN"),
                    str(snapshot.get("garage") or "NONE"),
                    str(snapshot.get("house") or "DAY"),
                    str(snapshot.get("vacation") or "NORMAL"),
                    str(snapshot.get("transition") or "STABLE"),
                    float(snapshot.get("confidence") or 0.0),
                    json.dumps(snapshot, ensure_ascii=False),
                ),
            )
            signals = snapshot.get("signals") if isinstance(snapshot.get("signals"), dict) else {}
            connection.execute(
                """
                INSERT INTO presence_history (
                    created_at, presence_state, departure_state, person_state, details_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    created_at,
                    str(snapshot.get("presence") or "UNKNOWN"),
                    str(snapshot.get("departure") or "UNKNOWN"),
                    str((signals.get("person") or {}).get("state") or ""),
                    json.dumps(snapshot.get("metrics") or {}, ensure_ascii=False),
                ),
            )
            connection.execute(
                """
                INSERT INTO house_state_history (
                    created_at, house_state, sleep_state, guest, details_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    created_at,
                    str(snapshot.get("house") or "DAY"),
                    str(snapshot.get("sleep") or "DAY"),
                    1 if snapshot.get("guest") else 0,
                    json.dumps(snapshot.get("active_rules") or [], ensure_ascii=False),
                ),
            )
            connection.execute(
                """
                INSERT INTO garage_context (
                    created_at, garage_state, door_state, details_json
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    created_at,
                    str(snapshot.get("garage") or "NONE"),
                    str((signals.get("garage_door") or {}).get("state") or ""),
                    json.dumps(snapshot.get("metrics", {}).get("departure") or {}, ensure_ascii=False),
                ),
            )
            connection.execute(
                """
                INSERT INTO sleep_context (
                    created_at, sleep_state, house_state, confidence, details_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    created_at,
                    str(snapshot.get("sleep") or "DAY"),
                    str(snapshot.get("house") or "DAY"),
                    float(snapshot.get("confidence") or 0.0),
                    json.dumps(snapshot.get("metrics", {}).get("house") or {}, ensure_ascii=False),
                ),
            )
            connection.commit()

    def latest_snapshot(self) -> dict[str, Any] | None:
        with closing(self.connect()) as connection:
            row = connection.execute(
                "SELECT * FROM context_history ORDER BY created_at DESC, id DESC LIMIT 1"
            ).fetchone()
        return self._history_row(row) if row else None

    def history(self, limit: int = 100) -> list[dict[str, Any]]:
        clean_limit = max(1, min(int(limit), 500))
        with closing(self.connect()) as connection:
            rows = connection.execute(
                "SELECT * FROM context_history ORDER BY created_at DESC, id DESC LIMIT ?",
                (clean_limit,),
            ).fetchall()
        return [self._history_row(row) for row in rows]

    def table_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        with closing(self.connect()) as connection:
            for table in (
                "context_history",
                "presence_history",
                "house_state_history",
                "garage_context",
                "sleep_context",
            ):
                counts[table] = int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        return counts

    def _history_row(self, row: sqlite3.Row) -> dict[str, Any]:
        payload = self._json(row["payload_json"], {})
        return {
            "id": int(row["id"]),
            "created_at": row["created_at"],
            "presence": row["presence_state"],
            "garage": row["garage_state"],
            "house": row["house_state"],
            "vacation": row["vacation_state"],
            "transition": row["transition_state"],
            "confidence": float(row["confidence"]),
            "payload": payload,
        }

    def _drop_column_if_exists(self, connection: sqlite3.Connection, table: str, column: str) -> None:
        columns = [str(row["name"]) for row in connection.execute(f"PRAGMA table_info({table})").fetchall()]
        if column not in columns:
            return
        try:
            connection.execute(f"ALTER TABLE {table} DROP COLUMN {column}")
        except sqlite3.OperationalError:
            pass

    @staticmethod
    def _json(value: str | None, fallback: Any) -> Any:
        if not value:
            return fallback
        try:
            return json.loads(value)
        except Exception:
            return fallback
