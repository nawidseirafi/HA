from datetime import datetime, timezone
from typing import Any

from backend.config import load_global_config
from backend.services.homeassistant_service import HomeAssistantService


ENTITY_KEYS = ("internet_status", "fritzbox_status", "connected_devices", "wifi_status")


class InfrastructureService:
    def __init__(self, ha_service: HomeAssistantService | None = None, config: dict[str, Any] | None = None) -> None:
        self.ha_service = ha_service or HomeAssistantService()
        self.config = config if config is not None else load_global_config()

    def status(self) -> dict[str, Any]:
        entities = self._configured_entities()
        checks = {key: self._read_entity(key, entities.get(key)) for key in ENTITY_KEYS}
        if not any(check.get("configured") for check in checks.values()):
            checks.update(self._discover_checks())
        summary = self._summary_from_checks(checks)
        return {
            "ok": summary["status"] not in {"down"},
            "updated_at": self._now(),
            "home_assistant": {
                "configured": self.ha_service.configured(),
            },
            "configured_entities": entities,
            "checks": checks,
            "summary": summary,
        }

    def summary(self) -> dict[str, Any]:
        data = self.status()
        return {
            "ok": data["ok"],
            "updated_at": data["updated_at"],
            "status": data["summary"]["status"],
            "label": data["summary"]["label"],
            "detail": data["summary"]["detail"],
            "router": data["summary"]["router"],
            "connected_devices": data["summary"]["connected_devices"],
            "wifi": data["summary"]["wifi"],
            "checks": data["checks"],
        }

    def _configured_entities(self) -> dict[str, str]:
        household_entities = ((self.config.get("household") or {}).get("entities") or {})
        infrastructure_entities = ((self.config.get("infrastructure") or {}).get("entities") or {})
        merged = {**household_entities, **infrastructure_entities}
        return {
            key: self._first_entity_id(merged.get(key))
            for key in ENTITY_KEYS
        }

    def _first_entity_id(self, value: Any) -> str:
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, list):
            for item in value:
                text = str(item or "").strip()
                if text:
                    return text
        return ""

    def _read_entity(self, key: str, entity_id: str | None) -> dict[str, Any]:
        clean_entity_id = str(entity_id or "").strip()
        if not clean_entity_id:
            return {
                "key": key,
                "configured": False,
                "entity_id": "",
                "status": "unknown",
                "value": None,
                "label": "Nicht konfiguriert",
            }
        try:
            state = self.ha_service.fetch_entity_state(clean_entity_id)
        except Exception as exc:
            return {
                "key": key,
                "configured": True,
                "entity_id": clean_entity_id,
                "status": "unknown",
                "value": None,
                "label": "Nicht verfügbar",
                "error": str(exc),
            }
        if not state:
            return {
                "key": key,
                "configured": True,
                "entity_id": clean_entity_id,
                "status": "unknown",
                "value": None,
                "label": "Unbekannt",
            }
        value = state.get("state")
        attributes = state.get("attributes") if isinstance(state.get("attributes"), dict) else {}
        return {
            "key": key,
            "configured": True,
            "entity_id": clean_entity_id,
            "status": self._status_for(key, value),
            "value": value,
            "label": attributes.get("friendly_name") or clean_entity_id,
            "unit": attributes.get("unit_of_measurement"),
            "attributes": self._safe_attributes(attributes),
        }

    def _discover_checks(self) -> dict[str, dict[str, Any]]:
        try:
            states = self.ha_service.get_states()
        except Exception:
            return {}
        if not isinstance(states, list):
            return {}
        return {
            key: self._check_from_state(key, state)
            for key, state in {
                "internet_status": self._find_state(states, (("internet",), ("wan",), ("dsl",), ("connection",), ("verbindung",))),
                "fritzbox_status": self._find_state(states, (("fritz",), ("fritzbox",), ("router",))),
                "connected_devices": self._find_state(states, (("connected", "devices"), ("verbundene", "geräte"), ("verbundene", "geraete"), ("clients",), ("devices",))),
                "wifi_status": self._find_state(states, (("wifi",), ("wlan",))),
            }.items()
            if state
        }

    def _find_state(self, states: list[dict[str, Any]], needle_groups: tuple[tuple[str, ...], ...]) -> dict[str, Any] | None:
        candidates = []
        for state in states:
            if not isinstance(state, dict):
                continue
            entity_id = str(state.get("entity_id") or "")
            attributes = state.get("attributes") if isinstance(state.get("attributes"), dict) else {}
            friendly_name = str(attributes.get("friendly_name") or "")
            text = f"{entity_id} {friendly_name}".lower()
            if any(all(needle in text for needle in needles) for needles in needle_groups):
                candidates.append(state)
        if not candidates:
            return None
        return sorted(candidates, key=self._discovery_rank)[0]

    def _discovery_rank(self, state: dict[str, Any]) -> tuple[int, int]:
        entity_id = str(state.get("entity_id") or "").lower()
        value = str(state.get("state") or "").lower()
        unknown = 1 if value in {"", "unknown", "unavailable", "none"} else 0
        preferred_domain = 0 if entity_id.startswith(("binary_sensor.", "sensor.", "switch.")) else 1
        return (unknown, preferred_domain)

    def _check_from_state(self, key: str, state: dict[str, Any]) -> dict[str, Any]:
        entity_id = str(state.get("entity_id") or "")
        value = state.get("state")
        attributes = state.get("attributes") if isinstance(state.get("attributes"), dict) else {}
        return {
            "key": key,
            "configured": False,
            "discovered": True,
            "entity_id": entity_id,
            "status": self._status_for(key, value),
            "value": value,
            "label": attributes.get("friendly_name") or entity_id,
            "unit": attributes.get("unit_of_measurement"),
            "attributes": self._safe_attributes(attributes),
        }

    def _summary_from_checks(self, checks: dict[str, dict[str, Any]]) -> dict[str, Any]:
        internet = checks["internet_status"]
        fritzbox = checks["fritzbox_status"]
        wifi = checks["wifi_status"]
        devices = checks["connected_devices"]
        status = self._overall_status([internet, fritzbox, wifi])
        device_value = devices.get("value")
        device_count = self._int_or_none(device_value)
        router_label = self._router_label(fritzbox)
        details = [
            f"{device_count} Geräte" if device_count is not None else "",
            f"WLAN {self._label_for_status(wifi.get('status'))}" if wifi.get("status") != "unknown" else "",
        ]
        return {
            "status": status,
            "label": self._label_for_status(status),
            "detail": " · ".join([item for item in details if item]) or router_label,
            "router": router_label,
            "connected_devices": device_count,
            "wifi": wifi.get("status", "unknown"),
        }

    def _overall_status(self, checks: list[dict[str, Any]]) -> str:
        statuses = [
            str(check.get("status") or "unknown")
            for check in checks
            if check.get("configured") or check.get("discovered")
        ]
        if not statuses:
            return "unknown"
        if "down" in statuses:
            return "down"
        if "unstable" in statuses:
            return "unstable"
        if any(status == "ok" for status in statuses):
            return "ok"
        return "unknown"

    def _status_for(self, key: str, value: Any) -> str:
        if key == "connected_devices":
            return "ok" if self._int_or_none(value) is not None else "unknown"
        text = str(value or "").strip().lower()
        if text in {"", "unknown", "unavailable", "none"}:
            return "unknown"
        if any(term in text for term in ("disconnect", "offline", "down", "off", "failed", "problem", "gestört", "stoer", "fehler")):
            return "down"
        if any(term in text for term in ("unstable", "instabil", "limited", "warning", "warn", "reconnect", "packet", "loss")):
            return "unstable"
        if any(term in text for term in ("connected", "online", "ok", "on", "up", "available", "verbunden", "home")):
            return "ok"
        return "unknown"

    def _label_for_status(self, status: Any) -> str:
        if status == "ok":
            return "OK"
        if status == "down":
            return "Gestört"
        if status == "unstable":
            return "Instabil"
        return "Unbekannt"

    def _router_label(self, fritzbox: dict[str, Any]) -> str:
        label = str(fritzbox.get("label") or "").strip()
        return label if label and label != "Nicht konfiguriert" else "Fritzbox"

    def _safe_attributes(self, attributes: dict[str, Any]) -> dict[str, Any]:
        allowed = ("friendly_name", "device_class", "unit_of_measurement", "icon")
        return {key: attributes[key] for key in allowed if key in attributes}

    def _int_or_none(self, value: Any) -> int | None:
        try:
            return int(float(str(value).replace(",", ".")))
        except (TypeError, ValueError):
            return None

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")
