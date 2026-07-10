from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from backend.config import resolve_api_path


class GardenStore:
    def __init__(self, database_path: str | Path = "data/garden/garden.db") -> None:
        self.path = resolve_api_path(database_path, "data/garden/garden.db")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                create table if not exists garden_snapshots (
                    id integer primary key autoincrement,
                    created_at text not null,
                    status text not null,
                    payload_json text not null
                )
                """
            )
            connection.execute("create index if not exists idx_garden_snapshots_created_at on garden_snapshots(created_at)")

    def add_snapshot(self, created_at: str, status: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self._connect() as connection:
            cursor = connection.execute(
                "insert into garden_snapshots (created_at, status, payload_json) values (?, ?, ?)",
                (created_at, status, json.dumps(payload, ensure_ascii=False)),
            )
            snapshot_id = int(cursor.lastrowid)
        return {"id": snapshot_id, "created_at": created_at, "status": status}

    def latest_snapshot(self) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "select * from garden_snapshots order by created_at desc, id desc limit 1"
            ).fetchone()
        return self._row(row) if row else None

    def history(self, limit: int = 100) -> list[dict[str, Any]]:
        clean_limit = max(1, min(int(limit), 500))
        with self._connect() as connection:
            rows = connection.execute(
                "select * from garden_snapshots order by created_at desc, id desc limit ?",
                (clean_limit,),
            ).fetchall()
        return [self._row(row) for row in rows]

    def _row(self, row: sqlite3.Row) -> dict[str, Any]:
        try:
            payload = json.loads(row["payload_json"])
        except Exception:
            payload = {}
        return {
            "id": row["id"],
            "created_at": row["created_at"],
            "status": row["status"],
            "payload": payload,
        }
