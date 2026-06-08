import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from backend.config import load_agent_section, resolve_api_path
from backend.editions import active_edition, is_core_service_enabled
from backend.paths import AGENTS_DIR


VALID_SCHEDULE_TYPES = {"once", "recurring", "cron", "condition"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SchedulerStore:
    def __init__(self, database_path: str | Path | None = None) -> None:
        config = load_agent_section("scheduler")
        self.db_path = resolve_api_path(database_path or config.get("database_path"), "data/scheduler/scheduler.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()
        if bool(config.get("default_tasks_enabled", True)):
            self.ensure_default_tasks()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=20)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=20000")
        return connection

    def _ensure_schema(self) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS scheduler_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    schedule_type TEXT NOT NULL,
                    schedule TEXT NOT NULL DEFAULT '{}',
                    next_run TEXT,
                    last_run TEXT,
                    target_agent TEXT NOT NULL DEFAULT '',
                    target_action TEXT NOT NULL DEFAULT '',
                    action_type TEXT NOT NULL DEFAULT 'execute_action',
                    action_payload_json TEXT NOT NULL DEFAULT '{}',
                    source TEXT NOT NULL DEFAULT 'manual',
                    default_key TEXT,
                    status TEXT NOT NULL DEFAULT 'active',
                    failure_count INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS scheduler_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER,
                    task_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    message TEXT NOT NULL DEFAULT '',
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    payload_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            self._add_column_if_missing(connection, "scheduler_tasks", "source", "TEXT NOT NULL DEFAULT 'manual'")
            self._add_column_if_missing(connection, "scheduler_tasks", "default_key", "TEXT")
            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_scheduler_tasks_default_key ON scheduler_tasks(default_key) WHERE default_key IS NOT NULL"
            )
            connection.commit()

    def ensure_default_tasks(self) -> None:
        for item in [*self._manifest_default_tasks(), *self._platform_default_tasks()]:
            if self._default_task_exists(item):
                continue
            self.create_task(item)

    def create_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        now = utc_now()
        schedule_type = self._schedule_type(payload.get("schedule_type"))
        schedule = payload.get("schedule") if isinstance(payload.get("schedule"), dict) else {}
        next_run = self.compute_next_run(schedule_type, schedule, datetime.now(timezone.utc))
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO scheduler_tasks (
                    name, description, enabled, schedule_type, schedule, next_run, last_run,
                    target_agent, target_action, action_type, action_payload_json, source, default_key, status,
                    failure_count, last_error, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, 0, NULL, ?, ?)
                """,
                (
                    str(payload.get("name") or "Scheduler Task"),
                    str(payload.get("description") or ""),
                    1 if payload.get("enabled", True) else 0,
                    schedule_type,
                    json.dumps(schedule),
                    next_run,
                    str(payload.get("target_agent") or ""),
                    str(payload.get("target_action") or ""),
                    str(payload.get("action_type") or "execute_action"),
                    json.dumps(payload.get("action_payload") if isinstance(payload.get("action_payload"), dict) else {}),
                    str(payload.get("source") or "manual"),
                    str(payload.get("default_key") or "") or None,
                    "active" if payload.get("enabled", True) else "disabled",
                    now,
                    now,
                ),
            )
            connection.commit()
            task_id = int(cursor.lastrowid)
        return self.get_task(task_id) or {}

    def update_task(self, task_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        current = self.get_task(task_id)
        if not current:
            raise KeyError(f"Scheduler Task {task_id} nicht gefunden.")
        merged = {**current, **payload}
        schedule = merged.get("schedule") if isinstance(merged.get("schedule"), dict) else {}
        schedule_type = self._schedule_type(merged.get("schedule_type"))
        next_run = self.compute_next_run(schedule_type, schedule, datetime.now(timezone.utc))
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE scheduler_tasks
                SET name = ?, description = ?, enabled = ?, schedule_type = ?, schedule = ?,
                    next_run = ?, target_agent = ?, target_action = ?, action_type = ?,
                    action_payload_json = ?, source = ?, default_key = ?, status = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    str(merged.get("name") or current["name"]),
                    str(merged.get("description") or ""),
                    1 if merged.get("enabled", True) else 0,
                    schedule_type,
                    json.dumps(schedule),
                    next_run,
                    str(merged.get("target_agent") or ""),
                    str(merged.get("target_action") or ""),
                    str(merged.get("action_type") or "execute_action"),
                    json.dumps(merged.get("action_payload") if isinstance(merged.get("action_payload"), dict) else {}),
                    str(merged.get("source") or current.get("source") or "manual"),
                    str(merged.get("default_key") or current.get("default_key") or "") or None,
                    "active" if merged.get("enabled", True) else "disabled",
                    now,
                    task_id,
                ),
            )
            connection.commit()
        return self.get_task(task_id) or {}

    def set_task_enabled(self, task_id: int, enabled: bool) -> dict[str, Any]:
        task = self.get_task(task_id)
        if not task:
            raise KeyError(f"Scheduler Task {task_id} nicht gefunden.")
        now = utc_now()
        next_run = self.compute_next_run(task["schedule_type"], task["schedule"], datetime.now(timezone.utc)) if enabled else None
        with self.connect() as connection:
            connection.execute(
                "UPDATE scheduler_tasks SET enabled = ?, status = ?, next_run = ?, updated_at = ? WHERE id = ?",
                (1 if enabled else 0, "active" if enabled else "disabled", next_run, now, task_id),
            )
            connection.commit()
        return self.get_task(task_id) or {}

    def get_task(self, task_id: int) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM scheduler_tasks WHERE id = ?", (task_id,)).fetchone()
        return self._task_from_row(row) if row else None

    def list_tasks(self, status: str | None = None, limit: int = 500) -> list[dict[str, Any]]:
        where = ""
        params: list[Any] = []
        if status and status != "all":
            if status == "active":
                where = "WHERE enabled = 1 AND status != 'error'"
            elif status == "paused":
                where = "WHERE enabled = 0"
            else:
                where = "WHERE status = ?"
                params.append(status)
        params.append(limit)
        with self.connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM scheduler_tasks {where} ORDER BY COALESCE(next_run, '9999') ASC, id ASC LIMIT ?",
                params,
            ).fetchall()
        return [self._task_from_row(row) for row in rows]

    def due_tasks(self, now: datetime | None = None) -> list[dict[str, Any]]:
        now = now or datetime.now(timezone.utc)
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM scheduler_tasks
                WHERE enabled = 1
                  AND next_run IS NOT NULL
                  AND datetime(next_run) <= datetime(?)
                ORDER BY next_run ASC
                """,
                (now.isoformat(),),
            ).fetchall()
        return [self._task_from_row(row) for row in rows]

    def mark_task_run(self, task: dict[str, Any], status: str, error: str | None = None) -> dict[str, Any]:
        now_dt = datetime.now(timezone.utc)
        next_run = None
        enabled = bool(task.get("enabled"))
        if enabled and task.get("schedule_type") != "once":
            next_run = self.compute_next_run(task["schedule_type"], task["schedule"], now_dt + timedelta(seconds=1))
        elif enabled and task.get("schedule_type") == "once":
            enabled = False
        failure_count = int(task.get("failure_count") or 0)
        if status == "error":
            failure_count += 1
        else:
            failure_count = 0
        if status == "error":
            task_status = "error"
        elif status == "skipped":
            task_status = "paused"
        else:
            task_status = "active" if enabled else "disabled"
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE scheduler_tasks
                SET enabled = ?, last_run = ?, next_run = ?, status = ?, failure_count = ?,
                    last_error = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    1 if enabled else 0,
                    now_dt.isoformat(),
                    next_run,
                    task_status,
                    failure_count,
                    error,
                    now_dt.isoformat(),
                    int(task["id"]),
                ),
            )
            connection.commit()
        return self.get_task(int(task["id"])) or {}

    def record_run(
        self,
        task: dict[str, Any],
        status: str,
        message: str,
        started_at: str,
        finished_at: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO scheduler_runs (task_id, task_name, status, message, started_at, finished_at, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(task.get("id") or 0) or None,
                    str(task.get("name") or "Scheduler Task"),
                    status,
                    message,
                    started_at,
                    finished_at,
                    json.dumps(payload or {}),
                ),
            )
            connection.commit()
            run_id = int(cursor.lastrowid)
            row = connection.execute("SELECT * FROM scheduler_runs WHERE id = ?", (run_id,)).fetchone()
        return self._run_from_row(row)

    def runs(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM scheduler_runs ORDER BY started_at DESC LIMIT ?", (limit,)).fetchall()
        return [self._run_from_row(row) for row in rows]

    def summary(self) -> dict[str, Any]:
        tasks = self.list_tasks()
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        with self.connect() as connection:
            today_count = connection.execute(
                "SELECT COUNT(*) AS count FROM scheduler_runs WHERE datetime(started_at) >= datetime(?)",
                (today_start,),
            ).fetchone()["count"]
        errors = [task for task in tasks if task.get("status") == "error"]
        active = [task for task in tasks if task.get("enabled")]
        next_task = next((task for task in active if task.get("next_run")), None)
        return {
            "active_tasks": len(active),
            "total_tasks": len(tasks),
            "next_run": next_task.get("next_run") if next_task else None,
            "next_task": next_task,
            "today_executed": int(today_count),
            "errors": len(errors),
            "updated_at": utc_now(),
        }

    def compute_next_run(self, schedule_type: str, schedule: dict[str, Any], after: datetime | None = None) -> str | None:
        after = after or datetime.now(timezone.utc)
        schedule_type = self._schedule_type(schedule_type)
        if schedule_type == "once":
            return self._once_next(schedule, after)
        if schedule_type in {"recurring", "condition"}:
            return self._daily_time_next(schedule, after)
        if schedule_type == "cron":
            return self._cron_next(str(schedule.get("cron") or ""), after)
        return None

    def _once_next(self, schedule: dict[str, Any], after: datetime) -> str | None:
        raw = str(schedule.get("run_at") or schedule.get("datetime") or "").strip()
        if not raw:
            return None
        try:
            value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat() if value > after else None

    def _daily_time_next(self, schedule: dict[str, Any], after: datetime) -> str | None:
        raw = str(schedule.get("time") or "08:00").strip()
        try:
            hour_text, minute_text = raw.split(":", 1)
            hour = max(0, min(23, int(hour_text)))
            minute = max(0, min(59, int(minute_text[:2])))
        except (ValueError, TypeError):
            hour, minute = 8, 0
        candidate = after.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= after:
            candidate += timedelta(days=1)
        return candidate.isoformat()

    def _cron_next(self, expression: str, after: datetime) -> str | None:
        parts = expression.split()
        if len(parts) != 5:
            return None
        minute_expr, hour_expr, *_ = parts
        candidate = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
        for _ in range(0, 60 * 24 * 7):
            if self._cron_matches(candidate.minute, minute_expr, 0, 59) and self._cron_matches(candidate.hour, hour_expr, 0, 23):
                return candidate.isoformat()
            candidate += timedelta(minutes=1)
        return None

    def _cron_matches(self, value: int, expression: str, min_value: int, max_value: int) -> bool:
        expression = expression.strip()
        if expression == "*":
            return True
        if expression.startswith("*/"):
            try:
                step = int(expression[2:])
            except ValueError:
                return False
            return step > 0 and value % step == 0
        try:
            exact = int(expression)
        except ValueError:
            return False
        return min_value <= exact <= max_value and value == exact

    def _schedule_type(self, value: Any) -> str:
        text = str(value or "recurring").strip().lower()
        return text if text in VALID_SCHEDULE_TYPES else "recurring"

    def _add_column_if_missing(self, connection: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        columns = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in columns:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def _default_task_exists(self, item: dict[str, Any]) -> bool:
        default_key = str(item.get("default_key") or "").strip()
        name = str(item.get("name") or "").strip()
        with self.connect() as connection:
            row = None
            if default_key:
                row = connection.execute("SELECT id, default_key FROM scheduler_tasks WHERE default_key = ?", (default_key,)).fetchone()
            if row:
                self._sync_platform_default_task(connection, int(row["id"]), item)
                return True
            if name:
                row = connection.execute("SELECT id, default_key FROM scheduler_tasks WHERE name = ?", (name,)).fetchone()
            if row:
                if default_key and not row["default_key"]:
                    connection.execute(
                        "UPDATE scheduler_tasks SET default_key = ?, source = ?, updated_at = ? WHERE id = ?",
                        (default_key, str(item.get("source") or "manifest"), utc_now(), int(row["id"])),
                    )
                    connection.commit()
                self._sync_platform_default_task(connection, int(row["id"]), item)
                return True
        return False

    def _sync_platform_default_task(self, connection: sqlite3.Connection, task_id: int, item: dict[str, Any]) -> None:
        if str(item.get("source") or "") != "platform":
            return
        schedule_type = self._schedule_type(item.get("schedule_type"))
        schedule = item.get("schedule") if isinstance(item.get("schedule"), dict) else {}
        next_run = self.compute_next_run(schedule_type, schedule, datetime.now(timezone.utc))
        connection.execute(
            """
            UPDATE scheduler_tasks
            SET description = ?, schedule_type = ?, schedule = ?, next_run = ?,
                target_agent = ?, target_action = ?, action_type = ?, source = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                str(item.get("description") or ""),
                schedule_type,
                json.dumps(schedule),
                next_run,
                str(item.get("target_agent") or ""),
                str(item.get("target_action") or ""),
                str(item.get("action_type") or "execute_action"),
                str(item.get("source") or "platform"),
                utc_now(),
                task_id,
            ),
        )
        connection.commit()

    def _manifest_default_tasks(self) -> list[dict[str, Any]]:
        tasks: list[dict[str, Any]] = []
        allowed_agents = set(active_edition().enabled_agents)
        for manifest_path in sorted(AGENTS_DIR.glob("*/manifest.yaml")):
            data = self._read_yaml(manifest_path)
            agent_id = str(data.get("id") or manifest_path.parent.name).strip()
            if agent_id not in allowed_agents:
                continue
            scheduler = data.get("scheduler") if isinstance(data.get("scheduler"), dict) else {}
            raw_tasks = scheduler.get("tasks") if isinstance(scheduler.get("tasks"), list) else []
            for index, raw_task in enumerate(raw_tasks):
                if not isinstance(raw_task, dict):
                    continue
                task = {
                    "name": str(raw_task.get("name") or f"{agent_id} Task"),
                    "description": str(raw_task.get("description") or ""),
                    "enabled": bool(raw_task.get("enabled", True)),
                    "schedule_type": raw_task.get("schedule_type") or "recurring",
                    "schedule": raw_task.get("schedule") if isinstance(raw_task.get("schedule"), dict) else {},
                    "target_agent": str(raw_task.get("target_agent") or agent_id),
                    "target_action": str(raw_task.get("target_action") or "run"),
                    "action_type": str(raw_task.get("action_type") or "execute_action"),
                    "action_payload": raw_task.get("action_payload") if isinstance(raw_task.get("action_payload"), dict) else {},
                    "source": f"manifest:{agent_id}",
                    "default_key": str(raw_task.get("default_key") or f"{agent_id}:{index}:{raw_task.get('name') or 'task'}"),
                }
                tasks.append(task)
        return tasks

    def _platform_default_tasks(self) -> list[dict[str, Any]]:
        tasks = [
            {
                "name": "Infrastructure Health Check",
                "description": "Prueft alle 5 Minuten Internet- und FritzBox-Status ueber Home Assistant.",
                "schedule_type": "cron",
                "schedule": {"cron": "*/5 * * * *"},
                "target_agent": "infrastructure",
                "target_action": "check",
                "action_type": "infrastructure_check",
                "source": "platform",
                "default_key": "platform:infrastructure:health-check",
            },
            {
                "name": "Household Fensterpruefung",
                "description": "Prueft abends Haushaltshinweise wie offene Fenster und erzeugt zentrale Nachrichten.",
                "schedule_type": "recurring",
                "schedule": {"time": "22:00"},
                "target_agent": "household",
                "target_action": "summary",
                "action_type": "household_check",
                "source": "platform",
                "default_key": "platform:household:window-check",
            },
            {
                "name": "System Updatepruefung",
                "description": "Prueft taeglich um 07:00 Uhr, ob ein RoboterSteve/SeniorCare Update verfuegbar ist.",
                "schedule_type": "cron",
                "schedule": {"cron": "0 7 * * *"},
                "target_agent": "system",
                "target_action": "update_check",
                "action_type": "update_check",
                "source": "platform",
                "default_key": "platform:system:update-check",
            },
        ]
        return [
            task for task in tasks
            if str(task.get("target_agent") or "") not in {"infrastructure", "household", "system"}
            or is_core_service_enabled(str(task.get("target_agent") or ""))
        ]

    def _read_yaml(self, path: Path) -> dict[str, Any]:
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            return {}
        return data if isinstance(data, dict) else {}

    def _task_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["enabled"] = bool(item.get("enabled"))
        item["schedule"] = self._json(item.pop("schedule", "{}"), {})
        item["action_payload"] = self._json(item.pop("action_payload_json", "{}"), {})
        return item

    def _run_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["payload"] = self._json(item.pop("payload_json", "{}"), {})
        return item

    def _json(self, raw: Any, fallback: Any) -> Any:
        if isinstance(raw, (dict, list)):
            return raw
        try:
            return json.loads(str(raw or ""))
        except (TypeError, ValueError, json.JSONDecodeError):
            return fallback
