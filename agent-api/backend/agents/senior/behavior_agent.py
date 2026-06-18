from __future__ import annotations

import json
import logging
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.services.llm.factory import create_llm_client
from backend.services.messaging import MessagingService

from .device_mapping_service import DeviceMappingService, now
from .notification_service import NotificationService

logger = logging.getLogger(__name__)

VALID_STATUSES = {"green", "yellow", "orange", "red"}
SYSTEM_PROMPT = """Du bist Sentero.

Du bewertest den Tagesablauf einer älteren Person.

Deine Aufgabe:
- normale Tage erkennen
- Auffälligkeiten erkennen
- Risiko einschätzen

Du stellst keine Diagnosen.
Du bewertest lediglich, ob das Verhalten vom üblichen Alltag abweicht.
Du löst keine Notrufe aus.

Antwort nur als JSON mit:
{
  "status": "green|yellow|orange|red",
  "confidence": 0.0,
  "summary": "",
  "findings": [],
  "recommendation": "",
  "email_subject": "",
  "email_body": ""
}"""


class SeniorBehaviorAgent:
    def __init__(self, mapping: DeviceMappingService | None = None, messaging: MessagingService | None = None) -> None:
        self.mapping = mapping or DeviceMappingService()
        self.messaging = messaging or MessagingService()
        self.notifications = NotificationService(self.mapping, self.messaging)
        self.ensure_schema()

    def ensure_schema(self) -> None:
        with self.mapping.connect() as con:
            con.execute(
                """create table if not exists senior_sensor_events (
                    id integer primary key autoincrement,
                    event_time text not null,
                    role text,
                    room text,
                    entity_id text,
                    state text,
                    device_class text,
                    source text not null default 'snapshot',
                    created_at text not null
                )"""
            )
            con.execute(
                """create table if not exists behavior_assessments (
                    id integer primary key autoincrement,
                    assessment_time text not null,
                    status text not null,
                    confidence real not null,
                    summary text not null,
                    findings_json text not null default '[]',
                    recommendation text not null,
                    llm_response text,
                    created_at text not null
                )"""
            )
            con.commit()

    def run(self, dry_run: bool = False) -> dict[str, Any]:
        self.ensure_schema()
        configured_roles = self.mapping.roles(dev=True, include_state=False)
        if not configured_roles:
            return {
                "status": "not_configured",
                "assessment": None,
                "payload": {"reason": "no_sensors_configured"},
                "dry_run": dry_run,
                "message": "Sentero wartet auf eingerichtete Sensoren. Es wurde keine KI-Auswertung gestartet und keine Benachrichtigung versendet.",
            }
        profile = self._profile()
        contacts = self._contacts()
        sensor_snapshot = self.mapping.roles(dev=True, include_state=True)
        try:
            ha_snapshot = self.mapping.snapshot()
        except Exception as exc:
            logger.info("Senior behavior HA snapshot unavailable for presence analysis: %s", exc)
            ha_snapshot = []
        if not dry_run:
            self._record_snapshot(sensor_snapshot, ha_snapshot)
        history = self._history(days=30)
        payload = self._analysis_payload(profile, contacts, sensor_snapshot, history, ha_snapshot)
        assessment = self._assess(payload)
        stored = assessment if dry_run else self._store_assessment(assessment)
        if not dry_run:
            self._notify_if_needed(stored, contacts)
        return {
            "status": stored["status"],
            "assessment": stored,
            "payload": payload,
            "dry_run": dry_run,
        }

    def latest(self) -> dict[str, Any] | None:
        self.ensure_schema()
        with self.mapping.connect() as con:
            row = con.execute("select * from behavior_assessments order by assessment_time desc, id desc limit 1").fetchone()
        return self._row_to_assessment(row) if row else None

    def history(self, limit: int = 20) -> list[dict[str, Any]]:
        self.ensure_schema()
        with self.mapping.connect() as con:
            rows = con.execute("select * from behavior_assessments order by assessment_time desc, id desc limit ?", (limit,)).fetchall()
        return [self._row_to_assessment(row) for row in rows]

    def timeline_today(self) -> dict[str, Any]:
        start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        events = [event for event in self._history(days=1) if self._parse_time(event.get("event_time")) >= start]
        return {
            "events": events,
            "assessment": self.latest(),
        }

    def _profile(self) -> dict[str, Any]:
        with self.mapping.connect() as con:
            row = con.execute("select * from senior_profile where id = 1").fetchone()
        data = dict(row) if row else {}
        notes = str(data.get("notes") or "").strip()
        data["notes_list"] = [part.strip() for part in re.split(r"[\n,;]+", notes) if part.strip()]
        return data

    def _contacts(self) -> list[dict[str, Any]]:
        with self.mapping.connect() as con:
            rows = con.execute("select * from trusted_contacts where active = 1 order by id").fetchall()
        return [dict(row) for row in rows]

    def _record_snapshot(self, roles: list[dict[str, Any]], ha_snapshot: list[dict[str, Any]] | None = None) -> None:
        timestamp = now()
        extra_events = self._fp300_snapshot_events(roles, ha_snapshot or [], timestamp)
        with self.mapping.connect() as con:
            for role in [*roles, *extra_events]:
                state = role.get("state")
                if state in (None, "", "unknown", "unavailable"):
                    continue
                con.execute(
                    """insert into senior_sensor_events
                       (event_time, role, room, entity_id, state, device_class, source, created_at)
                       values (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        role.get("last_changed") or role.get("last_updated") or timestamp,
                        role.get("role"),
                        role.get("room"),
                        role.get("entity_id"),
                        state,
                        role.get("device_class"),
                        role.get("source") or "snapshot",
                        timestamp,
                    ),
                )
            con.commit()

    def _history(self, days: int) -> list[dict[str, Any]]:
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
        with self.mapping.connect() as con:
            rows = con.execute(
                "select * from senior_sensor_events where event_time >= ? order by event_time asc",
                (since,),
            ).fetchall()
        return [dict(row) for row in rows]

    def _analysis_payload(
        self,
        profile: dict[str, Any],
        contacts: list[dict[str, Any]],
        sensor_snapshot: list[dict[str, Any]],
        history: list[dict[str, Any]],
        ha_snapshot: list[dict[str, Any]],
    ) -> dict[str, Any]:
        today = datetime.now(timezone.utc).date()
        today_events = [event for event in history if self._parse_time(event.get("event_time")).date() == today]
        previous_events = [event for event in history if self._parse_time(event.get("event_time")).date() != today]
        return {
            "profile": {
                "name": profile.get("name"),
                "age": profile.get("age"),
                "living_alone": True,
                "mobility": None,
                "notes": profile.get("notes_list") or [],
            },
            "trusted_contacts": [{"name": item.get("name"), "relationship": item.get("relationship"), "email": item.get("email")} for item in contacts],
            "daily_profile": self._daily_profile(previous_events),
            "current_day": self._day_summary(today_events),
            "current_sensor_snapshot": self._compact_roles(sensor_snapshot),
            "presence_sensor_analysis": self._fp300_analysis(sensor_snapshot, ha_snapshot, history),
            "deviations": self._deviations(today_events, previous_events, sensor_snapshot),
            "safety_rules": {
                "no_medical_diagnosis": True,
                "no_emergency_calls": True,
                "only_behavioral_anomaly_detection": True,
                "presence_sensor_limits": [
                    "Aqara FP300 erkennt Anwesenheit und Bewegung, aber keine Atmung.",
                    "Aqara FP300 unterscheidet Sitzen und Liegen nicht zuverlässig.",
                    "Aqara FP300 ist kein Sturzsensor und darf nicht als medizinisches Signal bewertet werden.",
                ],
            },
        }

    def _assess(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            client = create_llm_client()
            response = client.generate(
                prompt=(
                    "Bewerte diesen Sentero Tagesablauf. Nutze historische Routinen stärker als einzelne Sensorwerte. "
                    "Presence-Sensor-Auswertungen sind Näherungen: niemals Atmung, Sturz, Schlaf oder Körperposition behaupten. "
                    "Erzeuge auch einen menschenfreundlichen E-Mail-Text für orange/red, sonst leer lassen.\n\n"
                    f"{json.dumps(payload, ensure_ascii=False)}"
                ),
                system=SYSTEM_PROMPT,
            )
            raw = self._extract_json(response.text)
            return self._validate_assessment(raw, response.text)
        except Exception as exc:
            logger.info("Senior behavior LLM unavailable, using heuristic fallback: %s", exc)
            fallback = self._heuristic_assessment(payload)
            fallback["llm_response"] = json.dumps({"fallback_reason": str(exc)}, ensure_ascii=False)
            return fallback

    def _heuristic_assessment(self, payload: dict[str, Any]) -> dict[str, Any]:
        deviations = payload.get("deviations") or {}
        findings = []
        status = "green"
        if deviations.get("insufficient_data"):
            return {
                "assessment_time": now(),
                "status": "green",
                "confidence": 0.4,
                "summary": "Es liegen noch nicht genug Sensordaten für eine verlässliche Tagesbewertung vor.",
                "findings": ["Sentero sammelt zunächst Sensorhistorie, um Routinen zu lernen."],
                "recommendation": "Keine Aktion erforderlich.",
                "email_subject": "",
                "email_body": "",
                "llm_response": "",
            }
        if deviations.get("no_activity_today"):
            status = "orange"
            findings.append("Heute wurde bisher keine Sensoraktivität erkannt.")
        elif deviations.get("activity_ratio", 1) < 0.45:
            status = "yellow"
            findings.append("Heute wurde weniger Aktivität als üblich erkannt.")
        if deviations.get("inactive_hours", 0) >= 8:
            status = "red"
            findings.append("Es gibt eine ungewöhnlich lange Phase ohne erkannte Aktivität.")
        elif deviations.get("inactive_hours", 0) >= 5 and status in {"green", "yellow"}:
            status = "orange"
            findings.append("Es gibt eine längere Phase ohne erkannte Aktivität.")
        summary_by_status = {
            "green": "Der Tagesablauf entspricht soweit erkennbar dem üblichen Verhalten.",
            "yellow": "Der Tagesablauf zeigt leichte Abweichungen vom üblichen Muster.",
            "orange": "Der Tagesablauf weicht deutlich vom gewohnten Verhalten ab.",
            "red": "Der Tagesablauf zeigt erhebliche Auffälligkeiten.",
        }
        recommendation = "Keine Aktion erforderlich." if status == "green" else "Bitte kurz nachfragen, ob alles in Ordnung ist."
        return {
            "assessment_time": now(),
            "status": status,
            "confidence": 0.72 if findings else 0.62,
            "summary": summary_by_status[status],
            "findings": findings,
            "recommendation": recommendation,
            "email_subject": "Sentero Hinweis zum Tagesablauf" if status in {"orange", "red"} else "",
            "email_body": self._email_body(summary_by_status[status], findings, recommendation) if status in {"orange", "red"} else "",
            "llm_response": "",
        }

    def _store_assessment(self, assessment: dict[str, Any]) -> dict[str, Any]:
        timestamp = assessment.get("assessment_time") or now()
        with self.mapping.connect() as con:
            cur = con.execute(
                """insert into behavior_assessments
                   (assessment_time, status, confidence, summary, findings_json, recommendation, llm_response, created_at)
                   values (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    timestamp,
                    assessment["status"],
                    float(assessment.get("confidence") or 0),
                    assessment.get("summary") or "",
                    json.dumps(assessment.get("findings") or [], ensure_ascii=False),
                    assessment.get("recommendation") or "",
                    assessment.get("llm_response") or json.dumps(assessment, ensure_ascii=False),
                    now(),
                ),
            )
            con.commit()
            row = con.execute("select * from behavior_assessments where id = ?", (int(cur.lastrowid),)).fetchone()
        stored = self._row_to_assessment(row)
        stored["email_subject"] = assessment.get("email_subject") or ""
        stored["email_body"] = assessment.get("email_body") or ""
        return stored

    def _notify_if_needed(self, assessment: dict[str, Any], contacts: list[dict[str, Any]]) -> None:
        if not self.mapping.roles(dev=True, include_state=False):
            logger.info("Sentero notification skipped because no sensors are configured")
            return
        status = assessment.get("status")
        if status not in {"orange", "red"}:
            return
        severity = "critical" if status == "red" else "warning"
        self.messaging.create_message(
            source="senior",
            category="behavior",
            severity=severity,
            title="Sentero Tagesablauf prüfen",
            message=assessment.get("email_body") or assessment.get("summary") or "",
            payload={
                "assessment_id": assessment.get("id"),
                "status": status,
                "contacts": [{"name": item.get("name"), "email": item.get("email")} for item in contacts],
                "email_subject": assessment.get("email_subject") or "Sentero Hinweis",
            },
        )
        self.notifications.notify_assessment(assessment, contacts)

    def _daily_profile(self, events: list[dict[str, Any]]) -> dict[str, Any]:
        by_room: dict[str, list[int]] = defaultdict(list)
        for event in events:
            room = str(event.get("room") or "unknown")
            by_room[room].append(self._parse_time(event.get("event_time")).hour)
        return {
            room: {
                "common_hours": [hour for hour, _ in Counter(hours).most_common(5)],
                "event_count": len(hours),
            }
            for room, hours in by_room.items()
        }

    def _day_summary(self, events: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "event_count": len(events),
            "rooms": dict(Counter(str(event.get("room") or "unknown") for event in events)),
            "events": [
                {
                    "time": self._parse_time(event.get("event_time")).isoformat(timespec="minutes"),
                    "room": event.get("room"),
                    "role": event.get("role"),
                    "state": event.get("state"),
                }
                for event in events[-40:]
            ],
        }

    def _deviations(self, today_events: list[dict[str, Any]], previous_events: list[dict[str, Any]], roles: list[dict[str, Any]]) -> dict[str, Any]:
        historical_days = max(1, len({self._parse_time(event.get("event_time")).date() for event in previous_events}))
        average_events = len(previous_events) / historical_days if previous_events else 0
        ratio = (len(today_events) / average_events) if average_events else 1 if today_events else 0
        latest = max((self._parse_time(role.get("last_changed") or role.get("last_updated") or role.get("updated_at")) for role in roles if role.get("last_changed") or role.get("last_updated") or role.get("updated_at")), default=None)
        inactive_hours = ((datetime.now(timezone.utc) - latest).total_seconds() / 3600) if latest else 0
        return {
            "insufficient_data": not roles and not today_events and not previous_events,
            "no_activity_today": len(today_events) == 0,
            "today_event_count": len(today_events),
            "historical_daily_average": round(average_events, 2),
            "activity_ratio": round(ratio, 2),
            "inactive_hours": round(inactive_hours, 2),
        }

    def _fp300_snapshot_events(self, roles: list[dict[str, Any]], ha_snapshot: list[dict[str, Any]], timestamp: str) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for role in roles:
            if not self._is_presence_role(role):
                continue
            related = self._related_presence_entities(role, ha_snapshot)
            for kind, item in related.items():
                if not item:
                    continue
                events.append({
                    "role": f"{role.get('role')}_{kind}",
                    "room": role.get("room"),
                    "entity_id": item.get("entity_id"),
                    "state": item.get("state"),
                    "device_class": item.get("device_class"),
                    "source": "fp300_snapshot",
                    "last_changed": item.get("last_changed") or timestamp,
                    "last_updated": item.get("last_updated") or timestamp,
                })
        return events

    def _fp300_analysis(
        self,
        roles: list[dict[str, Any]],
        ha_snapshot: list[dict[str, Any]],
        history: list[dict[str, Any]],
    ) -> dict[str, Any]:
        devices = []
        for role in roles:
            if not self._is_presence_role(role):
                continue
            related = self._related_presence_entities(role, ha_snapshot)
            presence = related.get("presence")
            motion = related.get("motion")
            devices.append({
                "room": role.get("room"),
                "role": role.get("role"),
                "device_model": role.get("model"),
                "manufacturer": role.get("manufacturer"),
                "presence_entity": self._entity_compact(presence),
                "motion_entity": self._entity_compact(motion),
                "illuminance_entity": self._entity_compact(related.get("illuminance")),
                "temperature_entity": self._entity_compact(related.get("temperature")),
                "humidity_entity": self._entity_compact(related.get("humidity")),
                "battery_entity": self._entity_compact(related.get("battery")),
                "current": self._presence_current_metrics(presence, motion),
                "measurements": self._presence_measurements(related),
                "today": self._presence_history_metrics(history, role.get("room"), days=1),
                "history_30d": self._presence_history_metrics(history, role.get("room"), days=30),
            })
        return {
            "sensor_family": "Aqara FP300 compatible presence sensor",
            "capabilities": {
                "presence": True,
                "pir_motion": True,
                "illuminance": True,
                "temperature": True,
                "humidity": True,
                "battery": True,
                "presence_duration_calculable": True,
                "stillness_duration_calculable": True,
                "breathing_detection": False,
                "fall_detection": False,
                "sleep_detection": False,
                "posture_detection": False,
                "people_counting": False,
                "zone_tracking": False,
            },
            "interpretation_notes": [
                "presence=true und motion=false über längere Zeit bedeutet nur: Person ist im Raum und bewegt sich kaum.",
                "Stillstand kann Sitzen, Liegen oder ruhiges Verhalten bedeuten und ist keine medizinische Aussage.",
                "Atmung, Sturz, Schlaf und Körperposition dürfen aus diesen Daten nicht abgeleitet werden.",
            ],
            "devices": devices,
        }

    def _related_presence_entities(self, role: dict[str, Any], ha_snapshot: list[dict[str, Any]]) -> dict[str, dict[str, Any] | None]:
        role_entity = str(role.get("entity_id") or "")
        device_id = str(role.get("device_id") or "").strip()
        same_device = [item for item in ha_snapshot if device_id and str(item.get("device_id") or "") == device_id]
        if not same_device:
            prefix = role_entity.rsplit("_", 1)[0] if "_" in role_entity else role_entity.rsplit(".", 1)[-1]
            same_device = [item for item in ha_snapshot if prefix and str(item.get("entity_id") or "").startswith(prefix)]
        return {
            "presence": self._best_entity(same_device, self._is_presence_entity) or (role if self._is_presence_entity(role) else None),
            "motion": self._best_entity(same_device, self._is_motion_entity),
            "illuminance": self._best_entity(same_device, lambda item: self._device_class(item) == "illuminance" or "illuminance" in self._entity_text(item)),
            "temperature": self._best_entity(same_device, lambda item: self._device_class(item) == "temperature" or self._entity_id(item).endswith(("_temperature", "_temperatur"))),
            "humidity": self._best_entity(same_device, lambda item: self._device_class(item) == "humidity" or self._entity_id(item).endswith(("_humidity", "_luftfeuchtigkeit"))),
            "battery": self._best_entity(same_device, lambda item: self._entity_id(item).endswith(("_battery", "_batterie"))),
        }

    def _presence_measurements(self, related: dict[str, dict[str, Any] | None]) -> dict[str, Any]:
        presence = related.get("presence")
        motion = related.get("motion")
        illuminance = related.get("illuminance")
        temperature = related.get("temperature")
        humidity = related.get("humidity")
        battery = related.get("battery")
        return {
            "presence": self._boolean_measurement(presence),
            "pir_motion": self._boolean_measurement(motion),
            "illuminance_lux": self._numeric_measurement(illuminance),
            "temperature_celsius": self._numeric_measurement(temperature),
            "humidity_percent": self._numeric_measurement(humidity),
            "battery_percent": self._numeric_measurement(battery),
        }

    def _presence_current_metrics(self, presence: dict[str, Any] | None, motion: dict[str, Any] | None) -> dict[str, Any]:
        presence_active = self._is_on(presence.get("state") if presence else None)
        motion_active = self._is_on(motion.get("state") if motion else None)
        presence_since = self._parse_time(presence.get("last_changed") or presence.get("last_updated")) if presence else None
        motion_since = self._parse_time(motion.get("last_changed") or motion.get("last_updated")) if motion else None
        current_time = datetime.now(timezone.utc)
        presence_duration = int((current_time - presence_since).total_seconds()) if presence_active and presence_since else 0
        stillness_since = max([value for value in [presence_since, motion_since] if value], default=None)
        stillness_duration = int((current_time - stillness_since).total_seconds()) if presence_active and not motion_active and stillness_since else 0
        return {
            "presence_active": presence_active,
            "motion_active": motion_active,
            "presence_duration_seconds": max(presence_duration, 0),
            "stillness_duration_seconds": max(stillness_duration, 0),
            "interpretation": "person_present_but_still" if presence_active and not motion_active else "motion_detected" if motion_active else "not_present",
        }

    def _presence_history_metrics(self, history: list[dict[str, Any]], room: Any, days: int) -> dict[str, Any]:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        events = [
            event for event in history
            if event.get("room") == room
            and str(event.get("source") or "") == "fp300_snapshot"
            and self._parse_time(event.get("event_time")) >= since
        ]
        presence_events = [event for event in events if str(event.get("role") or "").endswith("_presence")]
        motion_events = [event for event in events if str(event.get("role") or "").endswith("_motion")]
        presence_active_count = sum(1 for event in presence_events if self._is_on(event.get("state")))
        motion_active_count = sum(1 for event in motion_events if self._is_on(event.get("state")))
        still_count = max(presence_active_count - motion_active_count, 0)
        return {
            "sample_count": len(events),
            "presence_samples": len(presence_events),
            "motion_samples": len(motion_events),
            "presence_active_samples": presence_active_count,
            "motion_active_samples": motion_active_count,
            "stillness_samples": still_count,
            "stillness_ratio": round(still_count / presence_active_count, 2) if presence_active_count else 0,
        }

    def _entity_compact(self, item: dict[str, Any] | None) -> dict[str, Any] | None:
        if not item:
            return None
        return {
            "entity_id": item.get("entity_id"),
            "name": item.get("friendly_name") or item.get("label") or item.get("original_name"),
            "state": item.get("state"),
            "numeric_value": self._number(item.get("state")),
            "unit": item.get("unit") or item.get("unit_of_measurement"),
            "device_class": item.get("device_class"),
            "last_changed": item.get("last_changed"),
            "last_updated": item.get("last_updated"),
        }

    def _boolean_measurement(self, item: dict[str, Any] | None) -> dict[str, Any]:
        compact = self._entity_compact(item)
        return {
            "active": self._is_on(item.get("state") if item else None),
            "entity": compact,
        }

    def _numeric_measurement(self, item: dict[str, Any] | None) -> dict[str, Any]:
        compact = self._entity_compact(item)
        return {
            "value": self._number(item.get("state") if item else None),
            "unit": (item.get("unit") or item.get("unit_of_measurement")) if item else None,
            "entity": compact,
        }

    def _best_entity(self, items: list[dict[str, Any]], predicate: Any) -> dict[str, Any] | None:
        matches = [item for item in items if predicate(item)]
        return sorted(matches, key=lambda item: (self._entity_id(item).startswith("binary_sensor."), self._parse_time(item.get("last_updated")).timestamp()), reverse=True)[0] if matches else None

    def _is_presence_role(self, role: dict[str, Any]) -> bool:
        text = self._entity_text(role)
        return str(role.get("role") or "").endswith("presence") or self._is_presence_entity(role) or "occupy" in text

    def _is_presence_entity(self, item: dict[str, Any]) -> bool:
        dc = self._device_class(item)
        text = self._entity_text(item)
        return dc in {"occupancy", "presence"} or any(term in text for term in ["presence", "praesenz", "präsenz", "occupancy", "occupy"])

    def _is_motion_entity(self, item: dict[str, Any]) -> bool:
        dc = self._device_class(item)
        text = self._entity_text(item)
        return dc == "motion" or any(term in text for term in ["motion", "bewegung", "pir_detection", "pir detection", "pir"])

    @staticmethod
    def _device_class(item: dict[str, Any]) -> str:
        return str(item.get("device_class") or "").lower()

    @staticmethod
    def _entity_id(item: dict[str, Any]) -> str:
        return str(item.get("entity_id") or "").lower()

    @staticmethod
    def _entity_text(item: dict[str, Any]) -> str:
        return " ".join(str(item.get(key) or "").lower() for key in ["entity_id", "friendly_name", "label", "original_name", "device_name", "model"])

    @staticmethod
    def _is_on(value: Any) -> bool:
        return str(value or "").strip().lower() in {"on", "true", "detected", "occupied", "home", "present", "1"}

    @staticmethod
    def _number(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(str(value).replace("%", "").replace(",", ".").strip())
        except ValueError:
            return None

    def _compact_roles(self, roles: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "role": role.get("role"),
                "room": role.get("room"),
                "label": role.get("label") or role.get("friendly_name"),
                "state": role.get("state"),
                "reachable": role.get("reachable"),
                "last_changed": role.get("last_changed"),
                "last_updated": role.get("last_updated"),
                "device_class": role.get("device_class"),
            }
            for role in roles
        ]

    def _validate_assessment(self, data: dict[str, Any], raw_text: str) -> dict[str, Any]:
        status = str(data.get("status") or "green").lower()
        if status not in VALID_STATUSES:
            status = "yellow"
        confidence = max(0.0, min(float(data.get("confidence") or 0.0), 1.0))
        return {
            "assessment_time": now(),
            "status": status,
            "confidence": confidence,
            "summary": str(data.get("summary") or "Sentero hat den Tagesablauf bewertet."),
            "findings": self._list(data.get("findings")),
            "recommendation": str(data.get("recommendation") or "Keine Aktion erforderlich."),
            "email_subject": str(data.get("email_subject") or ""),
            "email_body": str(data.get("email_body") or ""),
            "llm_response": raw_text,
        }

    def _row_to_assessment(self, row: Any) -> dict[str, Any]:
        data = dict(row)
        data["findings"] = self._list_json(data.pop("findings_json", "[]"))
        return data

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any]:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
            cleaned = re.sub(r"```$", "", cleaned).strip()
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            cleaned = match.group(0)
        return json.loads(cleaned)

    @staticmethod
    def _list(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item) for item in value if str(item).strip()]
        if value:
            return [str(value)]
        return []

    @staticmethod
    def _list_json(value: Any) -> list[str]:
        try:
            parsed = json.loads(str(value or "[]"))
        except json.JSONDecodeError:
            return []
        return SeniorBehaviorAgent._list(parsed)

    @staticmethod
    def _parse_time(value: Any) -> datetime:
        text = str(value or "").strip()
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            parsed = datetime.now(timezone.utc)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _email_body(summary: str, findings: list[str], recommendation: str) -> str:
        details = "\n".join(f"- {item}" for item in findings) if findings else "- Es wurden Abweichungen vom gewohnten Tagesablauf erkannt."
        return f"{summary}\n\n{details}\n\n{recommendation}"
