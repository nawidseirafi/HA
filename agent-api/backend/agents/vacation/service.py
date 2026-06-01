import json
import logging
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from backend.config import load_agent_section, resolve_api_path
from backend.paths import AGENTS_DIR
from backend.services.core.ha_client import HomeAssistantClient
from backend.services.messaging import MessagingService
from backend.services.waste_service import WasteService

logger = logging.getLogger(__name__)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


DEFAULT_CALENDAR_KEYWORDS = ("urlaub", "vacation", "abwesenheit", "reise", "travel", "holiday", "ferie", "ferien")


class VacationService:
    def __init__(self, ha_client: HomeAssistantClient | None = None) -> None:
        self._ha_client = ha_client
        self._last_run: dict[str, Any] | None = None
        self._last_scheduled_run: str | None = None
        self._last_error: str | None = None
        self.scheduler_stop = threading.Event()
        self.scheduler_thread: threading.Thread | None = None
        self._ensure_schema()

    def config(self) -> dict[str, Any]:
        config = load_agent_section("vacation")
        return {
            "enabled": self._bool_config(config.get("enabled", True)),
            "mode_entity": config.get("mode_entity", "input_boolean.vacation_mode"),
            "calendar_entity": config.get("calendar_entity", "auto"),
            "calendar_keywords": config.get("calendar_keywords") or list(DEFAULT_CALENDAR_KEYWORDS),
            "pre_departure_days": int(config.get("pre_departure_days", 3) or 3),
            "schedule_times": self._schedule_times(config.get("schedule_times")),
            "notifications": config.get("notifications") if isinstance(config.get("notifications"), dict) else {},
            "database_path": str(self.db_path()),
            "log_path": str(self.log_path()),
        }

    def status(self) -> dict[str, Any]:
        return self.get_status()

    def enable(self) -> dict[str, Any]:
        self._write_config(enabled=True)
        self._last_error = None
        return self.get_status()

    def disable(self) -> dict[str, Any]:
        self._write_config(enabled=False)
        return self.get_status()

    def toggle(self) -> dict[str, Any]:
        return self.disable() if self.config()["enabled"] else self.enable()

    def update_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        updates: dict[str, Any] = {}
        if "enabled" in payload:
            updates["enabled"] = bool(payload["enabled"])
        if "calendar_entity" in payload:
            updates["calendar_entity"] = str(payload["calendar_entity"] or "auto").strip() or "auto"
        if "schedule_times" in payload and isinstance(payload["schedule_times"], list):
            updates["schedule_times"] = [str(item).strip()[:5] for item in payload["schedule_times"] if str(item).strip()]
        if updates:
            self._write_config(**updates)
        return self.get_status()

    def start_scheduler(self) -> None:
        if self.scheduler_thread and self.scheduler_thread.is_alive():
            return
        self.scheduler_stop.clear()
        self.scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self.scheduler_thread.start()
        self._log("Vacation scheduler gestartet.")

    def stop_scheduler(self) -> None:
        self.scheduler_stop.set()

    def _scheduler_loop(self) -> None:
        last_run_keys: set[str] = set()
        while not self.scheduler_stop.is_set():
            now = datetime.now()
            today_key = now.date().isoformat()
            last_run_keys = {key for key in last_run_keys if key.startswith(today_key)}
            config = self.config()
            if config["enabled"]:
                for schedule_time in config["schedule_times"]:
                    run_key = f"{today_key}:{schedule_time}"
                    if run_key in last_run_keys:
                        continue
                    if self._time_due(now, schedule_time):
                        self._last_scheduled_run = utc_now()
                        self.run(dry_run=False)
                        last_run_keys.add(run_key)
            self.scheduler_stop.wait(30)

    def get_status(self) -> dict[str, Any]:
        config = self.config()
        vacation_mode = {"active": None, "source": config["mode_entity"], "updated_at": None, "error": None}
        current_status = "disabled" if not config["enabled"] else "idle"
        error = self._last_error
        try:
            vacation_mode = self.get_vacation_mode_state()
        except Exception as exc:
            current_status = "error"
            error = str(exc)
            vacation_mode["error"] = str(exc)
        reminders = self.get_reminders(status="open", limit=20)
        calendar = self.resolve_calendar_entity()
        calendar_period = self.calendar_vacation_period(calendar.get("entity_id"), calendar)
        if not calendar_period:
            for candidate in calendar.get("candidates", []):
                candidate_id = candidate.get("entity_id")
                if candidate_id == calendar.get("entity_id"):
                    continue
                calendar_period = self.calendar_vacation_period(candidate_id, candidate)
                if calendar_period:
                    calendar["entity_id"] = candidate_id
                    break
        if calendar_period:
            self.save_period(
                start_date=calendar_period.get("start_date"),
                end_date=calendar_period.get("end_date"),
                source="calendar",
                title=calendar_period.get("title"),
                calendar_entity=calendar_period.get("calendar_entity"),
                active=False,
            )
        active_period = self._active_period()
        summary = self._summary_counts()
        agent = {
            "enabled": config["enabled"],
            "status": current_status if current_status != "idle" else "active",
            "last_run": self._last_run.get("finished_at") if isinstance(self._last_run, dict) else None,
            "last_check": self._last_run.get("started_at") if isinstance(self._last_run, dict) else None,
            "last_error": error,
            "scheduler_running": bool(self.scheduler_thread and self.scheduler_thread.is_alive()),
            "schedule_times": config["schedule_times"],
            "last_scheduled_run": self._last_scheduled_run,
        }
        period = {
            "start_date": (calendar_period or active_period or {}).get("start_date"),
            "end_date": (calendar_period or active_period or {}).get("end_date"),
            "source": (calendar_period or {}).get("source") or ("local" if active_period else None),
            "title": (calendar_period or {}).get("title"),
            "calendar_entity": (calendar_period or {}).get("calendar_entity"),
            "duration_days": self._duration_days((calendar_period or active_period or {}).get("start_date"), (calendar_period or active_period or {}).get("end_date")),
        }
        return {
            "agent": agent,
            "vacation_mode": vacation_mode,
            "period": period,
            "summary": summary,
            "calendar_entity": calendar.get("entity_id"),
            "calendar_source": calendar.get("source"),
            "calendar_candidates": calendar.get("candidates", []),
            "calendar_error": calendar.get("error"),
            "enabled": agent["enabled"],
            "current_status": agent["status"],
            "mode_entity": config["mode_entity"],
            "vacation_mode_active": vacation_mode.get("active"),
            "active_period": active_period,
            "history_active": bool(active_period),
            "reminders": reminders,
            "open_reminders": len(reminders),
            "last_run": self._last_run,
            "last_error": error,
            "database_path": config["database_path"],
            "log_path": config["log_path"],
        }

    def start_vacation(self, start_date: str | None = None, end_date: str | None = None) -> dict[str, Any]:
        now = utc_now()
        start = start_date or now[:10]
        period = self.save_period(start_date=start, end_date=end_date, source="manual", active=True)
        self.create_event(
            event_type="vacation_started",
            severity="info",
            message="Vacation period started.",
            payload={"period": period},
        )
        return {"ok": True, "period": period, "status": self.get_status()}

    def end_vacation(self, end_date: str | None = None) -> dict[str, Any]:
        ended_at = end_date or utc_now()[:10]
        with self._connect() as connection:
            active = connection.execute(
                "select * from vacation_periods where active = 1 order by created_at desc, id desc limit 1"
            ).fetchone()
            connection.execute(
                "update vacation_periods set active = 0, end_date = coalesce(end_date, ?) where active = 1",
                (ended_at,),
            )
            connection.commit()
        self.create_event(
            event_type="vacation_ended",
            severity="info",
            message="Vacation period ended.",
            payload={"previous_period": dict(active) if active else None, "end_date": ended_at},
        )
        return {"ok": True, "ended_at": ended_at, "status": self.get_status()}

    def create_event(
        self,
        event_type: str,
        severity: str = "info",
        message: str = "",
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                insert into vacation_events (event_type, severity, message, payload_json, created_at)
                values (?, ?, ?, ?, ?)
                """,
                (
                    str(event_type or "event"),
                    str(severity or "info"),
                    str(message or ""),
                    json.dumps(payload or {}, ensure_ascii=False, sort_keys=True),
                    utc_now(),
                ),
            )
            connection.commit()
            row = connection.execute("select * from vacation_events where id = ?", (cursor.lastrowid,)).fetchone()
        return self._decode_event(dict(row))

    def get_reminders(self, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        limit = min(max(int(limit or 100), 1), 500)
        query = "select * from vacation_reminders"
        params: list[Any] = []
        if status:
            query += " where status = ?"
            params.append(status)
        query += " order by due_at is null, due_at asc, created_at desc, id desc limit ?"
        params.append(limit)
        with self._connect() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return [dict(row) for row in rows]

    def get_profiles(self, limit: int = 100) -> dict[str, Any]:
        limit = min(max(int(limit or 100), 1), 500)
        with self._connect() as connection:
            rows = connection.execute(
                "select * from presence_profiles order by updated_at desc, room, weekday limit ?",
                (limit,),
            ).fetchall()
        profiles = [dict(row) for row in rows]
        analyzed_days = len({(item.get("weekday"), item.get("updated_at", "")[:10]) for item in profiles})
        avg_confidence = round(sum(float(item.get("confidence") or 0) for item in profiles) / len(profiles), 2) if profiles else 0
        return {
            "status": "profile_available" if profiles else "learning",
            "analyzed_days": analyzed_days,
            "profile_count": len(profiles),
            "confidence": avg_confidence,
            "profiles": profiles,
        }

    def history(self, limit: int = 100) -> dict[str, Any]:
        limit = min(max(int(limit or 100), 1), 500)
        with self._connect() as connection:
            periods = connection.execute(
                "select * from vacation_periods order by created_at desc, id desc limit ?",
                (limit,),
            ).fetchall()
            events = connection.execute(
                "select * from vacation_events order by created_at desc, id desc limit ?",
                (limit,),
            ).fetchall()
            reminders = connection.execute(
                "select * from vacation_reminders order by created_at desc, id desc limit ?",
                (limit,),
            ).fetchall()
            profiles = connection.execute(
                "select * from presence_profiles order by room, weekday limit ?",
                (limit,),
            ).fetchall()
        return {
            "periods": [dict(row) for row in periods],
            "events": [self._decode_event(dict(row)) for row in events],
            "reminders": [dict(row) for row in reminders],
            "presence_profiles": [dict(row) for row in profiles],
        }

    def run(
        self,
        dry_run: bool = True,
        action: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        config = self.config()
        started_at = utc_now()
        if not config["enabled"]:
            result = {
                "status": "disabled",
                "message": "Vacation-Agent ist deaktiviert.",
                "dry_run": dry_run,
                "started_at": started_at,
            }
            self._last_run = result
            return result

        try:
            vacation_mode = self.get_vacation_mode()
            period = self.get_status().get("period", {})
            reminders = self.refresh_reminders(vacation_mode=vacation_mode, period=period)
            notification = self.send_pre_departure_notification(reminders, period)
            profiles = self.refresh_presence_profiles()
            result = {
                "status": "ok",
                "message": "Vacation-Agent bereit.",
                "dry_run": dry_run,
                "vacation_mode": vacation_mode,
                "mode_entity": config["mode_entity"],
                "started_at": started_at,
                "finished_at": utc_now(),
                "actions": ["calendar_check", "reminder_refresh", "presence_profile_refresh"],
                "reminders": len(reminders),
                "notification": notification,
                "profiles": len(profiles),
            }
            self._last_error = None
            self._last_run = result
            self._log(f"run dry_run={dry_run} vacation_mode={vacation_mode}")
            self.create_event(
                event_type="agent_run",
                severity="info",
                message="Vacation-Agent run completed.",
                payload=result,
            )
            return result
        except Exception as exc:
            self._last_error = str(exc)
            logger.exception("Vacation-Agent-Lauf fehlgeschlagen.")
            result = {
                "status": "error",
                "message": str(exc),
                "dry_run": dry_run,
                "started_at": started_at,
                "finished_at": utc_now(),
                "actions": [],
            }
            self._last_run = result
            self.create_event(
                event_type="agent_run_failed",
                severity="error",
                message=str(exc),
                payload=result,
            )
            return result

    def get_vacation_mode(self) -> bool:
        return bool(self.get_vacation_mode_state().get("active"))

    def get_vacation_mode_state(self) -> dict[str, Any]:
        mode_entity = self.config()["mode_entity"]
        state = self._ha().get_state(mode_entity)
        return {
            "active": state.get("state") == "on",
            "source": mode_entity,
            "updated_at": state.get("last_changed") or state.get("last_updated"),
        }

    def set_vacation_mode(self, active: bool) -> dict[str, Any]:
        mode_entity = self.config()["mode_entity"]
        service = "turn_on" if active else "turn_off"
        self._ha().call_service("input_boolean", service, {"entity_id": mode_entity})
        state = self.get_vacation_mode_state()
        return {"ok": True, "vacation_mode": state}

    def enable_vacation_mode(self) -> dict[str, Any]:
        return self.set_vacation_mode(True)

    def disable_vacation_mode(self) -> dict[str, Any]:
        return self.set_vacation_mode(False)

    def toggle_vacation_mode(self) -> dict[str, Any]:
        current = self.get_vacation_mode_state()
        return self.set_vacation_mode(not bool(current.get("active")))

    def save_period(
        self,
        start_date: str | None,
        end_date: str | None,
        source: str = "manual",
        title: str | None = None,
        calendar_entity: str | None = None,
        active: bool = False,
    ) -> dict[str, Any]:
        start = self._date_only(start_date)
        end = self._date_only(end_date)
        if not start and not end:
            start = utc_now()[:10]
        now = utc_now()
        with self._connect() as connection:
            existing = connection.execute(
                """
                select * from vacation_periods
                where coalesce(start_date, '') = coalesce(?, '')
                  and coalesce(end_date, '') = coalesce(?, '')
                  and coalesce(source, '') = coalesce(?, '')
                order by id desc limit 1
                """,
                (start, end, source),
            ).fetchone()
            if active:
                connection.execute("update vacation_periods set active = 0 where active = 1")
            if existing:
                connection.execute(
                    """
                    update vacation_periods
                    set active = max(active, ?), payload_json = ?, created_at = created_at
                    where id = ?
                    """,
                    (1 if active else 0, json.dumps({"title": title, "calendar_entity": calendar_entity}, ensure_ascii=False), existing["id"]),
                )
                connection.commit()
                row = connection.execute("select * from vacation_periods where id = ?", (existing["id"],)).fetchone()
            else:
                cursor = connection.execute(
                    """
                    insert into vacation_periods (start_date, end_date, source, active, payload_json, created_at)
                    values (?, ?, ?, ?, ?, ?)
                    """,
                    (start, end, source, 1 if active else 0, json.dumps({"title": title, "calendar_entity": calendar_entity}, ensure_ascii=False), now),
                )
                connection.commit()
                row = connection.execute("select * from vacation_periods where id = ?", (cursor.lastrowid,)).fetchone()
        return self._decode_period(dict(row))

    def refresh_reminders(self, vacation_mode: bool | None = None, period: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        try:
            states = self._ha().get_states()
        except Exception as exc:
            self._last_error = str(exc)
            self._close_generated_reminders()
            return [
                self._save_reminder(
                    reminder_type="internet",
                    title="Internetproblem erkannt",
                    message="Die Verbindung zu Home Assistant ist aktuell nicht erreichbar. Bitte vor dem Urlaub Netzwerk und Fernzugriff prüfen.",
                    severity="critical",
                )
            ]
        self._close_generated_reminders()
        period = period or {}
        pre_departure = self._is_pre_departure_window(period)
        candidates = self._reminder_candidates(states, vacation_mode=bool(vacation_mode), period=period, pre_departure=pre_departure)
        candidates.extend(self._waste_reminders_from_service(period, pre_departure=pre_departure))
        return [self._save_reminder(**candidate) for candidate in candidates]

    def send_pre_departure_notification(self, reminders: list[dict[str, Any]], period: dict[str, Any]) -> dict[str, Any]:
        config = self.config()
        notify_config = config.get("notifications") or {}
        if not notify_config.get("enabled", False):
            return {"sent": False, "reason": "disabled"}
        if not self._is_pre_departure_window(period):
            return {"sent": False, "reason": "not_in_pre_departure_window"}
        actionable = [
            item for item in reminders
            if str(item.get("severity") or "").lower() in {"warning", "critical"}
            and str(item.get("reminder_type") or "") not in {"internet", "security"}
        ]
        if not actionable:
            return {"sent": False, "reason": "no_warning_or_critical_reminders"}
        tag = f"vacation_pre_departure_{period.get('start_date') or utc_now()[:10]}"
        if self._notification_already_sent(tag):
            return {"sent": False, "reason": "already_sent"}
        title = "Schöne Reise"
        message = "Bitte denk vor der Abreise noch daran:\n" + "\n".join(
            f"- {self._push_text_for_reminder(item)}"
            for item in actionable[:5]
        )
        notify_service = str(notify_config.get("notify_service") or "").strip()
        try:
            if notify_service:
                self._ha().notify(notify_service, title, message, data={"tag": tag, "priority": "high"})
            if notify_config.get("persistent", False):
                self._ha().persistent_notification(title, message, notification_id=tag)
            self.create_event(
                event_type="pre_departure_notification_sent",
                severity="info",
                message=title,
                payload={"tag": tag, "reminders": [item.get("id") for item in actionable], "period": period},
            )
            for item in actionable:
                self._message_from_reminder(item)
            return {"sent": True, "tag": tag, "reminders": len(actionable)}
        except Exception as exc:
            self.create_event(
                event_type="pre_departure_notification_failed",
                severity="warning",
                message=str(exc),
                payload={"tag": tag, "period": period},
            )
            return {"sent": False, "reason": str(exc)}

    def refresh_presence_profiles(self) -> list[dict[str, Any]]:
        try:
            states = self._ha().get_states()
        except Exception:
            return []
        rooms: dict[str, dict[str, Any]] = {}
        for state in states:
            entity_id = str(state.get("entity_id") or "")
            if not entity_id.startswith(("light.", "switch.")):
                continue
            room = self._room_from_state(state)
            item = rooms.setdefault(room, {"on": 0, "total": 0})
            item["total"] += 1
            if state.get("state") == "on":
                item["on"] += 1
        now = datetime.now(timezone.utc)
        weekday = now.weekday()
        updated: list[dict[str, Any]] = []
        with self._connect() as connection:
            for room, values in rooms.items():
                confidence = min(0.95, max(0.1, float(values["total"]) / 20.0))
                on_time = now.strftime("%H:%M") if values["on"] else None
                off_time = now.strftime("%H:%M") if not values["on"] else None
                existing = connection.execute(
                    "select id from presence_profiles where room = ? and weekday = ?",
                    (room, weekday),
                ).fetchone()
                if existing:
                    connection.execute(
                        """
                        update presence_profiles
                        set avg_on_time = coalesce(?, avg_on_time),
                            avg_off_time = coalesce(?, avg_off_time),
                            confidence = max(confidence, ?),
                            updated_at = ?
                        where id = ?
                        """,
                        (on_time, off_time, confidence, utc_now(), existing["id"]),
                    )
                    row_id = existing["id"]
                else:
                    cursor = connection.execute(
                        """
                        insert into presence_profiles (room, weekday, avg_on_time, avg_off_time, confidence, updated_at)
                        values (?, ?, ?, ?, ?, ?)
                        """,
                        (room, weekday, on_time, off_time, confidence, utc_now()),
                    )
                    row_id = cursor.lastrowid
                row = connection.execute("select * from presence_profiles where id = ?", (row_id,)).fetchone()
                updated.append(dict(row))
            connection.commit()
        return updated

    def resolve_calendar_entity(self) -> dict[str, Any]:
        configured = str(self.config().get("calendar_entity") or "auto").strip()
        if configured and configured.lower() != "auto":
            return {"entity_id": configured, "source": "configured", "candidates": []}
        try:
            candidates = self.discover_calendar_entities()
        except Exception as exc:
            return {"entity_id": None, "source": "auto", "candidates": [], "error": str(exc)}
        selected = candidates[0]["entity_id"] if candidates else None
        return {"entity_id": selected, "source": "auto", "candidates": candidates}

    def discover_calendar_entities(self) -> list[dict[str, Any]]:
        calendars = self._calendar_entities()
        if not calendars:
            return []
        keywords = [str(item).lower() for item in self.config().get("calendar_keywords", DEFAULT_CALENDAR_KEYWORDS)]
        now = datetime.now(timezone.utc)
        start = now.isoformat(timespec="seconds")
        end = (now + timedelta(days=370)).isoformat(timespec="seconds")
        ranked: list[dict[str, Any]] = []
        for calendar in calendars:
            entity_id = str(calendar.get("entity_id") or "")
            name = str(calendar.get("name") or calendar.get("friendly_name") or "")
            haystack = f"{entity_id} {name}".lower()
            score = self._keyword_score(haystack, keywords) * 10
            matched_events: list[dict[str, Any]] = []
            if score == 0:
                try:
                    events = self._calendar_events(entity_id, start, end)
                except Exception:
                    events = []
                matched_events = self._matching_calendar_events(events, keywords)
                score += len(matched_events) * 5
                if not matched_events and events:
                    score += min(len(events), 3)
            ranked.append({
                "entity_id": entity_id,
                "name": name or entity_id,
                "score": score,
                "matched_events": len(matched_events),
            })
        ranked.sort(key=lambda item: (int(item["score"]), str(item["entity_id"])), reverse=True)
        return [item for item in ranked if int(item["score"]) > 0] or ranked

    def calendar_vacation_period(self, entity_id: str | None, calendar: dict[str, Any] | None = None) -> dict[str, Any] | None:
        if not entity_id:
            return None
        keywords = [str(item).lower() for item in self.config().get("calendar_keywords", DEFAULT_CALENDAR_KEYWORDS)]
        now = datetime.now(timezone.utc)
        start = (now - timedelta(days=30)).isoformat(timespec="seconds")
        end = (now + timedelta(days=370)).isoformat(timespec="seconds")
        try:
            events = self._calendar_events(entity_id, start, end)
        except Exception as exc:
            logger.info("Vacation calendar events could not be read from %s: %s", entity_id, exc)
            return None
        calendar_name = str((calendar or {}).get("name") or entity_id).lower()
        calendar_is_dedicated = self._keyword_score(f"{entity_id} {calendar_name}", keywords) > 0
        candidates = events if calendar_is_dedicated else self._matching_calendar_events(events, keywords)
        periods = [self._period_from_calendar_event(entity_id, event) for event in candidates]
        periods = [item for item in periods if item]
        if not periods:
            return None
        current = [
            item for item in periods
            if item["_start_dt"] <= now <= item["_end_dt"]
        ]
        upcoming = [
            item for item in periods
            if item["_end_dt"] >= now
        ]
        selected = sorted(current or upcoming or periods, key=lambda item: item["_start_dt"])[0]
        selected.pop("_start_dt", None)
        selected.pop("_end_dt", None)
        return selected

    def db_path(self) -> Path:
        config = load_agent_section("vacation")
        return resolve_api_path(config.get("database_path"), "data/vacation/vacation.db")

    def log_path(self) -> Path:
        config = load_agent_section("vacation")
        return resolve_api_path(config.get("log_path"), "logs/vacation.log")

    def _connect(self) -> sqlite3.Connection:
        path = self.db_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path)
        connection.row_factory = sqlite3.Row
        self._ensure_schema(connection)
        return connection

    def _ensure_schema(self, connection: sqlite3.Connection | None = None) -> None:
        close_connection = connection is None
        db = connection
        if db is None:
            path = self.db_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            db = sqlite3.connect(path)
            db.row_factory = sqlite3.Row
        try:
            db.execute(
                """
                create table if not exists vacation_periods (
                    id integer primary key autoincrement,
                    start_date text,
                    end_date text,
                    source text,
                    active integer not null default 0,
                    payload_json text not null default '{}',
                    created_at text not null
                )
                """
            )
            db.execute(
                """
                create table if not exists vacation_events (
                    id integer primary key autoincrement,
                    event_type text not null,
                    severity text not null default 'info',
                    message text not null default '',
                    payload_json text not null default '{}',
                    created_at text not null
                )
                """
            )
            db.execute(
                """
                create table if not exists vacation_reminders (
                    id integer primary key autoincrement,
                    reminder_type text,
                    title text,
                    message text,
                    severity text not null default 'info',
                    status text not null default 'open',
                    due_at text,
                    created_at text not null
                )
                """
            )
            db.execute(
                """
                create table if not exists presence_profiles (
                    id integer primary key autoincrement,
                    room text,
                    weekday integer,
                    avg_on_time text,
                    avg_off_time text,
                    confidence real,
                    updated_at text not null
                )
                """
            )
            self._ensure_column(db, "vacation_periods", "source", "text")
            self._ensure_column(db, "vacation_periods", "payload_json", "text not null default '{}'")
            self._ensure_column(db, "vacation_periods", "active", "integer not null default 0")
            self._ensure_column(db, "vacation_reminders", "severity", "text not null default 'info'")
            db.execute("create index if not exists idx_vacation_periods_active on vacation_periods(active, start_date)")
            db.execute("create index if not exists idx_vacation_periods_source_dates on vacation_periods(source, start_date, end_date)")
            db.execute("create index if not exists idx_vacation_events_created on vacation_events(created_at)")
            db.execute("create index if not exists idx_vacation_reminders_status_due on vacation_reminders(status, due_at)")
            db.execute("create index if not exists idx_presence_profiles_room_weekday on presence_profiles(room, weekday)")
            db.commit()
        finally:
            if close_connection and db is not None:
                db.close()

    def _active_period(self) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "select * from vacation_periods where active = 1 order by created_at desc, id desc limit 1"
            ).fetchone()
        return self._decode_period(dict(row)) if row else None

    def _summary_counts(self) -> dict[str, int]:
        with self._connect() as connection:
            reminders = connection.execute("select count(*) from vacation_reminders").fetchone()[0]
            events = connection.execute("select count(*) from vacation_events").fetchone()[0]
            profiles = connection.execute("select count(*) from presence_profiles").fetchone()[0]
        return {"reminders": int(reminders), "events": int(events), "profiles": int(profiles)}

    def _decode_event(self, row: dict[str, Any]) -> dict[str, Any]:
        try:
            row["payload"] = json.loads(row.pop("payload_json", "{}") or "{}")
        except (TypeError, json.JSONDecodeError):
            row["payload"] = {}
        return row

    def _decode_period(self, row: dict[str, Any]) -> dict[str, Any]:
        try:
            row["payload"] = json.loads(row.get("payload_json", "{}") or "{}")
        except (TypeError, json.JSONDecodeError):
            row["payload"] = {}
        return row

    def _ensure_column(self, db: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        columns = {row[1] for row in db.execute(f"pragma table_info({table})").fetchall()}
        if column not in columns:
            db.execute(f"alter table {table} add column {column} {definition}")

    def _save_reminder(
        self,
        reminder_type: str,
        title: str,
        message: str,
        severity: str = "info",
        due_at: str | None = None,
        status: str = "open",
    ) -> dict[str, Any]:
        severity = severity if severity in {"info", "warning", "critical"} else "info"
        with self._connect() as connection:
            existing = connection.execute(
                """
                select * from vacation_reminders
                where status = 'open'
                  and reminder_type = ?
                  and title = ?
                  and message = ?
                order by id desc limit 1
                """,
                (reminder_type, title, message),
            ).fetchone()
            if existing:
                row = existing
            else:
                cursor = connection.execute(
                    """
                    insert into vacation_reminders (reminder_type, title, message, severity, status, due_at, created_at)
                    values (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (reminder_type, title, message, severity, status, due_at, utc_now()),
                )
                connection.commit()
                row = connection.execute("select * from vacation_reminders where id = ?", (cursor.lastrowid,)).fetchone()
        return dict(row)

    def _message_from_reminder(self, reminder: dict[str, Any]) -> None:
        try:
            MessagingService().create_message(
                source="vacation",
                category="vacation",
                severity=str(reminder.get("severity") or "info"),
                title=str(reminder.get("title") or "Vacation Reminder"),
                message=str(reminder.get("message") or ""),
                payload={"reminder_id": reminder.get("id"), "reminder_type": reminder.get("reminder_type")},
            )
        except Exception:
            logger.exception("Vacation reminder could not be written to MessagingService.")

    def _reminder_candidates(self, states: list[dict[str, Any]], vacation_mode: bool, period: dict[str, Any], pre_departure: bool = False) -> list[dict[str, Any]]:
        windows: list[str] = []
        doors: list[str] = []
        batteries: list[str] = []
        waste_items: list[tuple[str, str]] = []
        lights_on = False
        internet_problem = False
        safety_problem = False
        mailbox = False

        for state in states:
            entity_id = str(state.get("entity_id") or "")
            name = self._friendly_name(state)
            value = str(state.get("state") or "").lower()
            attributes = state.get("attributes") or {}
            device_class = str(attributes.get("device_class") or "").lower()

            if entity_id.startswith("light.") and value == "on" and pre_departure:
                lights_on = True
            if entity_id == "input_boolean.post_im_briefkasten" and value == "on" and (vacation_mode or pre_departure):
                mailbox = True
            if entity_id.startswith("binary_sensor.") and device_class in {"door", "window", "opening"} and value == "on" and (vacation_mode or pre_departure):
                if device_class == "door":
                    doors.append(self._room_from_state(state))
                else:
                    windows.append(self._room_from_state(state))
            if value in {"unavailable", "unknown"} and not entity_id.startswith(("weather.", "calendar.")):
                if self._looks_like_internet_state(state):
                    internet_problem = True
                else:
                    safety_problem = True
            battery_value = self._battery_value(state)
            if battery_value is not None and battery_value <= 20:
                batteries.append(name)
            if self._looks_like_waste_state(state) and period.get("start_date") and period.get("end_date"):
                waste_date = self._date_only(state.get("state"))
                if waste_date and self._date_in_range(waste_date, period.get("start_date"), period.get("end_date")):
                    waste_items.append((self._waste_label(name), waste_date))

        candidates: list[dict[str, Any]] = []
        if waste_items:
            label, due_at = sorted(waste_items, key=lambda item: item[1])[0]
            candidates.append({
                "reminder_type": "waste",
                "title": "Müllabfuhr",
                "message": f"{label} {self._relative_day_text(due_at)}. Vor Urlaub bitte bereitstellen oder Nachbarn informieren.",
                "severity": "warning",
                "due_at": due_at,
            })
        if windows:
            candidates.append({
                "reminder_type": "windows",
                "title": "Fenster offen",
                "message": "Fenster sind noch offen. Bitte vor der Abreise schließen.",
                "severity": "critical",
            })
        if doors:
            candidates.append({
                "reminder_type": "doors",
                "title": "Tür offen",
                "message": "Türen sind noch offen. Bitte vor der Abreise schließen.",
                "severity": "critical",
            })
        if lights_on:
            candidates.append({
                "reminder_type": "lights",
                "title": "Lichter prüfen",
                "message": "Lichter sind noch an. Bitte vor der Abreise ausschalten.",
                "severity": "warning",
            })
        if mailbox:
            candidates.append({
                "reminder_type": "mailbox",
                "title": "Briefkasten prüfen",
                "message": "Der Briefkasten ist als voll markiert. Bitte vor dem Urlaub leeren oder Leerung organisieren.",
                "severity": "warning",
            })
        if internet_problem:
            candidates.append({
                "reminder_type": "internet",
                "title": "Internetproblem erkannt",
                "message": "Die Internetverbindung war zuletzt gestört. Bitte Router und Fernzugriff vor dem Urlaub prüfen.",
                "severity": "critical",
            })
        if batteries:
            candidates.append({
                "reminder_type": "batteries",
                "title": "Batterien kritisch",
                "message": "Folgende Batterien sollten vor dem Urlaub ersetzt oder geladen werden:\n" + self._bullet_list(batteries),
                "severity": "warning",
            })
        if safety_problem:
            candidates.append({
                "reminder_type": "security",
                "title": "Sicherheitsprüfung empfohlen",
                "message": "Ein Teil der Hausüberwachung war zuletzt nicht zuverlässig erreichbar. Bitte Sicherheit, Sensoren und Fernzugriff vor dem Urlaub prüfen.",
                "severity": "warning",
            })
        return candidates

    def _waste_reminders_from_service(self, period: dict[str, Any], pre_departure: bool = False) -> list[dict[str, Any]]:
        if not pre_departure and not (period.get("start_date") and period.get("end_date")):
            return []
        try:
            waste = WasteService().status()
        except Exception:
            return []
        if not waste.get("ok"):
            return []
        reminders: list[dict[str, Any]] = []
        seen_dates: set[tuple[str, str]] = set()
        waste_items = list(waste.get("items", []))
        if pre_departure and isinstance(waste.get("next"), dict):
            waste_items.insert(0, waste["next"])
        for item in waste_items:
            days_until = item.get("days_until")
            date_value = self._date_only(item.get("date"))
            in_period = bool(date_value and period.get("start_date") and period.get("end_date") and self._date_in_range(date_value, period.get("start_date"), period.get("end_date")))
            before_departure = isinstance(days_until, int) and 0 <= days_until <= max(1, self.config()["pre_departure_days"])
            if not in_period and not before_departure and not pre_departure:
                continue
            waste_type = self._waste_label(str(item.get("type") or "Müll"))
            key = (waste_type, date_value or "")
            if key in seen_dates:
                continue
            seen_dates.add(key)
            reminders.append({
                "reminder_type": "waste",
                "title": "Müllabfuhr",
                "message": f"{waste_type} {self._relative_day_text(date_value or '')}. Vor Urlaub bitte bereitstellen oder Nachbarn informieren.",
                "severity": "warning",
                "due_at": date_value,
            })
        return reminders

    def _close_generated_reminders(self) -> None:
        generated_types = (
            "homeassistant",
            "offline",
            "security",
            "internet",
            "windows",
            "doors",
            "mailbox",
            "batteries",
            "battery",
            "waste",
            "lights",
        )
        placeholders = ",".join("?" for _ in generated_types)
        with self._connect() as connection:
            connection.execute(
                f"update vacation_reminders set status = 'resolved' where status = 'open' and reminder_type in ({placeholders})",
                generated_types,
            )
            connection.commit()

    def _battery_value(self, state: dict[str, Any]) -> float | None:
        entity_id = str(state.get("entity_id") or "").lower()
        attributes = state.get("attributes") or {}
        device_class = str(attributes.get("device_class") or "").lower()
        if "battery" not in entity_id and device_class != "battery":
            return None
        try:
            return float(state.get("state"))
        except (TypeError, ValueError):
            return 0.0 if str(state.get("state") or "").lower() == "low" else None

    def _looks_like_waste_state(self, state: dict[str, Any]) -> bool:
        text = f"{state.get('entity_id', '')} {(state.get('attributes') or {}).get('friendly_name', '')}".lower()
        return any(token in text for token in ("waste", "muell", "müll", "abfall", "tonne"))

    def _looks_like_internet_state(self, state: dict[str, Any]) -> bool:
        text = f"{state.get('entity_id', '')} {(state.get('attributes') or {}).get('friendly_name', '')}".lower()
        return any(token in text for token in ("internet", "wan", "router", "fritz", "ping", "connectivity", "network", "online"))

    def _friendly_name(self, state: dict[str, Any]) -> str:
        attributes = state.get("attributes") or {}
        name = str(attributes.get("friendly_name") or "").strip()
        if name:
            return name
        entity_id = str(state.get("entity_id") or "")
        slug = entity_id.split(".", 1)[-1]
        return slug.replace("_", " ").replace("-", " ").strip().title() or "Gerät"

    def _waste_label(self, name: str) -> str:
        text = name.lower()
        if "gelb" in text:
            return "Gelbe Tonne"
        if "bio" in text:
            return "Biotonne"
        if "papier" in text or "blau" in text:
            return "Papiertonne"
        if "rest" in text:
            return "Restmüll"
        return "Müllabfuhr"

    def _relative_day_text(self, value: str) -> str:
        try:
            date_value = datetime.fromisoformat(value).date()
        except ValueError:
            return f"am {value}"
        today = datetime.now(timezone.utc).date()
        delta = (date_value - today).days
        if delta == 0:
            return "heute"
        if delta == 1:
            return "in 1 Tag"
        if delta > 1:
            return f"in {delta} Tagen"
        return f"vor {abs(delta)} Tagen"

    def _bullet_list(self, values: list[str]) -> str:
        unique = sorted({value for value in values if value})
        return "\n".join(f"- {value}" for value in unique)

    def _is_pre_departure_window(self, period: dict[str, Any]) -> bool:
        start_value = self._date_only(period.get("start_date"))
        if not start_value:
            return False
        try:
            start_date = datetime.fromisoformat(start_value).date()
        except ValueError:
            return False
        today = datetime.now(timezone.utc).date()
        days = (start_date - today).days
        return 0 <= days <= self.config()["pre_departure_days"]

    def _notification_already_sent(self, tag: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                """
                select id from vacation_events
                where event_type = 'pre_departure_notification_sent'
                  and payload_json like ?
                order by id desc limit 1
                """,
                (f"%{tag}%",),
            ).fetchone()
        return row is not None

    def _single_line(self, value: Any) -> str:
        return " ".join(str(value or "").split())

    def _push_text_for_reminder(self, reminder: dict[str, Any]) -> str:
        reminder_type = str(reminder.get("reminder_type") or "")
        message = self._single_line(reminder.get("message"))
        if reminder_type == "waste":
            return message
        if reminder_type == "windows":
            return "Fenster sind noch offen. Bitte vor der Abreise schließen."
        if reminder_type == "doors":
            return "Türen sind noch offen. Bitte vor der Abreise schließen."
        if reminder_type == "lights":
            return "Lichter sind noch an. Bitte vor der Abreise ausschalten."
        if reminder_type == "mailbox":
            return "Briefkasten bitte vor der Abreise leeren oder Leerung organisieren."
        if reminder_type == "batteries":
            return "Batterien bitte vor der Abreise prüfen."
        return message

    def _room_from_state(self, state: dict[str, Any]) -> str:
        attributes = state.get("attributes") or {}
        for key in ("area", "area_id", "room", "room_name"):
            value = attributes.get(key)
            if value:
                return str(value).replace("_", " ").title()
        entity_id = str(state.get("entity_id") or "")
        slug = entity_id.split(".", 1)[-1]
        return (slug.split("_", 1)[0] or "Haus").replace("-", " ").title()

    def _date_only(self, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, dict):
            value = value.get("dateTime") or value.get("date")
        match = str(value).strip()[:10]
        if len(match) == 10 and match[4] == "-" and match[7] == "-":
            return match
        return None

    def _date_in_range(self, value: str, start: str | None, end: str | None) -> bool:
        if not start or not end:
            return False
        return start <= value <= end

    def _duration_days(self, start: str | None, end: str | None) -> int | None:
        start_value = self._date_only(start)
        end_value = self._date_only(end)
        if not start_value or not end_value:
            return None
        try:
            start_date = datetime.fromisoformat(start_value).date()
            end_date = datetime.fromisoformat(end_value).date()
        except ValueError:
            return None
        return max(1, (end_date - start_date).days + 1)

    def _calendar_entities(self) -> list[dict[str, Any]]:
        try:
            calendars = self._ha().get_calendars()
            if isinstance(calendars, list) and calendars:
                return [
                    {
                        "entity_id": str(item.get("entity_id") or ""),
                        "name": str(item.get("name") or item.get("friendly_name") or ""),
                    }
                    for item in calendars
                    if isinstance(item, dict) and str(item.get("entity_id") or "").startswith("calendar.")
                ]
        except Exception:
            pass
        states = self._ha().get_states()
        return [
            {
                "entity_id": str(item.get("entity_id") or ""),
                "name": str((item.get("attributes") or {}).get("friendly_name") or ""),
            }
            for item in states
            if isinstance(item, dict) and str(item.get("entity_id") or "").startswith("calendar.")
        ]

    def _calendar_events(self, entity_id: str, start: str, end: str) -> list[dict[str, Any]]:
        raw = self._ha().get_calendar_events(entity_id, start, end)
        if isinstance(raw, dict):
            raw = raw.get("events", [])
        return [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []

    def _keyword_score(self, haystack: str, keywords: list[str]) -> int:
        return sum(1 for keyword in keywords if keyword and keyword in haystack)

    def _matching_calendar_events(self, events: list[Any], keywords: list[str]) -> list[dict[str, Any]]:
        matches: list[dict[str, Any]] = []
        for event in events:
            if not isinstance(event, dict):
                continue
            summary = str(event.get("summary") or event.get("message") or event.get("description") or "").lower()
            if self._keyword_score(summary, keywords):
                matches.append(event)
        return matches

    def _period_from_calendar_event(self, entity_id: str, event: dict[str, Any]) -> dict[str, Any] | None:
        start_raw = event.get("start")
        end_raw = event.get("end")
        start_dt = self._parse_calendar_datetime(start_raw)
        end_dt = self._parse_calendar_datetime(end_raw)
        if not start_dt or not end_dt:
            return None
        start_date = start_dt.date().isoformat()
        end_date_dt = end_dt.date()
        if self._is_date_only(start_raw) and self._is_date_only(end_raw) and end_date_dt > start_dt.date():
            end_date_dt = end_date_dt - timedelta(days=1)
        return {
            "start_date": start_date,
            "end_date": end_date_dt.isoformat(),
            "source": "homeassistant_calendar",
            "calendar_entity": entity_id,
            "title": str(event.get("summary") or event.get("message") or "Urlaub"),
            "_start_dt": start_dt,
            "_end_dt": end_dt,
        }

    def _parse_calendar_datetime(self, value: Any) -> datetime | None:
        if isinstance(value, dict):
            value = value.get("dateTime") or value.get("date")
        if not value:
            return None
        text = str(value).strip()
        try:
            if len(text) == 10 and text[4] == "-" and text[7] == "-":
                return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None

    def _is_date_only(self, value: Any) -> bool:
        if isinstance(value, dict):
            value = value.get("date")
        text = str(value or "").strip()
        return len(text) == 10 and text[4] == "-" and text[7] == "-"

    def _bool_config(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return True
        return str(value).strip().lower() not in {"0", "false", "no", "off", "disabled"}

    def _ha(self) -> HomeAssistantClient:
        if self._ha_client is None:
            self._ha_client = HomeAssistantClient()
        return self._ha_client

    def _log(self, message: str) -> None:
        path = self.log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"[{timestamp}] {message}\n")

    def _write_config(self, **updates: Any) -> None:
        path = AGENTS_DIR / "vacation" / "config.yaml"
        data: dict[str, Any] = {}
        if path.exists():
            with path.open("r", encoding="utf-8") as handle:
                loaded = yaml.safe_load(handle) or {}
                data = loaded if isinstance(loaded, dict) else {}
        section = data.get("vacation")
        if not isinstance(section, dict):
            section = {}
        section.update(updates)
        data["vacation"] = section
        with path.open("w", encoding="utf-8") as handle:
            yaml.safe_dump(data, handle, allow_unicode=True, sort_keys=False)

    def _schedule_times(self, value: Any) -> list[str]:
        values = value if isinstance(value, list) else ["07:30", "20:30"]
        result: list[str] = []
        for item in values:
            text = str(item or "").strip()
            if len(text) >= 5 and text[2] == ":":
                result.append(text[:5])
        return result or ["07:30", "20:30"]

    def _time_due(self, now: datetime, schedule_time: str) -> bool:
        try:
            hour, minute = [int(part) for part in schedule_time.split(":", 1)]
        except ValueError:
            return False
        return now.hour == hour and now.minute == minute
