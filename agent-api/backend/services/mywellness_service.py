import json
import os
import re
import subprocess
import sys
import threading
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import httpx
import yaml
from fastapi import HTTPException


BASE_DIR = Path(__file__).resolve().parents[2]
PROJECT_DIR = BASE_DIR.parent
AI_AGENT_DIR = PROJECT_DIR / "ai-agent"
AGENT_SCRIPT = AI_AGENT_DIR / "agents" / "mywellness.py"
AGENT_LOG_FILE = AI_AGENT_DIR / "agents" / "mywellness.log"
AGENT_CACHE_FILE = AI_AGENT_DIR / "agents" / "mywellness_cache.json"
CONFIG_PATH = BASE_DIR / "config.yaml"
AI_CONFIG_PATH = AI_AGENT_DIR / "config.yaml"
STATUS_FILE = BASE_DIR / "backend" / "storage" / "mywellness_status.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as config_file:
        return yaml.safe_load(config_file) or {}


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
        STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
        self.process: Optional[subprocess.Popen[str]] = None
        self.lock = threading.Lock()
        self._ensure_status()

    def status(self) -> dict[str, Any]:
        state = self._read_status()
        running = self._is_running()
        state["is_running"] = running
        state["current_status"] = "running" if running else state.get("current_status", "idle")
        state["next_scheduled_run"] = self._next_scheduled_run() if state.get("enabled", True) else None
        if not running and state.get("current_status") == "running":
            state["current_status"] = "idle"
        self._write_status(state)
        return state

    def start(self, mode: str = "prepare") -> dict[str, Any]:
        mode = mode if mode in {"prepare", "book"} else "prepare"
        with self.lock:
            state = self._read_status()
            if not state.get("enabled", True):
                state["enabled"] = True
            if self._is_running():
                return self.status()
            if not AGENT_SCRIPT.exists():
                raise HTTPException(status_code=500, detail="MyWellness-Agent wurde nicht gefunden.")

            state.update(
                {
                    "is_running": True,
                    "current_status": "running",
                    "last_started_at": utc_now(),
                    "last_mode": mode,
                    "last_error": None,
                }
            )
            self._write_status(state)

            env = os.environ.copy()
            env["PYTHONPATH"] = str(AI_AGENT_DIR)
            self.process = subprocess.Popen(
                [sys.executable, str(AGENT_SCRIPT), mode],
                cwd=AI_AGENT_DIR,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            threading.Thread(target=self._watch_process, args=(self.process, mode), daemon=True).start()
        return self.status()

    def stop(self) -> dict[str, Any]:
        with self.lock:
            state = self._read_status()
            state["enabled"] = False
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
        return self.status()

    def logs(self, limit: int = 200) -> dict[str, Any]:
        limit = min(max(limit, 1), 1000)
        lines: list[str] = []
        if AGENT_LOG_FILE.exists():
            lines = AGENT_LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]
        state = self._read_status()
        if state.get("last_output"):
            lines.extend(str(state["last_output"]).splitlines()[-40:])
        return {"logs": lines[-limit:]}

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

    def _watch_process(self, process: subprocess.Popen[str], mode: str) -> None:
        output, _ = process.communicate()
        state = self._read_status()
        has_error = process.returncode not in (0, None) or self._output_has_error(output)
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
        self._write_status(state)

    def _refresh_courses_state(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        courses = self._fetch_courses()
        state["available_courses"] = courses
        state["current_bookings"] = self._bookings_from_courses(courses)
        state["last_courses_refresh"] = utc_now()
        state["last_error"] = None
        self._write_status(state)
        return courses

    def _fetch_courses(self) -> list[dict[str, Any]]:
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

        return self._dedupe_courses(courses)

    def _normalize_course(self, item: dict[str, Any], target_date: str, desired: set[str]) -> dict[str, Any]:
        is_participant = bool(item.get("isParticipant"))
        starts_at = (
            item.get("startDateTime")
            or item.get("dateStart")
            or item.get("startTime")
            or item.get("start")
            or target_date
        )
        return {
            "id": str(item.get("id", "")),
            "name": item.get("name", "Unbekannter Kurs"),
            "starts_at": starts_at,
            "ends_at": item.get("endDateTime") or item.get("dateEnd") or item.get("endTime"),
            "location": item.get("facilityName") or item.get("locationName") or item.get("roomName") or item.get("room"),
            "booking_status": "booked" if is_participant else item.get("bookingStatus") or item.get("status") or ("found" if item.get("name") in desired else "available"),
            "is_desired": item.get("name") in desired,
            "is_participant": is_participant,
        }

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
        if not AGENT_CACHE_FILE.exists():
            return []
        try:
            data = json.loads(AGENT_CACHE_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
        return [
            {
                "id": str(course_id),
                "name": name,
                "starts_at": data.get("target_date"),
                "ends_at": None,
                "location": None,
                "booking_status": "cached",
                "is_desired": True,
            }
            for name, course_id in (data.get("course_ids") or {}).items()
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
        if not AGENT_LOG_FILE.exists():
            return []
        lines = AGENT_LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
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
            "name": name,
            "starts_at": None,
            "location": None,
            "booking_status": status,
        }

    def _mywellness_config(self) -> dict[str, Any]:
        env_values = read_env_file(AI_AGENT_DIR / ".env")
        api_config = read_yaml(CONFIG_PATH).get("agents", {}).get("mywellness", {})
        ai_config = read_yaml(AI_CONFIG_PATH).get("myWelness_agent", {})
        token = resolve_secret(api_config.get("token_env"), env_values) or resolve_secret(ai_config.get("token"), env_values)
        user_id = resolve_secret(api_config.get("user_id_env"), env_values) or resolve_secret(ai_config.get("user_id"), env_values)
        facility_id = resolve_secret(api_config.get("facility_id_env"), env_values) or resolve_secret(ai_config.get("facility_id"), env_values)
        return {
            "token": token,
            "user_id": user_id,
            "facility_id": facility_id,
            "desired_courses": api_config.get("desired_courses") or ["Cross-Power", "Body Workout", "Functional Training"],
            "days": int(api_config.get("days", 2)),
        }

    def _dates(self) -> tuple[str, str]:
        days = self._mywellness_config()["days"]
        now = datetime.now()
        return now.strftime("%Y%m%d"), (now + timedelta(days=days)).strftime("%Y%m%d")

    def _course_dates(self, days: int) -> list[str]:
        today = datetime.now()
        return [(today + timedelta(days=offset)).strftime("%Y%m%d") for offset in range(max(days, 0) + 1)]

    def _next_scheduled_run(self) -> Optional[str]:
        config = read_yaml(CONFIG_PATH).get("agents", {}).get("mywellness", {})
        schedule = config.get("schedule") or ["17:00:00", "20:59:58"]
        now = datetime.now().astimezone()
        candidates = []
        for item in schedule:
            try:
                hour, minute, second = [int(part) for part in str(item).split(":")]
                run_time = datetime.combine(now.date(), time(hour, minute, second), tzinfo=now.tzinfo)
                if run_time <= now:
                    run_time += timedelta(days=1)
                candidates.append(run_time)
            except ValueError:
                continue
        return min(candidates).isoformat(timespec="seconds") if candidates else None

    def _is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def _ensure_status(self) -> None:
        if not STATUS_FILE.exists():
            self._write_status(
                {
                    "enabled": True,
                    "is_running": False,
                    "current_status": "idle",
                    "last_successful_run": None,
                    "next_scheduled_run": None,
                    "last_error": None,
                    "available_courses": [],
                    "current_bookings": [],
                }
            )

    def _read_status(self) -> dict[str, Any]:
        self._ensure_status()
        try:
            return json.loads(STATUS_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"enabled": True, "is_running": False, "current_status": "error", "last_error": "Statusdatei ist defekt."}

    def _write_status(self, state: dict[str, Any]) -> None:
        STATUS_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    def _output_has_error(self, output: str) -> bool:
        return bool(re.search(r"\b(Fehler|Traceback|Exception|Error)\b", output or "", re.IGNORECASE))

    def _extract_error(self, output: str) -> Optional[str]:
        for line in reversed((output or "").splitlines()):
            if self._output_has_error(line):
                return line[-500:]
        return None
