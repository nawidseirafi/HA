import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.config import resolve_api_path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class InfrastructureStore:
    def __init__(self, database_path: str | Path = "data/infrastructure/infrastructure.db") -> None:
        self.database_path = resolve_api_path(database_path, "data/infrastructure/infrastructure.db")
        self._ensure_schema()

    def connect(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("pragma busy_timeout = 30000")
        return connection

    def get_state(self, key: str) -> Any:
        with self.connect() as connection:
            row = connection.execute("select value_json from infrastructure_state where key = ?", (key,)).fetchone()
        if row is None:
            return None
        try:
            return json.loads(row["value_json"])
        except (TypeError, json.JSONDecodeError):
            return None

    def set_state(self, key: str, value: Any, updated_at: str | None = None) -> None:
        now = updated_at or utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                insert into infrastructure_state (key, value_json, updated_at)
                values (?, ?, ?)
                on conflict(key) do update set
                    value_json = excluded.value_json,
                    updated_at = excluded.updated_at
                """,
                (key, json.dumps(value, ensure_ascii=False, sort_keys=True), now),
            )
            connection.commit()

    def create_event(
        self,
        source: str,
        event_type: str,
        severity: str,
        title: str,
        message: str,
        status: str = "open",
        started_at: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        with self.connect() as connection:
            cursor = connection.execute(
                """
                insert into infrastructure_events (
                    source, event_type, severity, title, message, status,
                    started_at, payload_json, created_at
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source,
                    event_type,
                    severity,
                    title,
                    message,
                    status,
                    started_at or now,
                    json.dumps(payload or {}, ensure_ascii=False, sort_keys=True),
                    now,
                ),
            )
            connection.commit()
            row = connection.execute("select * from infrastructure_events where id = ?", (cursor.lastrowid,)).fetchone()
        return self._decode_event(dict(row))

    def get_open_event(self, source: str, event_type: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                select * from infrastructure_events
                where source = ? and event_type = ? and status = 'open'
                order by started_at desc, id desc
                limit 1
                """,
                (source, event_type),
            ).fetchone()
        return self._decode_event(dict(row)) if row else None

    def close_event(self, event_id: int, ended_at: str | None = None, message: str | None = None) -> dict[str, Any] | None:
        end = ended_at or utc_now()
        with self.connect() as connection:
            row = connection.execute("select * from infrastructure_events where id = ?", (event_id,)).fetchone()
            if row is None:
                return None
            duration = self._duration_seconds(row["started_at"], end)
            connection.execute(
                """
                update infrastructure_events
                set status = 'closed', ended_at = ?, duration_seconds = ?, message = coalesce(?, message)
                where id = ?
                """,
                (end, duration, message, event_id),
            )
            connection.commit()
            updated = connection.execute("select * from infrastructure_events where id = ?", (event_id,)).fetchone()
        return self._decode_event(dict(updated)) if updated else None

    def get_events(self, limit: int = 100) -> list[dict[str, Any]]:
        limit = min(max(int(limit or 100), 1), 500)
        with self.connect() as connection:
            rows = connection.execute(
                "select * from infrastructure_events order by created_at desc, id desc limit ?",
                (limit,),
            ).fetchall()
        return [self._decode_event(dict(row)) for row in rows]

    def get_recent_events(self, hours: int = 24, limit: int = 100) -> list[dict[str, Any]]:
        limit = min(max(int(limit or 100), 1), 500)
        since = datetime.now(timezone.utc).timestamp() - max(int(hours or 24), 1) * 3600
        with self.connect() as connection:
            rows = connection.execute(
                """
                select * from infrastructure_events
                where strftime('%s', created_at) >= ?
                order by created_at desc, id desc
                limit ?
                """,
                (int(since), limit),
            ).fetchall()
        return [self._decode_event(dict(row)) for row in rows]

    def outage_stats(self, hours: int = 24) -> dict[str, Any]:
        since_ts = datetime.now(timezone.utc).timestamp() - max(int(hours or 24), 1) * 3600
        with self.connect() as connection:
            rows = connection.execute(
                """
                select * from infrastructure_events
                where event_type = 'internet_outage'
                  and strftime('%s', started_at) >= ?
                order by started_at desc, id desc
                """,
                (int(since_ts),),
            ).fetchall()
        events = [self._decode_event(dict(row)) for row in rows]
        duration = sum(int(event.get("duration_seconds") or 0) for event in events if event.get("status") == "closed")
        return {
            "hours": hours,
            "count": len(events),
            "duration_seconds": duration,
            "last_outage": events[0] if events else None,
            "events": events,
        }

    def _ensure_schema(self) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                create table if not exists infrastructure_events (
                    id integer primary key autoincrement,
                    source text not null,
                    event_type text not null,
                    severity text not null,
                    title text not null,
                    message text not null,
                    status text,
                    started_at text,
                    ended_at text,
                    duration_seconds integer,
                    payload_json text,
                    created_at text not null
                )
                """
            )
            connection.execute(
                """
                create table if not exists infrastructure_state (
                    key text primary key,
                    value_json text not null,
                    updated_at text not null
                )
                """
            )
            connection.execute("create index if not exists idx_infrastructure_events_type_status on infrastructure_events(event_type, status)")
            connection.execute("create index if not exists idx_infrastructure_events_created on infrastructure_events(created_at)")
            connection.commit()

    def _decode_event(self, row: dict[str, Any]) -> dict[str, Any]:
        try:
            row["payload"] = json.loads(row.pop("payload_json", "{}") or "{}")
        except (TypeError, json.JSONDecodeError):
            row["payload"] = {}
        return row

    def _duration_seconds(self, start: str | None, end: str | None) -> int | None:
        if not start or not end:
            return None
        try:
            start_dt = datetime.fromisoformat(str(start).replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(str(end).replace("Z", "+00:00"))
        except ValueError:
            return None
        return max(0, int((end_dt - start_dt).total_seconds()))
