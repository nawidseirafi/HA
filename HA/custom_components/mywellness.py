import requests
from datetime import datetime, timedelta
import time
import os
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

# =====================
# KONFIGURATION
# =====================
HA_URL = "http://homeassistant.local:8123"
HA_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiI3ZTEzNGQ3MTg0MDY0OGVjODI1MTZiMzE5YTI5ZGMzNyIsImlhdCI6MTc3NzcwMDAwOCwiZXhwIjoyMDkzMDYwMDA4fQ.10lZSyvgqa5bNU26YfPQ2IXiGTzbf9wb5heevOGdNVc"
HA_NOTIFY_SERVICE = "notify.mobile_app_system_error_404"

auth_token = 'MjAyNjAzMjcwODE3NTZ8NTAzZjA4MjQzOTRlNGNiNGFhZDk4OWUxMmQ3ZGI2MDZ8ZWMxZDM4ZDdkMzU5NDhkMGE2MGNkOGMwYjhmYjlkZjl8M3xXLiBFdXJvcGUgU3RhbmRhcmQgVGltZXxkZS1ERXxiNDdjMjMzMmNkMDM0YmFhYjBmZGEyNmIzMmVhZGMzYXx8fHwxfDF8MHwxMDB8fHw1OHw1OTI0fDB8Y29tLm15d2VsbG5lc3M1.FE4BFC3113662FA448A2B44154CAB6CA28363BE996FA1A4E599438029EE6A32185BAFA31EBFD7ECD22512618E2B3BEC36103B9D82961F32857BA0FD173B5518A'
userId = 'b47c2332-cd03-4baa-b0fd-a26b32eadc3a'
desired_courses = ['Cross-Power', 'Body Workout', 'Functional Training']  # Kurse die gebucht werden sollen
days = 2  # Anzahl der Tage im Voraus

FACILITY_ID = "0273e18b-52bf-404e-afa6-8bfb2eeccbad"

# Empfehlung:
# 20:58:00 -> MODE = "prepare"
# 20:59:58 -> MODE = "book"
# MODE = "book"
# MODE = "prepare"

MODE = sys.argv[1] if len(sys.argv) > 1 else "book"
MAX_RETRIES = 30  # Reduziert: meist reichen 2-3 Versuche
RETRY_DELAY = 0.1  # Schneller Retry
REQUEST_TIMEOUT = 3  # Erhöht: externe Services brauchen manchmal länger
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, "mywellness.log")
CACHE_FILE = os.path.join(BASE_DIR, "mywellness_cache.json")

headers = {
    "Content-Type": "application/json",
    "Authorization": auth_token
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
        url = f"{HA_URL}/api/services/notify/{service}"
        headers_ha = {
            "Authorization": f"Bearer {HA_TOKEN}",
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
    search_url = (
        f"https://services.mywellness.com/Core/Facility/{FACILITY_ID}/"
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
        save_course_ids(target_date, course_ids)
        message = "Vorbereitung abgeschlossen.\n\n"
        message += "Gefunden:\n"
        message += "\n".join(f"{k}: {v}" for k, v in course_ids.items()) or "Keine"
        log(message)
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
        "userId": userId
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
        send_ha_notification("Buchung erfolgreich", message)
    else:
        log("Keine erfolgreiche Buchung erkannt. Keine Push gesendet.")
    log("Buchung abgeschlossen.")

# =====================
# START
# =====================
if __name__ == "__main__":
    if MODE == "prepare":
        prepare_course_ids()
    elif MODE == "book":
        book_saved_course_ids()
    else:
        log(f"Unbekannter MODE: {MODE}")