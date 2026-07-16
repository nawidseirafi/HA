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
            connection.execute(
                """
                create table if not exists garden_zones (
                    id text primary key,
                    name text not null,
                    enabled integer not null default 1,
                    created_at text not null,
                    updated_at text not null
                )
                """
            )
            connection.execute(
                """
                create table if not exists garden_decisions (
                    id integer primary key autoincrement,
                    zone_id text not null,
                    evaluated_at text not null,
                    status text not null,
                    decision text not null,
                    recommended_duration_minutes integer,
                    apply_allowed integer not null default 0,
                    reasons_json text not null default '[]',
                    blocks_json text not null default '[]',
                    input_snapshot_json text not null default '{}'
                )
                """
            )
            connection.execute("create index if not exists idx_garden_decisions_zone_time on garden_decisions(zone_id, evaluated_at)")
            connection.execute(
                """
                create table if not exists garden_actions (
                    id integer primary key autoincrement,
                    zone_id text not null,
                    action text not null,
                    source text not null,
                    requested_at text not null,
                    completed_at text,
                    success integer,
                    entity_id text,
                    ha_domain text,
                    ha_service text,
                    details_json text not null default '{}',
                    error text
                )
                """
            )
            connection.execute("create index if not exists idx_garden_actions_zone_time on garden_actions(zone_id, requested_at)")
            connection.execute(
                """
                create table if not exists garden_irrigation_runs (
                    id integer primary key autoincrement,
                    zone_id text not null,
                    started_at text not null,
                    planned_end_at text not null,
                    ended_at text,
                    planned_duration_minutes integer not null,
                    actual_duration_seconds integer,
                    start_moisture real,
                    end_moisture real,
                    source text not null,
                    status text not null,
                    stop_reason text,
                    start_action_id integer,
                    stop_action_id integer
                )
                """
            )
            connection.execute("create index if not exists idx_garden_irrigation_runs_zone_status on garden_irrigation_runs(zone_id, status, started_at)")

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

    def upsert_zone(self, zone_id: str, name: str, enabled: bool, now: str) -> dict[str, Any]:
        with self._connect() as connection:
            connection.execute(
                """
                insert into garden_zones (id, name, enabled, created_at, updated_at)
                values (?, ?, ?, ?, ?)
                on conflict(id) do update set name = excluded.name, enabled = excluded.enabled, updated_at = excluded.updated_at
                """,
                (zone_id, name, 1 if enabled else 0, now, now),
            )
        return {"id": zone_id, "name": name, "enabled": enabled, "updated_at": now}

    def save_decision(self, decision: dict[str, Any]) -> dict[str, Any]:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                insert into garden_decisions (
                    zone_id, evaluated_at, status, decision, recommended_duration_minutes,
                    apply_allowed, reasons_json, blocks_json, input_snapshot_json
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    decision["zone_id"],
                    decision["evaluated_at"],
                    decision["status"],
                    decision["decision"],
                    decision.get("recommended_duration_minutes"),
                    1 if decision.get("apply_allowed") else 0,
                    json.dumps(decision.get("reasons") or [], ensure_ascii=False),
                    json.dumps(decision.get("blocks") or [], ensure_ascii=False),
                    json.dumps(decision.get("input_snapshot") or {}, ensure_ascii=False),
                ),
            )
            row = connection.execute("select * from garden_decisions where id = ?", (cursor.lastrowid,)).fetchone()
        return self._decision_row(row)

    def list_decisions(self, zone_id: str, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "select * from garden_decisions where zone_id = ? order by evaluated_at desc, id desc limit ?",
                (zone_id, max(1, min(int(limit), 500))),
            ).fetchall()
        return [self._decision_row(row) for row in rows]

    def create_action(self, zone_id: str, action: str, source: str, requested_at: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._connect() as connection:
            cursor = connection.execute(
                "insert into garden_actions (zone_id, action, source, requested_at, details_json) values (?, ?, ?, ?, ?)",
                (zone_id, action, source, requested_at, json.dumps(details or {}, ensure_ascii=False)),
            )
            row = connection.execute("select * from garden_actions where id = ?", (cursor.lastrowid,)).fetchone()
        return self._action_row(row)

    def complete_action(
        self,
        action_id: int,
        completed_at: str,
        success: bool,
        entity_id: str = "",
        ha_domain: str = "",
        ha_service: str = "",
        details: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        with self._connect() as connection:
            connection.execute(
                """
                update garden_actions
                set completed_at = ?, success = ?, entity_id = ?, ha_domain = ?, ha_service = ?, details_json = ?, error = ?
                where id = ?
                """,
                (completed_at, 1 if success else 0, entity_id, ha_domain, ha_service, json.dumps(details or {}, ensure_ascii=False), error, action_id),
            )
            row = connection.execute("select * from garden_actions where id = ?", (action_id,)).fetchone()
        return self._action_row(row)

    def start_irrigation_run(
        self,
        zone_id: str,
        started_at: str,
        planned_end_at: str,
        planned_duration_minutes: int,
        source: str,
        start_moisture: float | None,
        start_action_id: int | None,
    ) -> dict[str, Any]:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                insert into garden_irrigation_runs (
                    zone_id, started_at, planned_end_at, planned_duration_minutes,
                    start_moisture, source, status, start_action_id
                ) values (?, ?, ?, ?, ?, ?, 'running', ?)
                """,
                (zone_id, started_at, planned_end_at, planned_duration_minutes, start_moisture, source, start_action_id),
            )
            row = connection.execute("select * from garden_irrigation_runs where id = ?", (cursor.lastrowid,)).fetchone()
        return self._run_row(row)

    def close_irrigation_run(
        self,
        run_id: int,
        ended_at: str,
        end_moisture: float | None,
        stop_reason: str,
        stop_action_id: int | None,
        status: str = "completed",
    ) -> dict[str, Any]:
        current = self.get_irrigation_run(run_id)
        actual_duration_seconds = None
        if current:
            try:
                from datetime import datetime

                started = datetime.fromisoformat(str(current["started_at"]).replace("Z", "+00:00"))
                ended = datetime.fromisoformat(str(ended_at).replace("Z", "+00:00"))
                actual_duration_seconds = int((ended - started).total_seconds())
            except Exception:
                actual_duration_seconds = None
        with self._connect() as connection:
            connection.execute(
                """
                update garden_irrigation_runs
                set ended_at = ?, actual_duration_seconds = ?, end_moisture = ?, stop_reason = ?, stop_action_id = ?, status = ?
                where id = ?
                """,
                (ended_at, actual_duration_seconds, end_moisture, stop_reason, stop_action_id, status, run_id),
            )
            row = connection.execute("select * from garden_irrigation_runs where id = ?", (run_id,)).fetchone()
        return self._run_row(row)

    def get_irrigation_run(self, run_id: int) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("select * from garden_irrigation_runs where id = ?", (run_id,)).fetchone()
        return self._run_row(row) if row else None

    def open_irrigation_run(self, zone_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "select * from garden_irrigation_runs where zone_id = ? and status = 'running' order by started_at desc, id desc limit 1",
                (zone_id,),
            ).fetchone()
        return self._run_row(row) if row else None

    def latest_completed_irrigation_run(self, zone_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "select * from garden_irrigation_runs where zone_id = ? and ended_at is not null order by ended_at desc, id desc limit 1",
                (zone_id,),
            ).fetchone()
        return self._run_row(row) if row else None

    def list_irrigation_runs(self, zone_id: str, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "select * from garden_irrigation_runs where zone_id = ? order by started_at desc, id desc limit ?",
                (zone_id, max(1, min(int(limit), 500))),
            ).fetchall()
        return [self._run_row(row) for row in rows]

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

    def _decision_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "zone_id": row["zone_id"],
            "evaluated_at": row["evaluated_at"],
            "status": row["status"],
            "decision": row["decision"],
            "recommended_duration_minutes": row["recommended_duration_minutes"],
            "apply_allowed": bool(row["apply_allowed"]),
            "reasons": self._json(row["reasons_json"], []),
            "blocks": self._json(row["blocks_json"], []),
            "input_snapshot": self._json(row["input_snapshot_json"], {}),
        }

    def _action_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "zone_id": row["zone_id"],
            "action": row["action"],
            "source": row["source"],
            "requested_at": row["requested_at"],
            "completed_at": row["completed_at"],
            "success": None if row["success"] is None else bool(row["success"]),
            "entity_id": row["entity_id"],
            "ha_domain": row["ha_domain"],
            "ha_service": row["ha_service"],
            "details": self._json(row["details_json"], {}),
            "error": row["error"],
        }

    def _run_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "zone_id": row["zone_id"],
            "started_at": row["started_at"],
            "planned_end_at": row["planned_end_at"],
            "ended_at": row["ended_at"],
            "planned_duration_minutes": row["planned_duration_minutes"],
            "actual_duration_seconds": row["actual_duration_seconds"],
            "start_moisture": row["start_moisture"],
            "end_moisture": row["end_moisture"],
            "source": row["source"],
            "status": row["status"],
            "stop_reason": row["stop_reason"],
            "start_action_id": row["start_action_id"],
            "stop_action_id": row["stop_action_id"],
        }

    def _json(self, raw: Any, fallback: Any) -> Any:
        try:
            return json.loads(raw or "")
        except Exception:
            return fallback
