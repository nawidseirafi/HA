import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.config import resolve_api_path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class MessagingStore:
    def __init__(self, database_path: str | Path = "data/messaging/messages.db") -> None:
        self.database_path = resolve_api_path(database_path, "data/messaging/messages.db")
        self._ensure_schema()

    def connect(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def create_message(
        self,
        source: str,
        category: str,
        severity: str,
        title: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        with self.connect() as connection:
            cursor = connection.execute(
                """
                insert into messages (source, category, severity, title, message, payload_json, read, created_at)
                values (?, ?, ?, ?, ?, ?, 0, ?)
                """,
                (
                    source,
                    category,
                    severity,
                    title,
                    message,
                    json.dumps(payload or {}, ensure_ascii=False, sort_keys=True),
                    now,
                ),
            )
            connection.commit()
            row = connection.execute("select * from messages where id = ?", (cursor.lastrowid,)).fetchone()
        return self._decode_message(dict(row))

    def get_messages(self, limit: int = 100, unread_only: bool = False) -> list[dict[str, Any]]:
        limit = min(max(int(limit or 100), 1), 500)
        query = "select * from messages"
        params: list[Any] = []
        if unread_only:
            query += " where read = 0"
        query += " order by created_at desc, id desc limit ?"
        params.append(limit)
        with self.connect() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return [self._decode_message(dict(row)) for row in rows]

    def get_messages_by_source(self, source: str, limit: int = 100) -> list[dict[str, Any]]:
        limit = min(max(int(limit or 100), 1), 500)
        with self.connect() as connection:
            rows = connection.execute(
                "select * from messages where source = ? order by created_at desc, id desc limit ?",
                (source, limit),
            ).fetchall()
        return [self._decode_message(dict(row)) for row in rows]

    def get_unread_count(self) -> int:
        with self.connect() as connection:
            return int(connection.execute("select count(*) from messages where read = 0").fetchone()[0])

    def mark_read(self, message_id: int) -> dict[str, Any] | None:
        with self.connect() as connection:
            connection.execute("update messages set read = 1, read_at = ? where id = ?", (utc_now(), message_id))
            connection.commit()
            row = connection.execute("select * from messages where id = ?", (message_id,)).fetchone()
        return self._decode_message(dict(row)) if row else None

    def mark_all_read(self) -> int:
        with self.connect() as connection:
            cursor = connection.execute("update messages set read = 1, read_at = ? where read = 0", (utc_now(),))
            connection.commit()
            return int(cursor.rowcount)

    def delete_message(self, message_id: int) -> bool:
        with self.connect() as connection:
            cursor = connection.execute("delete from messages where id = ?", (message_id,))
            connection.commit()
            return int(cursor.rowcount) > 0

    def delete_all_messages(self) -> int:
        with self.connect() as connection:
            cursor = connection.execute("delete from messages")
            connection.commit()
            return int(cursor.rowcount)

    def _ensure_schema(self) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                create table if not exists messages (
                    id integer primary key autoincrement,
                    source text not null,
                    category text not null,
                    severity text not null,
                    title text not null,
                    message text not null,
                    payload_json text,
                    read integer not null default 0,
                    created_at text not null,
                    read_at text
                )
                """
            )
            connection.execute(
                """
                create table if not exists notification_targets (
                    id integer primary key autoincrement,
                    target_type text not null,
                    target_value text not null,
                    enabled integer not null default 1,
                    min_severity text not null default 'warning',
                    created_at text not null
                )
                """
            )
            connection.execute("create index if not exists idx_messages_read_created on messages(read, created_at)")
            connection.execute("create index if not exists idx_messages_source_created on messages(source, created_at)")
            connection.commit()

    def _decode_message(self, row: dict[str, Any]) -> dict[str, Any]:
        try:
            row["payload"] = json.loads(row.pop("payload_json", "{}") or "{}")
        except (TypeError, json.JSONDecodeError):
            row["payload"] = {}
        row["read"] = bool(row.get("read"))
        return row
