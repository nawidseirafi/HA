import requests
from datetime import datetime, timedelta
import time
import os
import json
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
import yaml

# =====================
# KONFIGURATION
# =====================
HA_NOTIFY_SERVICE = "notify.mobile_app_system_error_404"
desired_courses = ['Cross-Power', 'Body Workout', 'Functional Training']  # Kurse die gebucht werden sollen
days = 2  # Anzahl der Tage im Voraus


# Empfehlung:
# 20:58:00 -> MODE = "prepare"
# 20:59:58 -> MODE = "book"
# MODE = "book"
# MODE = "prepare"

MODE = sys.argv[1] if len(sys.argv) > 1 else "book"
MAX_RETRIES = 30  # Reduziert: meist reichen 2-3 Versuche
RETRY_DELAY = 0.1  # Schneller Retry
REQUEST_TIMEOUT = 3  # Erhöht: externe Services brauchen manchmal länger
BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from shared.ha_client import HomeAssistantClient
from mywellness.store import prepared_course_ids, record_run, replace_prepared_courses

LOG_FILE = PROJECT_DIR / "logs" / "mywellness.log"
CACHE_FILE = BASE_DIR / "mywellness_cache.json"

def load_raw_config() -> dict:
    load_dotenv(PROJECT_DIR / ".env")

    with (PROJECT_DIR / "config.yaml").open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def resolve_config_value(value):
    text = str(value or "")
    resolved = os.getenv(text) or os.getenv(text.upper())
    if resolved:
        return resolved
    if text.isupper() and text.replace("_", "").isalnum():
        return ""
    return text

def mywellness_config() -> dict:
    config = load_raw_config().get("myWelness_agent", {})
    return {
        "token": os.getenv("MY_WELLNESS_TOKEN") or resolve_config_value(config.get("token", "")),
        "user_id": os.getenv("MY_WELLNESS_USER_ID") or resolve_config_value(config.get("user_id", "")),
        "facility_id": os.getenv("MY_WELLNESS_FACILITY_ID") or resolve_config_value(config.get("facility_id", "")),
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
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
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
# DATUM / CACHE
# =====================
def get_dates():
    current_date = datetime.now().strftime("%Y%m%d")
    target_date = (datetime.now() + timedelta(days=days)).strftime("%Y%m%d")
    return current_date, target_date

def save_course_ids(target_date, course_ids):
    if not course_ids:
        log("WARNUNG: Keine Kurs-IDs gefunden. Cache wird geleert.")
        if os.path.exists(CACHE_FILE):
            os.remove(CACHE_FILE)
            log("Cache-Datei gelöscht.")
        return
    data = {
        "created_at": datetime.now().isoformat(),
        "target_date": target_date,
        "course_ids": course_ids
    }
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    log(f"Kurs-IDs gespeichert: {course_ids}")

def load_course_ids(target_date):
    stored_course_ids = prepared_course_ids(target_date)
    if stored_course_ids:
        log(f"Kurs-IDs aus Datenbank geladen: {stored_course_ids}")
        return stored_course_ids

    if not os.path.exists(CACHE_FILE):
        log("Keine Cache-Datei gefunden.")
        return {}
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("target_date") != target_date:
            log(f"Cache-Datum passt nicht: {data.get('target_date')} statt {target_date}")
            return {}
        return data.get("course_ids", {})

    except Exception as e:
        log(f"Fehler beim Lesen vom Cache: {e}")
        return {}

# =====================
# PREPARE: KURS-IDS HOLEN
# =====================
def prepare_course_ids():
    current_date, target_date = get_dates()
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
        course_ids = {
            event["name"]: event["id"]
            for event in event_items
            if event.get("name") in desired_courses
        }
        replace_prepared_courses(target_date, event_items, desired_courses)
        save_course_ids(target_date, course_ids)
        message = "Vorbereitung abgeschlossen.\n\n"
        message += "Gefunden:\n"
        message += "\n".join(f"{k}: {v}" for k, v in course_ids.items()) or "Keine"
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
            text = response.text
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
            try:
                response_json = response.json()

            except Exception:
                response_json = {}
            has_errors = bool(response_json.get("errors"))
            success = (
                response.status_code in (200, 201)
                and not has_errors
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
    if not course_ids:
        msg = "Buchung abgebrochen: Keine Kurs-IDs verfügbar."
        log(msg)
        return
    
    all_results = []
    successful_bookings = []
    max_workers = max(1, len(desired_courses))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for course_name in desired_courses:
            if course_name in course_ids:
                futures[
                    executor.submit(
                        try_booking_course,
                        course_name,
                        course_ids[course_name],
                        target_date
                    )
                ] = course_name
            else:
                all_results.append(f"{course_name}: Keine Kurs-ID gespeichert.")
        for future in as_completed(futures):
            course_name = futures[future]
            try:
                result = future.result()
                all_results.append(result["message"])
                if result["success"]:
                    successful_bookings.append(result["course_name"])
            except Exception as e:
                all_results.append(f"{course_name}: Fehler: {e}")
    log("\n\n".join(all_results))
    if successful_bookings:
        message = "Erfolgreich gebucht:\n" + "\n".join(successful_bookings)
        log("Erfolgreich gebucht: " + ", ".join(successful_bookings))
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
