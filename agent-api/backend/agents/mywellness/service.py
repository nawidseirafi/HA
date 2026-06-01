import json
import os
import re
import sqlite3
import subprocess
import sys
import threading
import time as time_module
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
import httpx
from fastapi import HTTPException
from backend.config import load_agent_section, resolve_api_path
from backend.paths import PROJECT_DIR, API_DIR, AGENTS_DIR

AGENT_SCRIPT = AGENTS_DIR / "mywellness" / "mywellness.py"
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from .store import delete_prepared_courses, list_prepared_courses, replace_live_courses, save_booking_history, save_course_history

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


def resolve_secret(value: Any, env_values: dict[str, str]) -> str:
    if value is None:
        return ""
    text = str(value)
    resolved = os.getenv(text) or env_values.get(text) or os.getenv(text.upper()) or env_values.get(text.upper())
    if resolved:
        return resolved
    if re.fullmatch(r"[A-Z0-9_]+", text):
        return ""
    return text


class MyWellnessService:
    def __init__(self) -> None:
        self.process: Optional[subprocess.Popen[str]] = None
        self.lock = threading.Lock()
        self.run_lock = threading.Lock()
        self.scheduler_stop = threading.Event()
        self.scheduler_thread: Optional[threading.Thread] = None
        self._state: dict[str, Any] = self._default_status()
        self._ensure_schema()
        self._courses_cache: Optional[list[dict[str, Any]]] = None
        self._courses_cache_time: Optional[float] = None
        self._cache_ttl = 0  # Cache deaktiviert

    def status(self) -> dict[str, Any]:
        settings = self._settings()
        state = self._read_status()
        running = self._is_running()
        state["is_running"] = running
        state["current_status"] = "running" if running else state.get("current_status", "idle")
        if not running and state.get("current_status") == "error" and not state.get("last_error"):
            state["current_status"] = "idle"
        state["enabled"] = bool(settings["enabled"])
        state["prepare_enabled"] = bool(settings["prepare_enabled"])
        state["booking_enabled"] = bool(settings["booking_enabled"])
        state["health_sync_enabled"] = bool(settings["health_sync_enabled"])
        state["last_prepare_run"] = settings["last_prepare_run"]
        state["last_booking_run"] = settings["last_booking_run"]
        state["last_health_sync_run"] = settings["last_health_sync_run"]
        state["last_status"] = settings["last_status"]
        state["prepare_time"] = settings["prepare_time"]
        state["booking_time"] = settings["booking_time"]
        state["health_sync_time"] = settings["health_sync_time"]
        state["days"] = settings["days"]
        state["desired_courses"] = settings["desired_courses"]
        state["last_error"] = settings["last_error"] or state.get("last_error")
        state["updated_at"] = settings["updated_at"]
        next_scheduled = self._next_scheduled() if state.get("enabled", True) else None
        state["next_scheduled_run"] = next_scheduled["run_at"] if next_scheduled else None
        state["next_scheduled_action"] = next_scheduled["action_type"] if next_scheduled else None
        if not running and state.get("current_status") == "running":
            state["current_status"] = "idle"
        self._write_status(state)
        return state

    def start(self, mode: str = "prepare") -> dict[str, Any]:
        return self.run_action(mode, dry_run=False, async_run=True)

    def run_action(self, action_type: str, dry_run: bool = False, async_run: bool = False) -> dict[str, Any]:
        action_type = action_type if action_type in {"prepare", "book"} else "prepare"
        if async_run:
            return self._start_async(action_type, dry_run=dry_run)
        result = self._run_subprocess(action_type, dry_run=dry_run)
        return {"result": result, "status": self.status()}

    def _start_async(self, mode: str, dry_run: bool = False) -> dict[str, Any]:
        mode = mode if mode in {"prepare", "book"} else "prepare"
        with self.lock:
            state = self._read_status()
            settings = self._settings()
            if not settings["enabled"]:
                self._write_settings(enabled=True, last_status="enabled")
            if self._is_running():
                return self.status()
            if not AGENT_SCRIPT.exists():
                raise HTTPException(status_code=500, detail="MyWellness-Agent wurde nicht gefunden.")

            started_at = utc_now()
            state.update(
                {
                    "is_running": True,
                    "current_status": "running",
                    "last_started_at": started_at,
                    "last_mode": mode,
                    "last_error": None,
                }
            )
            self._insert_log(mode, "running", f"{mode} gestartet.")
            self._write_settings(last_status="running", last_error=None)
            self._write_status(state)

            env = os.environ.copy()
            env["PYTHONPATH"] = str(API_DIR)
            command = self._command(mode, dry_run=dry_run)
            self.process = subprocess.Popen(
                command,
                cwd=API_DIR,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            threading.Thread(target=self._watch_process, args=(self.process, mode, started_at), daemon=True).start()
        return self.status()

    def stop(self) -> dict[str, Any]:
        with self.lock:
            state = self._read_status()
            self._write_settings(enabled=False, last_status="disabled")
            state["current_status"] = "stopped"
            if self._is_running() and self.process:
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                state["last_stopped_at"] = utc_now()
            state["is_running"] = False
            self._write_status(state)
            self._insert_log("toggle", "ok", "MyWellnessAgent deaktiviert.")
        return self.status()

    def enable(self) -> dict[str, Any]:
        self._write_settings(enabled=True, last_status="enabled", last_error=None)
        self._insert_log("toggle", "ok", "MyWellnessAgent aktiviert.")
        return self.status()

    def disable(self) -> dict[str, Any]:
        return self.stop()

    def toggle(self) -> dict[str, Any]:
        return self.disable() if self._settings()["enabled"] else self.enable()

    def update_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        updates: dict[str, Any] = {}
        if "enabled" in payload:
            enabled = bool(payload["enabled"])
            updates["enabled"] = enabled
            updates["prepare_enabled"] = enabled
            updates["booking_enabled"] = enabled
            updates["health_sync_enabled"] = enabled
        if "prepare_time" in payload:
            updates["prepare_time"] = self._normalize_time_string(payload["prepare_time"], "prepare_time")
        if "booking_time" in payload:
            updates["booking_time"] = self._normalize_time_string(payload["booking_time"], "booking_time")
        if "health_sync_enabled" in payload:
            updates["health_sync_enabled"] = bool(payload["health_sync_enabled"])
        if "health_sync_time" in payload:
            updates["health_sync_time"] = self._normalize_time_string(payload["health_sync_time"], "health_sync_time")
        if "days" in payload:
            days = int(payload["days"])
            if days < 0 or days > 14:
                raise HTTPException(status_code=400, detail="days muss zwischen 0 und 14 liegen.")
            updates["days"] = days
        if "desired_courses" in payload:
            courses = payload["desired_courses"]
            if not isinstance(courses, list):
                raise HTTPException(status_code=400, detail="desired_courses muss eine Liste sein.")
            cleaned = [str(course).strip() for course in courses if str(course).strip()]
            updates["desired_courses"] = cleaned
        if updates:
            self._write_settings(**updates, last_status="configured", last_error=None)
            self._insert_log("settings", "ok", "MyWellness Einstellungen aktualisiert.")
        return self.status()

    def logs(self, limit: int = 200) -> dict[str, Any]:
        limit = min(max(limit, 1), 1000)
        db_logs = self._logs(limit=limit)
        lines: list[str] = []
        log_file = self.get_log_path()
        if log_file.exists():
            lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]
        state = self._read_status()
        if state.get("last_output"):
            lines.extend(str(state["last_output"]).splitlines()[-40:])
        return {"items": db_logs, "logs": lines[-limit:]}

    def courses(self) -> dict[str, Any]:
        state = self._read_status()
        courses = self._courses_from_cache()
        state["available_courses"] = courses
        state["last_courses_refresh"] = utc_now()
        self._write_status(state)
        return {"courses": courses}

    def bookings(self) -> dict[str, Any]:
        state = self._read_status()
        try:
            courses = self._fetch_courses()
            state["current_bookings"] = self._bookings_from_courses(courses)
            state["last_bookings_refresh"] = utc_now()
            state["last_error"] = None
            self._write_status(state)
            return {"bookings": self._bookings_from_courses(courses)}
        except Exception as exc:
            state["last_error"] = str(exc)
            self._write_status(state)
            bookings = state.get("current_bookings") or []
            return {"bookings": bookings or self._bookings_from_logs(), "error": str(exc)}

    def upcoming_courses(self) -> dict[str, Any]:
        state = self._read_status()
        try:
            # Zuerst aus Datenbank-Cache lesen
            cached_courses = self._courses_from_db_cache()
            if cached_courses:
                courses = self._filter_upcoming(cached_courses)
                state["upcoming_courses"] = courses
                state["current_bookings"] = self._bookings_from_courses(courses)
                state["last_upcoming_refresh"] = utc_now()
                state["last_error"] = None
                self._write_status(state)
                return {"courses": courses}

            # Fallback: API laden
            courses = self._upcoming_courses()
            state["upcoming_courses"] = courses
            state["current_bookings"] = self._bookings_from_courses(courses)
            state["last_upcoming_refresh"] = utc_now()
            state["last_error"] = None
            self._write_status(state)
            return {"courses": courses}
        except Exception as exc:
            message = f"Kurse konnten nicht geladen werden: {exc}"
            self._agent_log(message)
            state["last_error"] = message
            self._write_status(state)
            return {"courses": state.get("upcoming_courses", []), "error": message}

    def book_course(self, course_id: str) -> dict[str, Any]:
        return self._change_booking(course_id=course_id, action="book")

    def cancel_course(self, course_id: str) -> dict[str, Any]:
        return self._change_booking(course_id=course_id, action="cancel")

    def _watch_process(self, process: subprocess.Popen[str], mode: str, started_at: str) -> None:
        start_time = time_module.monotonic()
        output, _ = process.communicate()
        state = self._read_status()
        has_error = process.returncode not in (0, None) or self._output_has_error(output)
        duration = time_module.monotonic() - start_time
        state["is_running"] = False
        state["last_finished_at"] = utc_now()
        state["last_output"] = output[-8000:] if output else ""
        state["current_status"] = "error" if has_error else "ok"
        state["last_error"] = self._extract_error(output) if has_error else None
        if not has_error:
            state["last_successful_run"] = utc_now()
        if mode == "book":
            bookings = self._bookings_from_courses(state.get("available_courses", []))
            state["current_bookings"] = bookings or self._bookings_from_output(output)
        status = "error" if has_error else "ok"
        message = state["last_error"] if has_error else f"{mode} abgeschlossen in {duration:.1f}s."
        self._record_action_result(mode, status, message or "", duration, started_at)
        self._write_status(state)

    def _run_subprocess(self, action_type: str, dry_run: bool = False) -> dict[str, Any]:
        if not self.run_lock.acquire(blocking=False):
            message = "Uebersprungen, MyWellnessAgent laeuft bereits."
            self._insert_log(action_type, "skipped", message)
            return {
                "action_type": action_type,
                "status": "skipped",
                "message": message,
                "duration_seconds": 0,
                "returncode": None,
                "dry_run": dry_run,
            }
        started_at = utc_now()
        start_time = time_module.monotonic()
        try:
            self._insert_log(action_type, "running", f"{action_type} gestartet.")
            self._write_settings(last_status="running", last_error=None)
            if dry_run:
                duration = time_module.monotonic() - start_time
                message = f"Dry Run: {action_type} wuerde ausgefuehrt."
                self._record_action_result(action_type, "ok", message, duration, started_at)
                return {
                    "action_type": action_type,
                    "status": "ok",
                    "message": message,
                    "duration_seconds": round(duration, 2),
                    "returncode": 0,
                    "dry_run": True,
                }
            if not AGENT_SCRIPT.exists():
                raise FileNotFoundError("MyWellness-Agent wurde nicht gefunden.")
            env = os.environ.copy()
            env["PYTHONPATH"] = str(API_DIR)
            result = subprocess.run(
                self._command(action_type, dry_run=dry_run),
                cwd=API_DIR,
                env=env,
                capture_output=True,
                text=True,
                timeout=300,
            )
            output = "\n".join(part for part in (result.stdout, result.stderr) if part)
            has_error = result.returncode != 0 or self._output_has_error(output)
            status = "error" if has_error else "ok"
            message = self._extract_error(output) if has_error else f"{action_type} abgeschlossen."
            duration = time_module.monotonic() - start_time
            self._record_action_result(action_type, status, message or "", duration, started_at)
            if has_error and output:
                self._agent_log(f"{action_type} Fehler: {self._extract_error(output)}")
            return {
                "action_type": action_type,
                "status": status,
                "message": message,
                "duration_seconds": round(duration, 2),
                "returncode": result.returncode,
                "dry_run": dry_run,
            }
        except Exception as exc:
            duration = time_module.monotonic() - start_time
            message = str(exc)
            self._record_action_result(action_type, "error", message, duration, started_at)
            return {
                "action_type": action_type,
                "status": "error",
                "message": message,
                "duration_seconds": round(duration, 2),
                "returncode": None,
                "dry_run": dry_run,
            }
        finally:
            self.run_lock.release()

    def start_scheduler(self) -> None:
        if self.scheduler_thread and self.scheduler_thread.is_alive():
            return
        settings = self._settings()
        if not settings["enabled"]:
            return
        self.scheduler_stop.clear()
        self.scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self.scheduler_thread.start()
        self._insert_log("scheduler", "ok", "MyWellness scheduler gestartet.")

    def stop_scheduler(self) -> None:
        self.scheduler_stop.set()

    def _scheduler_loop(self) -> None:
        last_run: dict[str, str] = {}
        while not self.scheduler_stop.is_set():
            now = datetime.now().astimezone()
            settings = self._settings()
            for action_type, run_time, enabled_key in self._scheduled_actions(now):
                run_key = f"{action_type}:{now.date().isoformat()}"
                if not settings["enabled"] or not settings[enabled_key] or run_key in last_run:
                    continue
                scheduled_at = datetime.combine(now.date(), run_time, tzinfo=now.tzinfo)
                seconds_from_schedule = (now - scheduled_at).total_seconds()
                if 0 <= seconds_from_schedule < 2:
                    last_run[run_key] = utc_now()
                    if not self._is_running():
                        target = self._run_health_sync if action_type == "health_sync" else self._run_subprocess
                        threading.Thread(target=target, args=(action_type,), daemon=True).start()
                    else:
                        self._insert_log(action_type, "skipped", "Uebersprungen, Agent laeuft bereits.")
            self.scheduler_stop.wait(1)

    def _scheduled_actions(self, now: datetime) -> list[tuple[str, time, str]]:
        settings = self._settings()
        prepare = self._parse_time(settings.get("prepare_time"), time(17, 0, 0))
        book = self._parse_time(settings.get("booking_time"), time(20, 59, 58))
        health_sync = self._parse_time(settings.get("health_sync_time"), time(23, 30, 0))
        return [
            ("prepare", prepare, "prepare_enabled"),
            ("book", book, "booking_enabled"),
            ("health_sync", health_sync, "health_sync_enabled"),
        ]

    def _run_health_sync(self, action_type: str = "health_sync") -> dict[str, Any]:
        if not self.run_lock.acquire(blocking=False):
            message = "Uebersprungen, MyWellnessAgent laeuft bereits."
            self._insert_log(action_type, "skipped", message)
            return {"action_type": action_type, "status": "skipped", "message": message}
        started_at = utc_now()
        start_time = time_module.monotonic()
        try:
            self._insert_log(action_type, "running", "Health-Sync gestartet.")
            from .health_service import MyWellnessHealthService

            health_service = MyWellnessHealthService()
            settings = health_service.settings()
            if not settings.get("enabled", True):
                message = "Health-Sync uebersprungen, Health-Analyse ist deaktiviert."
                duration = time_module.monotonic() - start_time
                self._record_action_result(action_type, "skipped", message, duration, started_at)
                return {"action_type": action_type, "status": "skipped", "message": message}

            result: dict[str, Any] = {}
            errors: list[str] = []
            try:
                result["homeassistant"] = health_service.import_from_ha()
            except Exception as exc:
                errors.append(f"Home Assistant: {exc}")
            try:
                result["withings"] = health_service.import_withings_metrics_from_ha()
            except Exception as exc:
                errors.append(f"Withings: {exc}")

            duration = time_module.monotonic() - start_time
            if errors:
                message = "; ".join(errors)
                self._record_action_result(action_type, "error", message, duration, started_at)
                return {"action_type": action_type, "status": "error", "message": message, "result": result}
            self._record_action_result(action_type, "ok", "Health-Sync abgeschlossen.", duration, started_at)
            return {"action_type": action_type, "status": "ok", "result": result}
        except Exception as exc:
            duration = time_module.monotonic() - start_time
            message = str(exc)
            self._record_action_result(action_type, "error", message, duration, started_at)
            self._agent_log(f"Health-Sync Fehler: {message}")
            return {"action_type": action_type, "status": "error", "message": message}
        finally:
            self.run_lock.release()

    def _command(self, action_type: str, dry_run: bool = False) -> list[str]:
        python = PROJECT_DIR / "venv" / "bin" / "python"
        command = [str(python if python.exists() else sys.executable), str(AGENT_SCRIPT), action_type]
        if dry_run:
            command.append("--dry-run")
        return command

    def _refresh_courses_state(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        courses = self._fetch_courses()
        state["available_courses"] = courses
        state["current_bookings"] = self._bookings_from_courses(courses)
        state["last_courses_refresh"] = utc_now()
        state["last_error"] = None
        self._write_status(state)
        return courses

    def _upcoming_courses(self) -> list[dict[str, Any]]:
        now = datetime.now()
        limit_day = now + timedelta(days=2)
        limit = datetime(limit_day.year, limit_day.month, limit_day.day, 23, 59, 59)
        return [
            course
            for course in self._fetch_courses()
            if self._course_datetime(course.get("startTime") or course.get("starts_at"), fallback_min=True) <= limit
        ]

    def _change_booking(self, course_id: str, action: str) -> dict[str, Any]:
        config = self._mywellness_config()
        if not config["token"] or not config["user_id"]:
            raise HTTPException(status_code=400, detail="MY_WELLNESS_TOKEN und MY_WELLNESS_USER_ID sind erforderlich.")

        courses = self._fetch_courses()
        course = next((item for item in courses if item.get("id") == course_id), None)
        if not course:
            message = f"Kurs nicht gefunden: {course_id}"
            self._agent_log(message)
            raise HTTPException(status_code=404, detail=message)
        if action == "book" and course.get("booked"):
            delete_prepared_courses(str(course.get("partitionDate") or ""), [course_id])
            return {"ok": True, "message": "Kurs ist bereits gebucht.", "course": course}
        if action == "book" and not course.get("bookable") and course.get("status") != "waitlist":
            message = f"Kurs ist nicht buchbar: {course.get('title')}"
            self._agent_log(message)
            raise HTTPException(status_code=409, detail=message)
        if action == "cancel" and not course.get("cancellable"):
            message = f"Kurs ist nicht stornierbar: {course.get('title')}"
            self._agent_log(message)
            raise HTTPException(status_code=409, detail=message)

        endpoint_action = "book" if action == "book" else "unbook"
        url = f"https://services.mywellness.com/core/calendarevent/{course_id}/{endpoint_action}?_c=de-DE"
        payload = {
            "partitionDate": course.get("partitionDate"),
            "userId": config["user_id"],
        }
        headers = {"Content-Type": "application/json", "Authorization": config["token"]}
        try:
            with httpx.Client(timeout=8) as client:
                response = client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json() if response.text else {}
        except Exception as exc:
            message = f"{'Buchung' if action == 'book' else 'Stornierung'} fehlgeschlagen: {exc}"
            self._agent_log(message)
            raise HTTPException(status_code=502, detail=message) from exc

        errors = data.get("errors") if isinstance(data, dict) else None
        if errors:
            message = f"{'Buchung' if action == 'book' else 'Stornierung'} fehlgeschlagen: {errors}"
            self._agent_log(message)
            raise HTTPException(status_code=409, detail=message)

        verb = "gebucht" if action == "book" else "storniert"
        message = f"{course.get('title')} erfolgreich {verb}."
        self._agent_log(message)
        if action == "book":
            delete_prepared_courses(str(course.get("partitionDate") or ""), [course_id])
        try:
            save_booking_history(
                booking_id=str(course.get("bookingUserStatus") or course.get("id") or ""),
                course_id=course_id,
                action="booked" if action == "book" else "cancelled",
            )
            save_course_history({**course, "status": "booked" if action == "book" else "cancelled"})
        except Exception as exc:
            self._agent_log(f"Historie konnte nicht gespeichert werden: {exc}")
        refreshed = self._upcoming_courses()
        state = self._read_status()
        state["upcoming_courses"] = refreshed
        state["current_bookings"] = self._bookings_from_courses(refreshed)
        state["last_error"] = None
        self._write_status(state)
        return {"ok": True, "message": message, "course": next((item for item in refreshed if item.get("id") == course_id), course)}

    def _fetch_courses(self, force_refresh: bool = False) -> list[dict[str, Any]]:
        # Cache-Check
        now = time_module.time()
        if not force_refresh and self._courses_cache is not None and self._courses_cache_time is not None:
            if now - self._courses_cache_time < self._cache_ttl:
                return self._courses_cache

        config = self._mywellness_config()
        if not config["token"] or not config["facility_id"]:
            raise RuntimeError("MY_WELLNESS_TOKEN und MY_WELLNESS_FACILITY_ID sind erforderlich.")

        url_template = "https://services.mywellness.com/Core/Facility/{facility_id}/SearchCalendarEvents"
        headers = {"Content-Type": "application/json", "Authorization": config["token"]}
        desired = set(config["desired_courses"])
        courses: list[dict[str, Any]] = []

        with httpx.Client(timeout=8) as client:
            for date_value in self._course_dates(config["days"]):
                url = (
                    url_template.format(facility_id=config["facility_id"])
                    + f"?_c=de-DE&dateStart={date_value}&dateLimit=0"
                )
                payload = {
                    "dateLimit": "0",
                    "dateStart": date_value,
                    "eventType": "Class",
                    "timeScope": "Custom",
                }
                response = client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
                courses.extend(self._normalize_course(item, date_value, desired) for item in self._event_items(data))

        deduped = self._dedupe_courses(courses)
        replace_live_courses(deduped)
        self._delete_booked_prepared_courses(deduped)

        # Cache aktualisieren
        self._courses_cache = deduped
        self._courses_cache_time = now

        return deduped

    def _delete_booked_prepared_courses(self, courses: list[dict[str, Any]]) -> int:
        deleted = 0
        for course in courses:
            if not course.get("booked") and not course.get("is_participant"):
                continue
            partition_date = str(course.get("partitionDate") or "")
            course_id = str(course.get("id") or "")
            if partition_date and course_id:
                deleted += delete_prepared_courses(partition_date, [course_id])
        if deleted:
            self._agent_log(f"Vorgemerkte gebuchte Kurse geloescht: {deleted}")
        return deleted

    def _normalize_course(self, item: dict[str, Any], target_date: str, desired: set[str]) -> dict[str, Any]:
        is_participant = bool(item.get("isParticipant"))
        starts_at = self._course_start_time(item, target_date)
        ends_at = self._course_end_time(item, starts_at)
        available_slots = item.get("availablePlaces")
        waiting_list = bool(item.get("bookingHasWaitingList") or item.get("isInWaitingList"))
        status = self._course_status(item, is_participant, available_slots, waiting_list)
        cancellable = self._is_cancellable(item, starts_at, is_participant)
        return {
            "id": str(item.get("id", "")),
            "title": item.get("name", "Unbekannter Kurs"),
            "studio": item.get("facilityName") or "",
            "trainer": item.get("assignedTo"),
            "startTime": starts_at,
            "endTime": ends_at,
            "availableSlots": available_slots,
            "waitingList": waiting_list,
            "booked": is_participant,
            "bookable": bool(item.get("bookingAvailable")) and status in {"available", "waitlist"},
            "cancellable": cancellable,
            "status": status,
            "category": item.get("calendarEventType") or item.get("eventTypeId"),
            "partitionDate": str(item.get("partitionDate") or target_date),
            "bookingUserStatus": item.get("bookingUserStatus"),
            "room": item.get("room"),
            "name": item.get("name", "Unbekannter Kurs"),
            "starts_at": starts_at,
            "ends_at": ends_at,
            "location": item.get("facilityName") or item.get("locationName") or item.get("roomName") or item.get("room"),
            "booking_status": status if status != "available" else ("found" if item.get("name") in desired else "available"),
            "is_desired": item.get("name") in desired,
            "is_participant": is_participant,
        }

    def _course_start_time(self, item: dict[str, Any], target_date: str) -> str:
        if item.get("startDateTime"):
            return str(item["startDateTime"])
        date_value = str(item.get("partitionDate") or item.get("dateStart") or target_date)
        hour = int(item.get("startHour") or 0)
        minute = int(item.get("startMinutes") or 0)
        if re.fullmatch(r"\d{8}", date_value):
            start = datetime(int(date_value[:4]), int(date_value[4:6]), int(date_value[6:8]), hour, minute)
            return start.isoformat(timespec="minutes")
        return date_value

    def _course_end_time(self, item: dict[str, Any], starts_at: str) -> Optional[str]:
        if item.get("endDateTime"):
            return str(item["endDateTime"])
        start = self._course_datetime(starts_at)
        if not start:
            return None
        end = start.replace(hour=int(item.get("endHour") or start.hour), minute=int(item.get("endMinutes") or start.minute))
        if end < start:
            end += timedelta(days=1)
        return end.isoformat(timespec="minutes")

    def _course_status(self, item: dict[str, Any], booked: bool, available_slots: Any, waiting_list: bool) -> str:
        if booked:
            return "booked"
        if item.get("isInWaitingList"):
            return "waitlist"
        if available_slots is not None and int(available_slots) <= 0:
            return "waitlist" if waiting_list else "full"
        if not item.get("bookingAvailable"):
            return "full"
        return "available"

    def _is_cancellable(self, item: dict[str, Any], starts_at: str, booked: bool) -> bool:
        if not booked:
            return False
        start = self._course_datetime(starts_at)
        if not start:
            return True
        minutes = int(item.get("cancellationMinutesInAdvance") or 0)
        return datetime.now() < start - timedelta(minutes=minutes)

    def _course_datetime(self, value: Any, fallback_min: bool = False) -> datetime:
        if not value:
            return datetime.min if fallback_min else datetime.max
        text = str(value)
        if re.fullmatch(r"\d{8}", text):
            return datetime(int(text[:4]), int(text[4:6]), int(text[6:8]))
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            return datetime.min if fallback_min else datetime.max

    def _event_items(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        direct_items = data.get("data", {}).get("eventItems")
        if isinstance(direct_items, list):
            return [item for item in direct_items if isinstance(item, dict)]
        items = data.get("eventItems")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
        return []

    def _dedupe_courses(self, courses: list[dict[str, Any]]) -> list[dict[str, Any]]:
        deduped: dict[str, dict[str, Any]] = {}
        for course in courses:
            key = f"{course.get('id')}:{course.get('starts_at')}"
            deduped[key] = course
        return list(deduped.values())

    def _bookings_from_courses(self, courses: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [course for course in courses if course.get("is_participant") is True]

    def _courses_from_cache(self) -> list[dict[str, Any]]:
        _, target_date = self._dates()
        return list_prepared_courses(target_date)

    def _courses_from_db_cache(self) -> list[dict[str, Any]]:
        """Lädt Kurse aus der Datenbank (live source)"""
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    """
                    select * from courses
                    where source = 'live'
                    order by start_time, title
                    """
                ).fetchall()
            return [self._course_row_to_api(row) for row in rows]
        except Exception:
            return []

    def _course_row_to_api(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "title": row["title"],
            "studio": row["studio"] or "",
            "trainer": row["trainer"],
            "startTime": row["start_time"],
            "endTime": row["end_time"],
            "availableSlots": row["available_slots"],
            "waitingList": bool(row["waiting_list"]),
            "booked": bool(row["booked"]),
            "bookable": bool(row["bookable"]),
            "cancellable": bool(row["cancellable"]),
            "status": row["status"],
            "category": row["category"],
            "partitionDate": row["partition_date"],
            "bookingUserStatus": row["booking_user_status"],
            "room": row["room"],
            "name": row["title"],
            "starts_at": row["start_time"],
            "ends_at": row["end_time"],
            "location": row["studio"],
            "booking_status": row["status"],
            "is_desired": bool(row["is_desired"]),
            "is_participant": bool(row["booked"]),
        }

    def _filter_upcoming(self, courses: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Filtert Kurse für die nächsten 48 Stunden"""
        now = datetime.now()
        limit_day = now + timedelta(days=2)
        limit = datetime(limit_day.year, limit_day.month, limit_day.day, 23, 59, 59)
        return [
            course
            for course in courses
            if self._course_datetime(course.get("startTime") or course.get("starts_at"), fallback_min=True) <= limit
        ]

    def _bookings_from_output(self, output: str) -> list[dict[str, Any]]:
        names = re.findall(r"Erfolgreich gebucht:\s*(.+)", output or "")
        booked = []
        for name in names:
            for item in re.split(r",|\n", name):
                if item.strip():
                    booked.append(self._booking_item(item.strip(), "booked"))
        if booked:
            return booked
        return self._bookings_from_logs()

    def _bookings_from_logs(self) -> list[dict[str, Any]]:
        log_file = self.get_log_path()
        if not log_file.exists():
            return []
        lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
        bookings: list[dict[str, Any]] = []
        for line in lines[-500:]:
            match = re.search(r"Erfolgreich gebucht:\s*(.+)$", line)
            if match:
                for item in re.split(r",|\n", match.group(1)):
                    if item.strip():
                        bookings.append(self._booking_item(item.strip(), "booked"))
        return bookings[-20:]

    def _booking_item(self, name: str, status: str) -> dict[str, Any]:
        return {
            "id": name,
            "title": name,
            "studio": "",
            "trainer": None,
            "startTime": None,
            "endTime": None,
            "availableSlots": None,
            "waitingList": None,
            "booked": status == "booked",
            "bookable": False,
            "cancellable": False,
            "status": status,
            "name": name,
            "starts_at": None,
            "location": None,
            "booking_status": status,
        }

    def _mywellness_config(self) -> dict[str, Any]:
        env_values = read_env_file(API_DIR / ".env")
        api_config = load_agent_section("mywellness")
        settings = self._settings()
        token = resolve_secret(api_config.get("token"), env_values)
        user_id = resolve_secret(api_config.get("user_id"), env_values)
        facility_id = resolve_secret(api_config.get("facility_id"), env_values)
        return {
            "token": token,
            "user_id": user_id,
            "facility_id": facility_id,
            "desired_courses": settings.get("desired_courses") or api_config.get("desired_courses") or ["Cross-Power", "Body Workout", "Functional Training"],
            "days": int(settings.get("days") or api_config.get("days", 2)),
        }

    def _dates(self) -> tuple[str, str]:
        days = self._mywellness_config()["days"]
        now = datetime.now()
        return now.strftime("%Y%m%d"), (now + timedelta(days=days)).strftime("%Y%m%d")

    def _course_dates(self, days: int) -> list[str]:
        today = datetime.now()
        return [(today + timedelta(days=offset)).strftime("%Y%m%d") for offset in range(max(days, 0) + 1)]

    def _agent_log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        try:
            log_file = self.get_log_path()
            log_file.parent.mkdir(parents=True, exist_ok=True)
            with log_file.open("a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] {message}\n")
        except OSError:
            pass

    def _connect(self) -> sqlite3.Connection:
        db_path = self.get_db_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(db_path)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def get_db_path() -> Path:
        api_config = load_agent_section("mywellness")
        return resolve_api_path(api_config.get("database_path"), "data/mywellness/mywellness.db")

    @staticmethod
    def get_log_path() -> Path:
        api_config = load_agent_section("mywellness")
        return resolve_api_path(api_config.get("log_path"), "logs/my_wellness.log")

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                create table if not exists mywellness_settings (
                    id integer primary key check (id = 1),
                    enabled integer not null default 1,
                    prepare_enabled integer not null default 1,
                    booking_enabled integer not null default 1,
                    health_sync_enabled integer not null default 1,
                    prepare_time text not null default '17:00:00',
                    booking_time text not null default '20:59:58',
                    health_sync_time text not null default '23:30:00',
                    days integer not null default 2,
                    desired_courses text not null default '[]',
                    last_prepare_run text,
                    last_booking_run text,
                    last_health_sync_run text,
                    last_status text not null default 'idle',
                    last_error text,
                    updated_at text not null
                )
                """
            )
            connection.execute(
                """
                create table if not exists mywellness_logs (
                    id integer primary key autoincrement,
                    action_type text not null,
                    status text not null,
                    message text not null default '',
                    duration_seconds real,
                    created_at text not null
                )
                """
            )
            existing_columns = {row["name"] for row in connection.execute("pragma table_info(mywellness_settings)").fetchall()}
            extra_columns = {
                "prepare_time": "text not null default '17:00:00'",
                "booking_time": "text not null default '20:59:58'",
                "health_sync_enabled": "integer not null default 1",
                "health_sync_time": "text not null default '23:30:00'",
                "days": "integer not null default 2",
                "desired_courses": "text not null default '[]'",
                "last_health_sync_run": "text",
            }
            for column, definition in extra_columns.items():
                if column not in existing_columns:
                    connection.execute(f"alter table mywellness_settings add column {column} {definition}")
            connection.execute(
                """
                insert or ignore into mywellness_settings
                (id, enabled, prepare_enabled, booking_enabled, health_sync_enabled, prepare_time, booking_time, health_sync_time, days, desired_courses, last_status, updated_at)
                values (1, 1, 1, 1, 1, ?, ?, ?, ?, ?, 'idle', ?)
                """,
                (
                    self._config_schedule()[0],
                    self._config_schedule()[1],
                    self._config_health_sync_time(),
                    self._config_days(),
                    json.dumps(self._config_desired_courses(), ensure_ascii=False),
                    utc_now(),
                ),
            )
            connection.execute(
                """
                update mywellness_settings
                set prepare_time = coalesce(nullif(prepare_time, ''), ?),
                    booking_time = coalesce(nullif(booking_time, ''), ?),
                    health_sync_time = coalesce(nullif(health_sync_time, ''), ?),
                    days = coalesce(days, ?),
                    desired_courses = case when desired_courses is null or desired_courses = '[]' then ? else desired_courses end
                where id = 1
                """,
                (
                    self._config_schedule()[0],
                    self._config_schedule()[1],
                    self._config_health_sync_time(),
                    self._config_days(),
                    json.dumps(self._config_desired_courses(), ensure_ascii=False),
                ),
            )
            connection.commit()

    def _settings(self) -> dict[str, Any]:
        self._ensure_schema()
        with self._connect() as connection:
            row = connection.execute("select * from mywellness_settings where id = 1").fetchone()
        if row is None:
            return {
                "enabled": True,
                "prepare_enabled": True,
                "booking_enabled": True,
                "health_sync_enabled": True,
                "prepare_time": "17:00:00",
                "booking_time": "20:59:58",
                "health_sync_time": "23:30:00",
                "days": 2,
                "desired_courses": [],
                "last_prepare_run": None,
                "last_booking_run": None,
                "last_health_sync_run": None,
                "last_status": "idle",
                "last_error": None,
                "updated_at": utc_now(),
            }
        item = dict(row)
        item["enabled"] = bool(item["enabled"])
        item["prepare_enabled"] = bool(item["prepare_enabled"])
        item["booking_enabled"] = bool(item["booking_enabled"])
        item["health_sync_enabled"] = bool(item.get("health_sync_enabled", 1))
        item["days"] = int(item.get("days") or 2)
        try:
            item["desired_courses"] = json.loads(item.get("desired_courses") or "[]")
        except json.JSONDecodeError:
            item["desired_courses"] = []
        return item

    def _write_settings(self, **values: Any) -> None:
        allowed = {
            "enabled",
            "prepare_enabled",
            "booking_enabled",
            "health_sync_enabled",
            "prepare_time",
            "booking_time",
            "health_sync_time",
            "days",
            "desired_courses",
            "last_prepare_run",
            "last_booking_run",
            "last_health_sync_run",
            "last_status",
            "last_error",
        }
        fields = [field for field in values if field in allowed]
        if not fields:
            return
        assignments = ", ".join(f"{field} = ?" for field in fields)
        params = [self._setting_value(values[field]) for field in fields]
        params.extend([utc_now(), 1])
        with self._connect() as connection:
            connection.execute(
                f"update mywellness_settings set {assignments}, updated_at = ? where id = ?",
                tuple(params),
            )
            connection.commit()

    def _setting_value(self, value: Any) -> Any:
        if isinstance(value, bool):
            return 1 if value else 0
        if isinstance(value, list):
            return json.dumps(value, ensure_ascii=False)
        return value

    def _insert_log(self, action_type: str, status: str, message: str, duration_seconds: float | None = None) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                insert into mywellness_logs (action_type, status, message, duration_seconds, created_at)
                values (?, ?, ?, ?, ?)
                """,
                (action_type, status, message[-2000:], duration_seconds, utc_now()),
            )
            connection.commit()

    def _logs(self, limit: int = 200) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "select * from mywellness_logs order by created_at desc, id desc limit ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def _record_action_result(self, action_type: str, status: str, message: str, duration: float, started_at: str) -> None:
        updates: dict[str, Any] = {
            "last_status": status,
            "last_error": message if status == "error" else None,
        }
        if action_type == "prepare":
            updates["last_prepare_run"] = started_at
        if action_type == "book":
            updates["last_booking_run"] = started_at
        if action_type == "health_sync":
            updates["last_health_sync_run"] = started_at
        self._write_settings(**updates)
        self._insert_log(action_type, status, f"{message} Laufzeit: {duration:.1f}s", duration_seconds=duration)

    def _next_scheduled_run(self) -> Optional[str]:
        next_scheduled = self._next_scheduled()
        return next_scheduled["run_at"] if next_scheduled else None

    def _next_scheduled(self) -> Optional[dict[str, str]]:
        now = datetime.now().astimezone()
        settings = self._settings()
        candidates = []
        for action_type, item, enabled_key in self._scheduled_actions(now):
            if not settings[enabled_key]:
                continue
            run_time = datetime.combine(now.date(), item, tzinfo=now.tzinfo)
            if run_time <= now:
                run_time += timedelta(days=1)
            candidates.append((run_time, action_type))
        if not candidates:
            return None
        run_at, action_type = min(candidates, key=lambda item: item[0])
        return {"run_at": run_at.isoformat(timespec="seconds"), "action_type": action_type}

    def _parse_time(self, value: Any, default: time) -> time:
        try:
            parts = [int(part) for part in str(value).split(":")]
            if len(parts) == 2:
                parts.append(0)
            return time(parts[0], parts[1], parts[2])
        except (TypeError, ValueError, IndexError):
            return default

    def _normalize_time_string(self, value: Any, field_name: str) -> str:
        parts = str(value).strip().split(":")
        if len(parts) == 2:
            parts.append("0")
        if len(parts) != 3:
            raise HTTPException(status_code=400, detail=f"{field_name} muss HH:MM oder HH:MM:SS sein.")
        try:
            hour, minute, second = [int(part) for part in parts]
            parsed = time(hour, minute, second)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"{field_name} ist ungueltig.") from exc
        return parsed.isoformat()

    def _config_schedule(self) -> list[str]:
        config = load_agent_section("mywellness")
        schedule = config.get("schedule") or ["17:00:00", "20:59:58"]
        return [
            self._normalize_time_string(schedule[0] if len(schedule) > 0 else "17:00:00", "prepare_time"),
            self._normalize_time_string(schedule[1] if len(schedule) > 1 else "20:59:58", "booking_time"),
        ]

    def _config_health_sync_time(self) -> str:
        config = load_agent_section("mywellness")
        return self._normalize_time_string(config.get("health_sync_time", "23:30:00"), "health_sync_time")

    def _config_days(self) -> int:
        config = load_agent_section("mywellness")
        return int(config.get("days", 2) or 2)

    def _config_desired_courses(self) -> list[str]:
        config = load_agent_section("mywellness")
        courses = config.get("desired_courses") or ["Cross-Power", "Body Workout", "Functional Training"]
        return [str(course).strip() for course in courses if str(course).strip()]

    def _is_running(self) -> bool:
        return self.run_lock.locked() or (self.process is not None and self.process.poll() is None)

    def _ensure_status(self) -> None:
        # legacy no-op: state lives in-memory now.
        return

    def _read_status(self) -> dict[str, Any]:
        return self._state

    def _write_status(self, state: dict[str, Any]) -> None:
        # `state` is the same dict as self._state in normal flow; rebind defensively
        # so callers that build a fresh dict also work.
        if state is not self._state:
            self._state = state

    def _default_status(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "is_running": False,
            "current_status": "idle",
            "last_successful_run": None,
            "next_scheduled_run": None,
            "last_error": None,
            "available_courses": [],
            "current_bookings": [],
            "upcoming_courses": [],
        }

    def _output_has_error(self, output: str) -> bool:
        relevant_lines = [
            line
            for line in (output or "").splitlines()
            if "Home Assistant Notification" not in line
        ]
        return bool(re.search(r"\b(Fehler|Traceback|Exception|Error)\b", "\n".join(relevant_lines), re.IGNORECASE))

    def _extract_error(self, output: str) -> Optional[str]:
        for line in reversed((output or "").splitlines()):
            cleaned = line.strip()
            if not cleaned:
                continue
            if cleaned.startswith(("File ", "Traceback ")):
                continue
            if self._output_has_error(cleaned):
                return cleaned[-500:]
        for line in reversed((output or "").splitlines()):
            cleaned = line.strip()
            if cleaned:
                return cleaned[-500:]
        return None
