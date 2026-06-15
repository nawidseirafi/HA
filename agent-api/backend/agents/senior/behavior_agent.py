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
        profile = self._profile()
        contacts = self._contacts()
        sensor_snapshot = self.mapping.roles(dev=True, include_state=True)
        if not dry_run:
            self._record_snapshot(sensor_snapshot)
        history = self._history(days=30)
        payload = self._analysis_payload(profile, contacts, sensor_snapshot, history)
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

    def _record_snapshot(self, roles: list[dict[str, Any]]) -> None:
        timestamp = now()
        with self.mapping.connect() as con:
            for role in roles:
                state = role.get("state")
                if state in (None, "", "unknown", "unavailable"):
                    continue
                con.execute(
                    """insert into senior_sensor_events
                       (event_time, role, room, entity_id, state, device_class, source, created_at)
                       values (?, ?, ?, ?, ?, ?, 'snapshot', ?)""",
                    (
                        role.get("last_changed") or role.get("last_updated") or timestamp,
                        role.get("role"),
                        role.get("room"),
                        role.get("entity_id"),
                        state,
                        role.get("device_class"),
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
            "deviations": self._deviations(today_events, previous_events, sensor_snapshot),
            "safety_rules": {
                "no_medical_diagnosis": True,
                "no_emergency_calls": True,
                "only_behavioral_anomaly_detection": True,
            },
        }

    def _assess(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            client = create_llm_client()
            response = client.generate(
                prompt=(
                    "Bewerte diesen Sentero Tagesablauf. Nutze historische Routinen stärker als einzelne Sensorwerte. "
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
