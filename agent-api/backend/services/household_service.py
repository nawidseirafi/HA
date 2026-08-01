from datetime import datetime, timezone
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


class HouseholdService:
    def __init__(        self,
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
        reminders = self._reminders(waste, post, vacation, infrastructure, openings)
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
            "reminders": status["reminders"],
            "counts": {
                "reminders": len(status["reminders"]),
                "high_priority": len([item for item in status["reminders"] if item.get("priority") == "high"]),
                "waste_items": len(waste.get("items", [])) if isinstance(waste, dict) else 0,
                "calendar_events_today": int(calendar.get("today_count") or 0) if isinstance(calendar, dict) else 0,
                "openings_open": len(openings.get("open", [])) if isinstance(openings, dict) else 0,
            },
            "state": {
                "mailbox_has_mail": post.get("has_mail"),
                "vacation_mode": vacation.get("vacation_mode"),
                "next_waste": waste.get("next") if isinstance(waste, dict) else None,
                "next_calendar_event": calendar.get("next_event") if isinstance(calendar, dict) else None,
                "infrastructure_status": infrastructure.get("status") if isinstance(infrastructure, dict) else "unknown",
                "bedroom_fan_status": comfort.get("bedroom_fan", {}).get("decision", {}).get("status") if isinstance(comfort, dict) else "unknown",
                "openings_open": len(openings.get("open", [])) if isinstance(openings, dict) else 0,
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
            },
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

    def _reminders(self, waste: dict[str, Any], post: dict[str, Any], vacation: dict[str, Any], infrastructure: dict[str, Any], openings: dict[str, Any] | None = None) -> list[dict[str, str]]:
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

    def _opening_entity(self, state: dict[str, Any]) -> dict[str, Any]:
        item = self._simple_entity(state)
        item["open"] = str(state.get("state") or "").lower() == "on"
        item["last_changed"] = state.get("last_changed")
        item["last_updated"] = state.get("last_updated")
        return item

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

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")
