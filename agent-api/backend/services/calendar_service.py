from __future__ import annotations

import os
from datetime import date, datetime, time, timezone
from typing import Any

from backend.services.homeassistant_service import HomeAssistantService

DEFAULT_CALENDAR_ENTITY = "calendar.devcal"


class CalendarService:
    """Small facade for wall agenda data.

    Home Assistant is the first source. Other providers can be added here later
    without coupling the wall UI to Google Calendar or a larger calendar agent.
    """

    def __init__(self, ha_service: HomeAssistantService | None = None, calendar_entity: str | None = None) -> None:
        self.ha_service = ha_service or HomeAssistantService()
        self.calendar_entity = (
            calendar_entity
            or os.getenv("WALL_CALENDAR_ENTITY")
            or os.getenv("HOUSEHOLD_CALENDAR_ENTITY")
            or DEFAULT_CALENDAR_ENTITY
        )

    def today_summary(self) -> dict[str, Any]:
        now = datetime.now().astimezone()
        updated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        try:
            entity_id = self._resolve_calendar_entity()
            if not entity_id:
                return empty_summary(updated_at, "stub")

            start = datetime.combine(now.date(), time.min, tzinfo=now.tzinfo)
            end = datetime.combine(now.date(), time.max, tzinfo=now.tzinfo)
            events = [
                event for event in (
                    self._event_summary(entity_id, raw_event)
                    for raw_event in self.ha_service.get_calendar_events(entity_id, start.isoformat(), end.isoformat())
                )
                if event
            ]
        except Exception as exc:
            return empty_summary(updated_at, f"homeassistant:{normalize_entity_id(self.calendar_entity)}", str(exc))
        events.sort(key=lambda item: parse_event_datetime(item.get("start")) or datetime.max.replace(tzinfo=timezone.utc))
        active_or_upcoming = [
            event for event in events
            if (parse_event_datetime(event.get("end")) or parse_event_datetime(event.get("start")) or now) >= now
        ]
        next_event = active_or_upcoming[0] if active_or_upcoming else None
        upcoming = (active_or_upcoming or events)[:3]
        return {
            "ok": True,
            "updated_at": updated_at,
            "today_count": len(events),
            "next_event": next_event,
            "upcoming": upcoming,
            "source": f"homeassistant:{entity_id}",
        }

    def _resolve_calendar_entity(self) -> str | None:
        configured = normalize_entity_id(self.calendar_entity)
        if configured:
            try:
                state = self.ha_service.get_state(configured)
                if state:
                    return configured
            except Exception:
                if configured != DEFAULT_CALENDAR_ENTITY:
                    raise

        calendars = self.ha_service.get_calendars()
        if not calendars:
            return configured or None
        wanted = configured or DEFAULT_CALENDAR_ENTITY
        exact = next((item for item in calendars if normalize_entity_id(item.get("entity_id")) == wanted), None)
        if exact:
            return str(exact.get("entity_id"))
        devcal = next(
            (
                item for item in calendars
                if "devcal" in f"{item.get('entity_id') or ''} {item.get('name') or ''}".lower()
            ),
            None,
        )
        if devcal:
            return str(devcal.get("entity_id"))
        first = next((item for item in calendars if str(item.get("entity_id") or "").startswith("calendar.")), None)
        return str(first.get("entity_id")) if first else None

    def _event_summary(self, entity_id: str, event: Any) -> dict[str, Any] | None:
        if not isinstance(event, dict):
            return None
        title = str(event.get("summary") or event.get("title") or event.get("message") or "Termin").strip()
        start = normalize_calendar_time(event.get("start"))
        end = normalize_calendar_time(event.get("end"))
        if not start:
            return None
        return {
            "title": title or "Termin",
            "start": start,
            "end": end,
            "location": str(event.get("location") or "").strip(),
            "source": f"homeassistant:{entity_id}",
        }


def empty_summary(updated_at: str, source: str, error: str | None = None) -> dict[str, Any]:
    data = {
        "ok": error is None,
        "updated_at": updated_at,
        "today_count": 0,
        "next_event": None,
        "upcoming": [],
        "source": source,
    }
    if error:
        data["error"] = error
    return data


def normalize_entity_id(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text if text.startswith("calendar.") else f"calendar.{text}"


def normalize_calendar_time(value: Any) -> str | None:
    raw = value
    if isinstance(value, dict):
        raw = value.get("dateTime") or value.get("date")
    if isinstance(raw, datetime):
        return raw.isoformat()
    if isinstance(raw, date):
        return datetime.combine(raw, time.min).isoformat()
    text = str(raw or "").strip()
    if not text:
        return None
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        return f"{text}T00:00:00"
    return text


def parse_event_datetime(value: Any) -> datetime | None:
    text = normalize_calendar_time(value)
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.astimezone()
    return parsed.astimezone()
