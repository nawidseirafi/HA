from datetime import datetime, timezone
from typing import Any, Callable

from backend.services.calendar_service import CalendarService
from backend.services.homeassistant_service import HomeAssistantService
from backend.services.household.comfort_service import HouseholdComfortService
from backend.services.infrastructure_service import InfrastructureService
from backend.services.waste_service import MAILBOX_ENTITY_ID, WasteService


class HouseholdService:
    def __init__(        self,
        ha_service: HomeAssistantService | None = None,
        waste_service: WasteService | None = None,
        infrastructure_service: InfrastructureService | None = None,
        calendar_service: CalendarService | None = None,
        vacation_status_provider: Callable[[], dict[str, Any]] | None = None,
    ) -> None:
        self.ha_service = ha_service or HomeAssistantService()
        self.waste_service = waste_service or WasteService(self.ha_service)
        self.infrastructure_service = infrastructure_service or InfrastructureService(self.ha_service)
        self.calendar_service = calendar_service or CalendarService()
        self.comfort_service = HouseholdComfortService(self.ha_service)
        self.vacation_status_provider = vacation_status_provider

    def status(self) -> dict[str, Any]:
        waste = self._waste_status()
        post = self._post_status()
        vacation = self._vacation_status()
        infrastructure = self._infrastructure_status()
        calendar = self._calendar_status()
        comfort = self._comfort_status()
        reminders = self._reminders(waste, post, vacation, infrastructure)
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
        return {
            "ok": status["ok"],
            "updated_at": status["updated_at"],
            "waste": waste,
            "post": post,
            "vacation": vacation,
            "infrastructure": infrastructure,
            "calendar": calendar,
            "comfort": comfort,
            "reminders": status["reminders"],
            "counts": {
                "reminders": len(status["reminders"]),
                "high_priority": len([item for item in status["reminders"] if item.get("priority") == "high"]),
                "waste_items": len(waste.get("items", [])) if isinstance(waste, dict) else 0,
                "calendar_events_today": int(calendar.get("today_count") or 0) if isinstance(calendar, dict) else 0,
            },
            "state": {
                "mailbox_has_mail": post.get("has_mail"),
                "vacation_mode": vacation.get("vacation_mode"),
                "next_waste": waste.get("next") if isinstance(waste, dict) else None,
                "next_calendar_event": calendar.get("next_event") if isinstance(calendar, dict) else None,
                "infrastructure_status": infrastructure.get("status") if isinstance(infrastructure, dict) else "unknown",
                "bedroom_fan_status": comfort.get("bedroom_fan", {}).get("decision", {}).get("status") if isinstance(comfort, dict) else "unknown",
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
            },
        }

    def comfort_bedroom_fan(self, apply: bool = False, include_ai: bool | None = None) -> dict[str, Any]:
        return self.comfort_service.evaluate_bedroom_fan(apply=apply, include_ai=include_ai)

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
        }

    def _reminders(self, waste: dict[str, Any], post: dict[str, Any], vacation: dict[str, Any], infrastructure: dict[str, Any]) -> list[dict[str, str]]:
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
