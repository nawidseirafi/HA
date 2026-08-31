from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from backend.config import load_global_config
from backend.services.calendar_service import CalendarService
from backend.services.homeassistant_service import HomeAssistantService
from backend.services.household.comfort_service import HouseholdComfortService
from backend.services.household.front_light_service import HouseholdFrontLightService
from backend.services.household.garage_service import HouseholdGarageService
from backend.services.household.shutter_service import HouseholdShutterService
from backend.services.infrastructure_service import InfrastructureService
from backend.services.messaging import MessagingService
from backend.services.waste_service import MAILBOX_ENTITY_ID, WasteService


OPENING_DEVICE_CLASSES = {"door", "window", "opening"}
SAFETY_DEVICE_CLASSES = {"smoke", "gas", "carbon_monoxide"}
ACTIVE_SAFETY_STATES = {"on", "detected", "problem", "unsafe"}
WATER_LEAK_DEVICE_CLASSES = {"moisture"}
AIR_QUALITY_DEVICE_CLASSES = {"aqi", "carbon_dioxide", "pm25", "volatile_organic_compounds"}
AIR_QUALITY_THRESHOLDS = {
    "aqi": (100.0, 150.0),
    "carbon_dioxide": (1500.0, 2000.0),
    "pm25": (35.0, 75.0),
    "volatile_organic_compounds": (500.0, 1000.0),
}


class HouseholdService:
    def __init__(
        self,
        ha_service: HomeAssistantService | None = None,
        waste_service: WasteService | None = None,
        infrastructure_service: InfrastructureService | None = None,
        calendar_service: CalendarService | None = None,
        messaging_service: MessagingService | None = None,
        vacation_status_provider: Callable[[], dict[str, Any]] | None = None,
    ) -> None:
        self.ha_service = ha_service or HomeAssistantService()
        self.waste_service = waste_service or WasteService(self.ha_service)
        self.infrastructure_service = infrastructure_service or InfrastructureService(self.ha_service)
        self.calendar_service = calendar_service or CalendarService()
        self.comfort_service = HouseholdComfortService(self.ha_service)
        self.front_light_service = HouseholdFrontLightService(self.ha_service)
        self.garage_service = HouseholdGarageService(self.ha_service)
        self.shutter_service = HouseholdShutterService(self.ha_service)
        self.messaging_service = messaging_service or MessagingService()
        self.config = load_global_config().get("household") or {}
        self.vacation_status_provider = vacation_status_provider

    def status(self) -> dict[str, Any]:
        waste = self._waste_status()
        post = self._post_status()
        vacation = self._vacation_status()
        infrastructure = self._infrastructure_status()
        calendar = self._calendar_status()
        comfort = self._comfort_status()
        openings = self.openings_status()
        safety = self.safety_status()
        reminders = self._reminders(waste, post, vacation, infrastructure, openings, safety)
        return {
            "ok": not any(item.get("priority") == "critical" for item in reminders),
            "updated_at": self._now(),
            "home_assistant": {
                "configured": self.ha_service.configured(),
            },
            "waste": waste,
            "post": post,
            "vacation": vacation,
            "infrastructure": infrastructure,
            "calendar": calendar,
            "comfort": comfort,
            "openings": openings,
            "safety": safety,
            "reminders": reminders,
        }

    def summary(self) -> dict[str, Any]:
        status = self.status()
        waste = status["waste"]
        post = status["post"]
        vacation = status["vacation"]
        infrastructure = status["infrastructure"]
        calendar = status["calendar"]
        comfort = status["comfort"]
        openings = status["openings"]
        safety = status["safety"]
        return {
            "ok": status["ok"],
            "updated_at": status["updated_at"],
            "waste": waste,
            "post": post,
            "vacation": vacation,
            "infrastructure": infrastructure,
            "calendar": calendar,
            "comfort": comfort,
            "openings": openings,
            "safety": safety,
            "reminders": status["reminders"],
            "counts": {
                "reminders": len(status["reminders"]),
                "high_priority": len([item for item in status["reminders"] if item.get("priority") == "high"]),
                "waste_items": len(waste.get("items", [])) if isinstance(waste, dict) else 0,
                "calendar_events_today": int(calendar.get("today_count") or 0) if isinstance(calendar, dict) else 0,
                "openings_open": len(openings.get("open", [])) if isinstance(openings, dict) else 0,
                "safety_alerts": len(safety.get("active_alerts", [])) if isinstance(safety, dict) else 0,
            },
            "state": {
                "mailbox_has_mail": post.get("has_mail"),
                "vacation_mode": vacation.get("vacation_mode"),
                "next_waste": waste.get("next") if isinstance(waste, dict) else None,
                "next_calendar_event": calendar.get("next_event") if isinstance(calendar, dict) else None,
                "infrastructure_status": infrastructure.get("status") if isinstance(infrastructure, dict) else "unknown",
                "bedroom_fan_status": comfort.get("bedroom_fan", {}).get("decision", {}).get("status") if isinstance(comfort, dict) else "unknown",
                "openings_open": len(openings.get("open", [])) if isinstance(openings, dict) else 0,
                "safety_alerts": len(safety.get("active_alerts", [])) if isinstance(safety, dict) else 0,
            },
        }

    def reminders(self) -> dict[str, Any]:
        status = self.status()
        return {
            "ok": status["ok"],
            "updated_at": status["updated_at"],
            "reminders": status["reminders"],
            "context": {
                "mailbox_has_mail": status["post"].get("has_mail"),
                "vacation_mode": status["vacation"].get("vacation_mode"),
                "infrastructure_status": status["infrastructure"].get("status"),
                "openings_open": len(status.get("openings", {}).get("open", [])) if isinstance(status.get("openings"), dict) else 0,
                "safety_alerts": len(status.get("safety", {}).get("active_alerts", [])) if isinstance(status.get("safety"), dict) else 0,
            },
        }

    def check_alerts(self, notify: bool = True) -> dict[str, Any]:
        alerts = self.alerts_status()
        active_alerts = alerts.get("active_alerts", []) if isinstance(alerts, dict) else []
        delivered: list[dict[str, Any]] = []
        suppressed: list[dict[str, Any]] = []
        for alert in active_alerts:
            signature = str(alert.get("signature") or "")
            if not signature:
                continue
            if self._recent_alert_message_exists(signature):
                suppressed.append({"signature": signature, "reason": "deduplicated"})
                continue
            channels = self._alert_channels(alert) if notify else ["message_center"]
            message = self.messaging_service.create_message(
                source="household",
                category=str(alert.get("category") or "household"),
                severity=str(alert.get("severity") or "warning"),
                title=str(alert.get("title") or "Haushaltsalarm"),
                message=str(alert.get("message") or ""),
                payload={"kind": "household_alert", "signature": signature, "channels": channels, "alert": alert},
            )
            channel_results = {"message_center": {"ok": True, "message_id": message.get("id")}}
            if notify and "mobile_push" in channels:
                channel_results["mobile_push"] = self._send_alert_push(alert)
            if notify and "telegram" in channels:
                channel_results["telegram"] = self._send_alert_telegram(alert)
            delivered.append({"signature": signature, "channels": channels, "results": channel_results})
        return {
            "ok": not any(str(item.get("severity") or "") == "critical" for item in active_alerts),
            "updated_at": alerts.get("updated_at") if isinstance(alerts, dict) else self._now(),
            "active_alerts": active_alerts,
            "delivered": delivered,
            "suppressed": suppressed,
            "notified": bool(delivered),
        }

    def alerts_status(self) -> dict[str, Any]:
        updated_at = self._now()
        try:
            states = self.ha_service.get_states()
        except Exception as exc:
            return {"ok": False, "updated_at": updated_at, "active_alerts": [], "error": str(exc)}
        alerts: list[dict[str, Any]] = []
        for state in states:
            safety = self._safety_alert(state)
            if safety:
                alerts.append(safety)
                continue
            water = self._water_leak_alert(state)
            if water:
                alerts.append(water)
                continue
            air = self._air_quality_alert(state)
            if air:
                alerts.append(air)
        alerts.sort(key=lambda item: (0 if item.get("severity") == "critical" else 1, item.get("title") or ""))
        return {
            "ok": not any(str(item.get("severity") or "") == "critical" for item in alerts),
            "updated_at": updated_at,
            "active_alerts": alerts,
        }

    def comfort_bedroom_fan(self, apply: bool = False, include_ai: bool | None = None) -> dict[str, Any]:
        return self.comfort_service.evaluate_bedroom_fan(apply=apply, include_ai=include_ai)

    def front_light_on_arrival(self, apply: bool = False) -> dict[str, Any]:
        return self.front_light_service.evaluate(apply=apply)

    def garage_context_control(self, apply: bool = False) -> dict[str, Any]:
        return self.garage_service.evaluate(apply=apply)

    def ground_floor_shutters_context_control(self, apply: bool = False) -> dict[str, Any]:
        return self.shutter_service.evaluate(apply=apply)

    def openings_status(self) -> dict[str, Any]:
        updated_at = self._now()
        try:
            states = self.ha_service.get_states()
        except Exception as exc:
            return {"ok": False, "updated_at": updated_at, "total": 0, "open": [], "error": str(exc)}
        openings = [self._opening_entity(state) for state in states if self._is_opening_state(state)]
        open_items = [item for item in openings if item["open"]]
        return {
            "ok": True,
            "updated_at": updated_at,
            "total": len(openings),
            "open": open_items,
        }

    def safety_status(self) -> dict[str, Any]:
        updated_at = self._now()
        try:
            states = self.ha_service.get_states()
        except Exception as exc:
            return {"ok": False, "updated_at": updated_at, "total": 0, "detectors": [], "active_alerts": [], "offline": [], "error": str(exc)}
        detectors = [self._safety_entity(state) for state in states if self._is_safety_state(state)]
        active_alerts = [item for item in detectors if item["active"]]
        offline = [item for item in detectors if str(item.get("state") or "").lower() in {"unavailable", "unknown"}]
        return {
            "ok": not active_alerts,
            "updated_at": updated_at,
            "total": len(detectors),
            "detectors": detectors,
            "active_alerts": active_alerts,
            "offline": offline,
        }

    def check_openings(self, notify: bool = True) -> dict[str, Any]:
        openings = self.openings_status()
        open_items = openings.get("open", []) if isinstance(openings, dict) else []
        if not openings.get("ok") or not open_items:
            return {"ok": bool(openings.get("ok")), "notified": False, "openings": openings}

        signature = ",".join(sorted(str(item.get("entity_id") or "") for item in open_items))
        title = self._openings_title(open_items)
        message = self._openings_message(open_items)
        if notify and not self._recent_openings_message_exists(signature):
            self.messaging_service.create_message(
                source="household",
                category="security",
                severity="warning",
                title=title,
                message=message,
                payload={"kind": "openings_check", "signature": signature, "openings": open_items},
            )
            self._send_openings_push(title, message, signature)
            return {"ok": True, "notified": True, "openings": openings}
        return {"ok": True, "notified": False, "openings": openings}

    def _waste_status(self) -> dict[str, Any]:
        try:
            return self.waste_service.status()
        except Exception as exc:
            return {
                "ok": False,
                "updated_at": self._now(),
                "next": None,
                "items": [],
                "context": {},
                "reminders": [],
                "source_entity": "",
                "error": str(exc),
            }

    def _post_status(self) -> dict[str, Any]:
        try:
            entity = self.ha_service.fetch_entity_state(MAILBOX_ENTITY_ID)
        except Exception as exc:
            return {
                "ok": False,
                "entity_id": MAILBOX_ENTITY_ID,
                "has_mail": None,
                "entity": None,
                "error": str(exc),
            }
        if not entity:
            return {
                "ok": True,
                "entity_id": MAILBOX_ENTITY_ID,
                "has_mail": None,
                "entity": None,
            }
        return {
            "ok": True,
            "entity_id": MAILBOX_ENTITY_ID,
            "has_mail": str(entity.get("state") or "").lower() == "on",
            "entity": self._simple_entity(entity),
        }

    def _vacation_status(self) -> dict[str, Any]:
        if not self.vacation_status_provider:
            return {"ok": True, "available": False, "vacation_mode": None}
        try:
            status = self.vacation_status_provider()
        except Exception as exc:
            return {"ok": False, "available": False, "vacation_mode": None, "error": str(exc)}
        return {
            "ok": True,
            "available": True,
            **status,
        }

    def _infrastructure_status(self) -> dict[str, Any]:
        try:
            return self.infrastructure_service.summary()
        except Exception as exc:
            return {
                "ok": False,
                "updated_at": self._now(),
                "status": "unknown",
                "label": "Unbekannt",
                "detail": "Infrastructure Status nicht verfügbar",
                "router": "Fritzbox",
                "connected_devices": None,
                "wifi": "unknown",
                "checks": {},
                "error": str(exc),
            }

    def _calendar_status(self) -> dict[str, Any]:
        try:
            return self.calendar_service.today_summary()
        except Exception as exc:
            return {
                "ok": False,
                "updated_at": self._now(),
                "today_count": 0,
                "next_event": None,
                "upcoming": [],
                "source": "stub",
                "error": str(exc),
            }

    def _comfort_status(self) -> dict[str, Any]:
        return {
            "bedroom_fan": self.comfort_service.bedroom_fan_status(include_ai=False),
            "front_light": self.front_light_service.status(),
            "garage": self.garage_service.status(),
            "ground_floor_shutters": self.shutter_service.status(),
        }

    def _reminders(
        self,
        waste: dict[str, Any],
        post: dict[str, Any],
        vacation: dict[str, Any],
        infrastructure: dict[str, Any],
        openings: dict[str, Any] | None = None,
        safety: dict[str, Any] | None = None,
    ) -> list[dict[str, str]]:
        reminders: list[dict[str, str]] = []
        for item in waste.get("reminders", []) if isinstance(waste, dict) else []:
            if isinstance(item, dict):
                reminders.append({
                    "priority": str(item.get("priority") or "medium"),
                    "message": str(item.get("message") or ""),
                    "reason": str(item.get("reason") or "Abfallstatus"),
                    "source": "waste",
                })

        if post.get("has_mail") is True:
            reminders.append({
                "priority": "medium",
                "message": "Post im Briefkasten",
                "reason": "Briefkasten meldet Post.",
                "source": "post",
            })

        if vacation.get("vacation_mode") is True and post.get("has_mail") is True:
            reminders.append({
                "priority": "high",
                "message": "Post trotz Urlaubsmodus beachten",
                "reason": "Urlaubsmodus ist aktiv und Briefkasten meldet Post.",
                "source": "household",
            })

        open_items = openings.get("open", []) if isinstance(openings, dict) else []
        if open_items:
            reminders.append({
                "priority": "high",
                "message": self._openings_title(open_items),
                "reason": self._openings_message(open_items),
                "source": "household",
            })

        active_alerts = safety.get("active_alerts", []) if isinstance(safety, dict) else []
        if active_alerts:
            reminders.append({
                "priority": "critical",
                "message": self._safety_title(active_alerts),
                "reason": self._safety_message(active_alerts),
                "source": "household",
            })

        for item in vacation.get("reminders", []) if isinstance(vacation, dict) else []:
            if isinstance(item, dict):
                reminders.append({
                    "priority": str(item.get("severity") or "medium"),
                    "message": str(item.get("title") or item.get("message") or "Vacation Reminder"),
                    "reason": str(item.get("message") or item.get("reminder_type") or "Vacation-Agent Reminder"),
                    "source": "vacation",
                })

        infrastructure_status = str(infrastructure.get("status") or "")
        if infrastructure_status in {"down", "critical"}:
            reminders.append({
                "priority": "high",
                "message": "Internet oder Netzwerk gestört",
                "reason": str(infrastructure.get("subtitle") or infrastructure.get("detail") or "Infrastructure Status meldet Störung."),
                "source": "infrastructure",
            })
        elif infrastructure_status in {"unstable", "warning"}:
            reminders.append({
                "priority": "medium",
                "message": "Internet oder Netzwerk instabil",
                "reason": str(infrastructure.get("subtitle") or infrastructure.get("detail") or "Infrastructure Status meldet Instabilität."),
                "source": "infrastructure",
            })

        for section, source in ((waste, "waste"), (post, "post"), (vacation, "vacation"), (infrastructure, "infrastructure")):
            error = section.get("error") if isinstance(section, dict) else None
            if error:
                reminders.append({
                    "priority": "low",
                    "message": f"{source} Status eingeschraenkt",
                    "reason": str(error),
                    "source": source,
                })

        return reminders

    def _is_opening_state(self, state: dict[str, Any]) -> bool:
        attributes = state.get("attributes") if isinstance(state.get("attributes"), dict) else {}
        entity_id = str(state.get("entity_id") or "")
        device_class = str(attributes.get("device_class") or "").lower()
        return entity_id.startswith("binary_sensor.") and device_class in OPENING_DEVICE_CLASSES

    def _is_safety_state(self, state: dict[str, Any]) -> bool:
        attributes = state.get("attributes") if isinstance(state.get("attributes"), dict) else {}
        entity_id = str(state.get("entity_id") or "")
        device_class = str(attributes.get("device_class") or "").lower()
        haystack = f"{entity_id} {attributes.get('friendly_name') or ''}".lower()
        return entity_id.startswith("binary_sensor.") and (
            device_class in SAFETY_DEVICE_CLASSES
            or any(token in haystack for token in ("rauch", "smoke", "gas", "co_melder", "kohlenmonoxid", "carbon_monoxide"))
        )

    def _safety_alert(self, state: dict[str, Any]) -> dict[str, Any] | None:
        if not self._is_safety_state(state):
            return None
        item = self._safety_entity(state)
        if not item["active"]:
            return None
        return {
            "kind": "safety",
            "category": "security",
            "severity": "critical",
            "signature": f"safety:{item.get('entity_id')}:{item.get('state')}",
            "title": self._safety_title([item]),
            "message": self._safety_message([item]),
            "entity": item,
        }

    def _water_leak_alert(self, state: dict[str, Any]) -> dict[str, Any] | None:
        if not self._is_water_leak_state(state):
            return None
        item = self._simple_entity(state)
        if str(item.get("state") or "").lower() not in ACTIVE_SAFETY_STATES | {"wet", "moist"}:
            return None
        return {
            "kind": "water_leak",
            "category": "security",
            "severity": "critical",
            "signature": f"water_leak:{item.get('entity_id')}:{item.get('state')}",
            "title": "Wasserleck erkannt",
            "message": f"Aktiv: {item.get('name') or item.get('entity_id') or 'Wassersensor'}",
            "entity": item,
        }

    def _air_quality_alert(self, state: dict[str, Any]) -> dict[str, Any] | None:
        attributes = state.get("attributes") if isinstance(state.get("attributes"), dict) else {}
        if not str(state.get("entity_id") or "").startswith("sensor."):
            return None
        device_class = str(attributes.get("device_class") or "").lower()
        haystack = f"{state.get('entity_id') or ''} {attributes.get('friendly_name') or ''}".lower()
        inferred_class = device_class
        if not inferred_class:
            if "co2" in haystack or "carbon dioxide" in haystack:
                inferred_class = "carbon_dioxide"
            elif "pm2" in haystack or "feinstaub" in haystack:
                inferred_class = "pm25"
            elif "voc" in haystack:
                inferred_class = "volatile_organic_compounds"
            elif "aqi" in haystack or "luftqual" in haystack or "air quality" in haystack:
                inferred_class = "aqi"
        if inferred_class not in AIR_QUALITY_DEVICE_CLASSES:
            return None
        value = self._numeric_state(state)
        if value is None:
            return None
        warning, critical = AIR_QUALITY_THRESHOLDS.get(inferred_class, (100.0, 150.0))
        if value < warning:
            return None
        item = self._simple_entity(state)
        severity = "critical" if value >= critical else "warning"
        unit = item.get("unit") or ""
        return {
            "kind": "air_quality",
            "category": "environment",
            "severity": severity,
            "signature": f"air_quality:{item.get('entity_id')}:{severity}",
            "title": "Luftqualität kritisch" if severity == "critical" else "Luftqualität auffällig",
            "message": f"{item.get('name') or item.get('entity_id')}: {value:g} {unit}".strip(),
            "entity": {**item, "value": value, "air_quality_class": inferred_class},
        }

    def _is_water_leak_state(self, state: dict[str, Any]) -> bool:
        attributes = state.get("attributes") if isinstance(state.get("attributes"), dict) else {}
        entity_id = str(state.get("entity_id") or "")
        device_class = str(attributes.get("device_class") or "").lower()
        haystack = f"{entity_id} {attributes.get('friendly_name') or ''}".lower()
        return entity_id.startswith("binary_sensor.") and (
            device_class in WATER_LEAK_DEVICE_CLASSES
            or any(token in haystack for token in ("wasser", "water", "leck", "leak", "moisture", "feucht"))
        )

    def _opening_entity(self, state: dict[str, Any]) -> dict[str, Any]:
        item = self._simple_entity(state)
        item["open"] = str(state.get("state") or "").lower() == "on"
        item["last_changed"] = state.get("last_changed")
        item["last_updated"] = state.get("last_updated")
        return item

    def _safety_entity(self, state: dict[str, Any]) -> dict[str, Any]:
        item = self._simple_entity(state)
        item["active"] = str(state.get("state") or "").lower() in ACTIVE_SAFETY_STATES
        item["last_changed"] = state.get("last_changed")
        item["last_updated"] = state.get("last_updated")
        return item

    def _safety_title(self, active_alerts: list[dict[str, Any]]) -> str:
        count = len(active_alerts)
        if count == 1:
            device_class = str(active_alerts[0].get("device_class") or "").lower()
            if device_class == "carbon_monoxide":
                return "CO-Alarm erkannt"
            if device_class == "gas":
                return "Gas-Alarm erkannt"
            return "Rauchalarm erkannt"
        return f"{count} Sicherheitsalarme erkannt"

    def _safety_message(self, active_alerts: list[dict[str, Any]]) -> str:
        names = [str(item.get("name") or item.get("entity_id") or "Melder") for item in active_alerts[:5]]
        suffix = f" und {len(active_alerts) - 5} weitere" if len(active_alerts) > 5 else ""
        return "Aktiv: " + ", ".join(names) + suffix

    def _openings_title(self, open_items: list[dict[str, Any]]) -> str:
        count = len(open_items)
        if count == 1:
            return "Fenster oder Tür offen"
        return f"{count} Fenster oder Türen offen"

    def _openings_message(self, open_items: list[dict[str, Any]]) -> str:
        names = [str(item.get("name") or item.get("entity_id") or "Kontakt") for item in open_items[:5]]
        suffix = f" und {len(open_items) - 5} weitere" if len(open_items) > 5 else ""
        return "Offen: " + ", ".join(names) + suffix

    def _recent_openings_message_exists(self, signature: str) -> bool:
        for message in self.messaging_service.get_messages_by_source("household", limit=20):
            payload = message.get("payload") if isinstance(message.get("payload"), dict) else {}
            if payload.get("kind") == "openings_check" and payload.get("signature") == signature and not message.get("read"):
                return True
        return False

    def _recent_alert_message_exists(self, signature: str) -> bool:
        notifications = self.config.get("notifications") if isinstance(self.config.get("notifications"), dict) else {}
        cooldown_minutes = self._int_config(notifications.get("alert_dedupe_minutes"), 30, minimum=1)
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=cooldown_minutes)
        for message in self.messaging_service.get_messages_by_source("household", limit=100):
            payload = message.get("payload") if isinstance(message.get("payload"), dict) else {}
            if payload.get("kind") != "household_alert" or payload.get("signature") != signature:
                continue
            if not message.get("read"):
                return True
            try:
                created_at = datetime.fromisoformat(str(message.get("created_at") or ""))
            except ValueError:
                return True
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            if created_at >= cutoff:
                return True
        return False

    def _alert_channels(self, alert: dict[str, Any]) -> list[str]:
        notifications = self.config.get("notifications") if isinstance(self.config.get("notifications"), dict) else {}
        channels = ["message_center"]
        severity = str(alert.get("severity") or "warning")
        away = self._house_is_away()
        if severity == "critical" or away:
            if notifications.get("alert_push_enabled", True) is not False:
                channels.append("mobile_push")
            if notifications.get("alert_telegram_enabled", True) is not False:
                channels.append("telegram")
        return channels

    def _send_alert_push(self, alert: dict[str, Any]) -> dict[str, Any]:
        notifications = self.config.get("notifications") if isinstance(self.config.get("notifications"), dict) else {}
        notify_service = str(notifications.get("notify_service") or "notify.mobile_app_system_error_404").strip()
        if not notify_service:
            return {"ok": False, "skipped": "missing_notify_service"}
        try:
            result = self.ha_service.call_service(
                "notify",
                notify_service.replace("notify.", ""),
                {
                    "title": str(alert.get("title") or "Haushaltsalarm"),
                    "message": str(alert.get("message") or ""),
                    "data": {
                        "tag": str(alert.get("signature") or "household_alert"),
                        "group": "household",
                        "priority": str(alert.get("severity") or "warning"),
                    },
                },
            )
            return {"ok": True, "result": result}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _send_alert_telegram(self, alert: dict[str, Any]) -> dict[str, Any]:
        try:
            from backend.agents.telegram.service import TelegramService

            return TelegramService().send_notification(
                title=str(alert.get("title") or "Haushaltsalarm"),
                message=str(alert.get("message") or ""),
                severity=str(alert.get("severity") or "warning"),
            )
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _send_openings_push(self, title: str, message: str, signature: str) -> None:
        notifications = self.config.get("notifications") if isinstance(self.config.get("notifications"), dict) else {}
        if notifications.get("openings_push_enabled", True) is False:
            return
        notify_service = str(notifications.get("notify_service") or "notify.mobile_app_system_error_404").strip()
        if not notify_service:
            return
        try:
            self.ha_service.call_service(
                "notify",
                notify_service.replace("notify.", ""),
                {"title": title, "message": message, "data": {"tag": "household_openings", "group": "household", "signature": signature}},
            )
        except Exception:
            # Message Center remains the reliable local notification channel.
            return

    def _house_is_away(self) -> bool:
        auth = load_global_config().get("auth") or {}
        away = auth.get("away_reauth") if isinstance(auth.get("away_reauth"), dict) else {}
        entity_id = str(away.get("presence_entity") or "").strip()
        home_states = {str(item).lower() for item in away.get("home_states", ["home"]) if str(item).strip()} if isinstance(away.get("home_states", ["home"]), list) else {"home"}
        if not entity_id:
            return False
        try:
            state = self.ha_service.fetch_entity_state(entity_id)
        except Exception:
            return False
        value = str((state or {}).get("state") or "").lower()
        return bool(value and value not in home_states)

    def _simple_entity(self, state: dict[str, Any]) -> dict[str, Any]:
        attributes = state.get("attributes") if isinstance(state.get("attributes"), dict) else {}
        return {
            "entity_id": state.get("entity_id"),
            "name": attributes.get("friendly_name") or str(state.get("entity_id") or "").replace("_", " "),
            "state": state.get("state"),
            "area": attributes.get("area") or attributes.get("area_id") or "",
            "device_class": attributes.get("device_class"),
            "unit": attributes.get("unit_of_measurement"),
        }

    def _numeric_state(self, state: dict[str, Any]) -> float | None:
        try:
            return float(str(state.get("state") or "").replace(",", "."))
        except (TypeError, ValueError):
            return None

    def _int_config(self, value: Any, fallback: int, minimum: int = 0) -> int:
        try:
            return max(int(value), minimum)
        except (TypeError, ValueError):
            return fallback

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")
