from datetime import datetime, timezone
from typing import Any

from backend.services.homeassistant_service import HomeAssistantService


WASTE_ENTITY_ID = "sensor.abfall_naechster_termin"
VACATION_ENTITY_ID = "input_boolean.vacation_mode"
MAILBOX_ENTITY_ID = "input_boolean.post_im_briefkasten"


class WasteServiceError(RuntimeError):
    pass


class WasteService:
    def __init__(self, ha_service: HomeAssistantService | None = None) -> None:
        self.ha_service = ha_service or HomeAssistantService()

    def status(self) -> dict[str, Any]:
        updated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        try:
            raw = self.fetch_ha_state(WASTE_ENTITY_ID)
            normalized = self.normalize(raw)
            context = self.context()
            reminders = self.reminders(normalized.get("items", []), context)
            return {
                "ok": True,
                "updated_at": updated_at,
                "next": normalized.get("next"),
                "items": normalized.get("items", []),
                "context": context,
                "reminders": reminders,
                "source_entity": WASTE_ENTITY_ID,
                "raw": normalized.get("raw"),
            }
        except WasteServiceError as exc:
            return {
                "ok": False,
                "updated_at": updated_at,
                "next": None,
                "items": [],
                "context": self.context(suppress_errors=True),
                "reminders": [],
                "source_entity": WASTE_ENTITY_ID,
                "error": str(exc),
            }

    def next(self) -> dict[str, Any]:
        data = self.status()
        return {
            "ok": data["ok"],
            "updated_at": data["updated_at"],
            "next": data.get("next"),
            "source_entity": WASTE_ENTITY_ID,
            **({"error": data["error"]} if data.get("error") else {}),
        }

    def reminder_status(self) -> dict[str, Any]:
        data = self.status()
        return {
            "ok": data["ok"],
            "updated_at": data["updated_at"],
            "context": data.get("context", {}),
            "reminders": data.get("reminders", []),
            "source_entity": WASTE_ENTITY_ID,
            **({"error": data["error"]} if data.get("error") else {}),
        }

    def fetch_ha_state(self, entity_id: str) -> dict[str, Any]:
        try:
            state = self.ha_service.get_state(entity_id)
        except Exception as exc:
            raise WasteServiceError(str(exc)) from exc
        if state is None:
            raise WasteServiceError(f"Home Assistant Entity nicht gefunden: {entity_id}")
        value = state.get("state")
        if value in {"unknown", "unavailable"}:
            return {
                **state,
                "attributes": state.get("attributes") or {},
                "unavailable": True,
            }
        return {
            **state,
            "attributes": state.get("attributes") or {},
        }

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        attributes = raw.get("attributes") if isinstance(raw.get("attributes"), dict) else {}
        next_data = attributes.get("next") if isinstance(attributes.get("next"), dict) else None
        next_by_type = attributes.get("next_by_type") if isinstance(attributes.get("next_by_type"), dict) else {}
        items = self._items_from_next_by_type(next_by_type)

        if next_data and not any(item.get("date") == next_data.get("date") for item in items):
            items.append(self._item_from_data("Abfall", next_data))

        items = sorted(items, key=lambda item: (self._days_sort_value(item.get("days_until")), item.get("type") or ""))
        next_item = self._pick_next_item(items, next_data)
        return {"next": next_item, "items": items, "raw": raw}

    def context(self, suppress_errors: bool = False) -> dict[str, bool | None]:
        return {
            "vacation_mode": self._optional_boolean(VACATION_ENTITY_ID, suppress_errors=suppress_errors),
            "mailbox_has_mail": self._optional_boolean(MAILBOX_ENTITY_ID, suppress_errors=suppress_errors),
        }

    def reminders(self, items: list[dict[str, Any]], context: dict[str, Any]) -> list[dict[str, str]]:
        reminders: list[dict[str, str]] = []
        upcoming = [
            item
            for item in items
            if isinstance(item.get("days_until"), int) and item["days_until"] in {0, 1}
        ]
        for item in upcoming:
            waste_type = str(item.get("type") or "Müll")
            if item["days_until"] == 0:
                reminders.append({
                    "priority": "medium",
                    "message": f"{waste_type}: Heute Abholung",
                    "reason": "Mülltermin ist heute.",
                })
            if item["days_until"] == 1:
                reminders.append({
                    "priority": "medium",
                    "message": f"{waste_type}: Heute Abend rausstellen",
                    "reason": "Mülltermin ist morgen.",
                })

        if context.get("vacation_mode"):
            vacation_items = [
                item for item in items
                if isinstance(item.get("days_until"), int) and 0 <= item["days_until"] <= 2
            ]
            for item in vacation_items:
                reminders.append({
                    "priority": "high",
                    "message": f"{item.get('type') or 'Müll'} trotz Urlaub beachten",
                    "reason": "Urlaubsmodus aktiv und Mülltermin innerhalb von 2 Tagen.",
                })
            if context.get("mailbox_has_mail"):
                reminders.append({
                    "priority": "medium",
                    "message": "Post im Briefkasten",
                    "reason": "Urlaubsmodus aktiv und Briefkasten meldet Post.",
                })

        return reminders

    def _items_from_next_by_type(self, next_by_type: dict[str, Any]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for waste_type, data in next_by_type.items():
            if isinstance(data, dict):
                items.append(self._item_from_data(str(waste_type), data))
        return items

    def _item_from_data(self, waste_type: str, data: dict[str, Any]) -> dict[str, Any]:
        days_until = self._int_or_none(data.get("days_until"))
        meta = self._type_meta(waste_type)
        return {
            "type": waste_type,
            "date": data.get("date"),
            "date_de": data.get("date_de"),
            "days_until": days_until,
            "label": self._day_label(days_until),
            "icon": meta["icon"],
            "color": meta["color"],
        }

    def _pick_next_item(self, items: list[dict[str, Any]], next_data: dict[str, Any] | None) -> dict[str, Any] | None:
        if not items:
            return None
        if next_data and next_data.get("date"):
            for item in items:
                if item.get("date") == next_data.get("date"):
                    return item
        return items[0]

    def _optional_boolean(self, entity_id: str, suppress_errors: bool = False) -> bool | None:
        try:
            state = self.ha_service.get_state(entity_id)
        except Exception:
            if suppress_errors:
                return None
            return None
        if not state:
            return None
        value = str(state.get("state") or "").lower()
        if value in {"unknown", "unavailable", ""}:
            return None
        return value == "on"

    def _type_meta(self, waste_type: str) -> dict[str, str]:
        value = waste_type.lower()
        if "bio" in value:
            return {"icon": "mdi:leaf", "color": "green"}
        if any(term in value for term in ("papier", "altpapier", "blaue")):
            return {"icon": "mdi:package-variant", "color": "blue"}
        if any(term in value for term in ("gelb", "leicht", "verpackung")):
            return {"icon": "mdi:recycle", "color": "yellow"}
        if "rest" in value:
            return {"icon": "mdi:trash-can", "color": "grey"}
        return {"icon": "mdi:trash-can-outline", "color": "grey"}

    def _day_label(self, days_until: int | None) -> str:
        if days_until is None:
            return "Unbekannt"
        if days_until < 0:
            return "Vergangen"
        if days_until == 0:
            return "Heute"
        if days_until == 1:
            return "Morgen"
        if days_until == 2:
            return "Übermorgen"
        return f"in {days_until} Tagen"

    def _int_or_none(self, value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _days_sort_value(self, value: Any) -> int:
        days = self._int_or_none(value)
        return days if days is not None else 9999
