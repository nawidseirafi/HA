from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any

DEFAULT_MYWELLNESS_CALENDAR_ENTITY = "calendar.devcal"


def add_course_to_calendar(course: dict[str, Any], ha_service: Any, calendar_entity: str | None = None) -> dict[str, Any]:
    entity_id = normalize_calendar_entity(
        calendar_entity
        or os.getenv("MYWELLNESS_CALENDAR_ENTITY")
        or os.getenv("WALL_CALENDAR_ENTITY")
        or DEFAULT_MYWELLNESS_CALENDAR_ENTITY
    )
    title = str(course.get("title") or course.get("name") or "MyWellness Kurs").strip()
    start = normalize_datetime(course.get("startTime") or course.get("starts_at") or course.get("start_time"))
    end = normalize_datetime(course.get("endTime") or course.get("ends_at") or course.get("end_time"))
    if not start:
        return {"ok": False, "skipped": True, "reason": "missing_start_time", "entity_id": entity_id}
    if not end:
        end = (parse_datetime(start) + timedelta(hours=1)).isoformat(timespec="minutes")

    if calendar_event_exists(ha_service, entity_id, title, start, end):
        return {"ok": True, "skipped": True, "reason": "already_exists", "entity_id": entity_id}

    payload = {
        "entity_id": entity_id,
        "summary": title,
        "start_date_time": start,
        "end_date_time": end,
        "description": "Automatisch eingetragen nach MyWellness-Buchung.",
    }
    location = str(course.get("location") or course.get("studio") or course.get("room") or "").strip()
    if location:
        payload["location"] = location
    response = ha_service.call_service("calendar", "create_event", payload)
    return {"ok": True, "skipped": False, "entity_id": entity_id, "response": response}


def calendar_event_exists(ha_service: Any, entity_id: str, title: str, start: str, end: str) -> bool:
    try:
        start_dt = parse_datetime(start)
        end_dt = parse_datetime(end)
        events = ha_service.get_calendar_events(
            entity_id,
            (start_dt - timedelta(minutes=2)).isoformat(),
            (end_dt + timedelta(minutes=2)).isoformat(),
        )
    except Exception:
        return False
    expected_start = parse_datetime(start)
    normalized_title = normalize_title(title)
    for event in events if isinstance(events, list) else []:
        if not isinstance(event, dict):
            continue
        event_title = normalize_title(event.get("summary") or event.get("title") or event.get("message"))
        event_start = parse_calendar_event_time(event.get("start"))
        if event_title == normalized_title and event_start and abs((comparable_datetime(event_start) - comparable_datetime(expected_start)).total_seconds()) < 120:
            return True
    return False


def normalize_calendar_entity(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return DEFAULT_MYWELLNESS_CALENDAR_ENTITY
    return text if text.startswith("calendar.") else f"calendar.{text}"


def normalize_datetime(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat(timespec="minutes")
    text = str(value or "").strip()
    if not text:
        return None
    parsed = parse_datetime(text)
    return parsed.isoformat(timespec="minutes")


def parse_datetime(value: Any) -> datetime:
    text = str(value or "").strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    return datetime.fromisoformat(text)


def parse_calendar_event_time(value: Any) -> datetime | None:
    raw = value
    if isinstance(value, dict):
        raw = value.get("dateTime") or value.get("date")
    if not raw:
        return None
    try:
        return parse_datetime(raw)
    except Exception:
        return None


def normalize_title(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def comparable_datetime(value: datetime) -> datetime:
    return value.replace(tzinfo=None)
