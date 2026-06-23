import requests
from datetime import datetime, timedelta
import json
import time
import os
import sys
from pathlib import Path

from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
from backend.config import load_agent_runtime_config
from backend.paths import API_DIR
# =====================
# KONFIGURATION
# =====================
HA_NOTIFY_SERVICE = "notify.mobile_app_system_error_404"
DEFAULT_DESIRED_COURSES = ['Cross-Power', 'Body Workout', 'Functional Training']


# Empfehlung:
# 20:58:00 -> MODE = "prepare"
# 20:59:58 -> MODE = "book"
# MODE = "book"
# MODE = "prepare"

MODE = sys.argv[1] if len(sys.argv) > 1 else "book"
MAX_RETRIES = 30  # Reduziert: meist reichen 2-3 Versuche
RETRY_DELAY = 0.1  # Schneller Retry
REQUEST_TIMEOUT = 3  # Erhöht: externe Services brauchen manchmal länger

from backend.services.core.ha_client import HomeAssistantClient
from backend.agents.mywellness.store import (
    delete_prepared_courses,
    list_prepared_courses,
    load_agent_settings,
    prepared_course_ids,
    record_run,
    replace_prepared_courses,
    save_booking_history,
)
from backend.agents.mywellness.calendar import add_course_to_calendar

agent_settings = load_agent_settings()
desired_courses = agent_settings["desired_courses"] or DEFAULT_DESIRED_COURSES
days = int(agent_settings["days"] or 2)

def load_raw_config() -> dict:
    load_dotenv(API_DIR / ".env")
    return load_agent_runtime_config("mywellness")


def get_log_path() -> Path:
    config = load_raw_config()
    log_path = config.get("my_wellness", {}).get("log_path", "logs/my_wellness.log")
    return (API_DIR / log_path).resolve()

def resolve_config_value(value):
    text = str(value or "")
    resolved = os.getenv(text) or os.getenv(text.upper())
    if resolved:
        return resolved
    if text.isupper() and text.replace("_", "").isalnum():
        return ""
    return text

def mywellness_config() -> dict:
    config = load_raw_config().get("my_wellness", {})
    return {
        "token":resolve_config_value(config.get("token", "")),
        "user_id": resolve_config_value(config.get("user_id", "")),
        "facility_id": resolve_config_value(config.get("facility_id", "")),
        "calendar_entity": resolve_config_value(config.get("calendar_entity", "")) or os.getenv("MYWELLNESS_CALENDAR_ENTITY") or os.getenv("WALL_CALENDAR_ENTITY") or "calendar.devcal",
    }
    
headers = {
    "Content-Type": "application/json",
    "Authorization": mywellness_config().get("token", "")
}

session = requests.Session()
session.headers.update(headers)


# =====================
# LOGGING
# =====================
def log(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    line = f"[{timestamp}] {message}"
    print(line)
    log_file = get_log_path()
    log_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception as e:
        print(f"Fehler beim Schreiben der Log-Datei: {e}")

# =====================
# HOME ASSISTANT
# =====================
def send_ha_notification(title, message):
    try:
        service = HA_NOTIFY_SERVICE.replace("notify.", "")
        url = f"{ha.base_url}/api/services/notify/{service}"
        headers_ha = {
            "Authorization": f"Bearer {ha.token}",
            "Content-Type": "application/json"
        }

        payload = {
            "title": title,
            "message": message
        }
        r = requests.post(url, headers=headers_ha, json=payload, timeout=2)
        r.raise_for_status()
        log(f"Home Assistant Notification Status: {r.status_code}")
    except Exception as e:
        log(f"Fehler bei Home Assistant Notification: {e}")

# =====================
# DATUM / DATENBANK
# =====================
def get_dates():
    current_date = datetime.now().strftime("%Y%m%d")
    target_date = (datetime.now() + timedelta(days=days)).strftime("%Y%m%d")
    return current_date, target_date

def load_course_ids(target_date):
    stored_course_ids = prepared_course_ids(target_date)
    if stored_course_ids:
        log(f"Kurs-IDs aus Datenbank geladen: {stored_course_ids}")
        return stored_course_ids
    log("Keine Kurs-IDs in der Datenbank gefunden.")
    return {}

# =====================
# PREPARE: KURS-IDS HOLEN
# =====================
def prepare_course_ids():
    current_date, target_date = get_dates()
    log(f"Prepare sucht Kurse fuer {target_date}: {', '.join(desired_courses)}")
    facility_id = mywellness_config().get("facility_id", "")
    search_url = (
        f"https://services.mywellness.com/Core/Facility/{facility_id}/"
        f"SearchCalendarEvents?_c=de-DE&dateStart={current_date}&dateLimit=0"
    )
    payload = {
        "dateLimit": "0",
        "dateStart": target_date,
        "eventType": "Class",
        "timeScope": "Custom"
    }
    try:
        response = session.post(search_url, json=payload, timeout=4)
        response.raise_for_status()
        data = response.json()
        event_items = data.get("data", {}).get("eventItems", [])
        replace_prepared_courses(target_date, event_items, desired_courses)
        course_ids = prepared_course_ids(target_date)
        message = "Vorbereitung abgeschlossen.\n\n"
        message += "Gefunden:\n"
        message += "\n".join(f"{k}: {v}" for k, v in course_ids.items()) or "Keine"
        if not course_ids:
            names = [str(event.get("name")) for event in event_items if event.get("name")]
            log("Keine Wunschkurse gefunden. Geladene Kurse: " + (", ".join(names[:40]) if names else "Keine"))
        log(message)
        if course_ids:
            send_ha_notification("Kurs-IDs vorbereitet", message)
    except Exception as e:
        msg = f"Fehler beim Vorbereiten: {e}"
        log(msg)
        send_ha_notification("Vorbereitung Fehler", msg)

# =====================
# BOOKING
# =====================
def try_booking_course(course_name, course_id, target_date):
    booking_url = f"https://services.mywellness.com/core/calendarevent/{course_id}/book?_c=de-DE"
    payload = {
        "partitionDate": target_date,
        "userId": mywellness_config().get("user_id", "")
    }
    for attempt in range(1, MAX_RETRIES + 1):
        start = time.perf_counter()
        try:
            response = session.post(
                booking_url,
                json=payload,
                timeout=REQUEST_TIMEOUT
            )
            elapsed_ms = round((time.perf_counter() - start) * 1000)
            try:
                response_json = response.json()
            except Exception:
                response_json = {}
            log_payload = dict(response_json) if isinstance(response_json, dict) else {}
            if "token" in log_payload:
                log_payload["token"] = "[redacted]"
            text = json.dumps(log_payload, ensure_ascii=False) if log_payload else response.text
            result = (
                f"{course_name}: Versuch {attempt}, "
                f"Status {response.status_code}, "
                f"{elapsed_ms} ms, Antwort: {text}"
            )
            log(result)
            if "Booking has not opened" in text:
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY)
                    continue
                return {
                    "course_name": course_name,
                    "success": False,
                    "message": f"{course_name}: Buchung nicht geöffnet nach {MAX_RETRIES} Versuchen."
                }
            has_errors = bool(response_json.get("errors"))
            booking_state = response_json.get("data")
            success = (
                response.status_code in (200, 201)
                and not has_errors
                and booking_state == "Booked"
            )
            return {
                "course_name": course_name,
                "success": success,
                "message": result
            }
        except Exception as e:
            elapsed_ms = round((time.perf_counter() - start) * 1000)
            log(f"{course_name}: Fehler Versuch {attempt}, {elapsed_ms} ms: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
    return {
        "course_name": course_name,
        "success": False,
        "message": f"{course_name}: Buchung nach {MAX_RETRIES} Versuchen nicht erfolgreich."
    }

def book_saved_course_ids():
    _, target_date = get_dates()
    course_ids = load_course_ids(target_date)
    prepared_courses = {str(course.get("id")): course for course in list_prepared_courses(target_date)}
    if not course_ids:
        msg = "Buchung abgebrochen: Keine Kurs-IDs verfügbar."
        log(msg)
        return
    
    all_results = []
    successful_bookings = []
    successful_course_ids = []
    max_workers = max(1, len(course_ids))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for course_name, course_id in course_ids.items():
            futures[
                executor.submit(
                    try_booking_course,
                    course_name,
                    course_id,
                    target_date
                )
            ] = course_name
        for future in as_completed(futures):
            course_name = futures[future]
            try:
                result = future.result()
                all_results.append(result["message"])
                if result["success"]:
                    successful_bookings.append(result["course_name"])
                    if result["course_name"] in course_ids:
                        successful_course_ids.append(course_ids[result["course_name"]])
                        try:
                            save_booking_history(
                                booking_id=course_ids[result["course_name"]],
                                course_id=course_ids[result["course_name"]],
                                action="booked",
                            )
                        except Exception as history_error:
                            log(f"{course_name}: Buchungshistorie konnte nicht gespeichert werden: {history_error}")
                        try:
                            course = prepared_courses.get(str(course_ids[result["course_name"]])) or {"id": course_ids[result["course_name"]], "title": result["course_name"]}
                            calendar_result = add_course_to_calendar(course, ha, calendar_entity=mywellness_config().get("calendar_entity"))
                            log(f"{course_name}: Kalendereintrag Ergebnis: {calendar_result}")
                        except Exception as calendar_error:
                            log(f"{course_name}: Kalendereintrag konnte nicht erstellt werden: {calendar_error}")
            except Exception as e:
                all_results.append(f"{course_name}: Fehler: {e}")
    log("\n\n".join(all_results))
    if successful_bookings:
        message = "Erfolgreich gebucht:\n" + "\n".join(successful_bookings)
        log("Erfolgreich gebucht: " + ", ".join(successful_bookings))
        deleted = delete_prepared_courses(target_date, successful_course_ids)
        log(f"Vorgemerkte Kurse geloescht: {deleted}")
        send_ha_notification("Buchung erfolgreich", message)
    else:
        log("Keine erfolgreiche Buchung erkannt. Keine Push gesendet.")
    log("Buchung abgeschlossen.")

# =====================
# START
# =====================
if __name__ == "__main__":
    ha = HomeAssistantClient()
    started_at = datetime.now().isoformat(timespec="seconds")

    try:
        if MODE == "prepare":
            prepare_course_ids()
        elif MODE == "book":
            book_saved_course_ids()
        else:
            log(f"Unbekannter MODE: {MODE}")
        record_run(MODE, "ok", started_at, datetime.now().isoformat(timespec="seconds"))
    except Exception as exc:
        record_run(MODE, "error", started_at, datetime.now().isoformat(timespec="seconds"), str(exc))
        raise
