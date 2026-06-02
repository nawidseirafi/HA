from datetime import datetime, timezone
from typing import Any

from backend.config import load_global_config
from backend.services.homeassistant_service import HomeAssistantService
from backend.services.infrastructure_store import InfrastructureStore
from backend.services.messaging import MessagingService


ENTITY_KEYS = (
    "internet_status",
    "fritzbox_status",
    "connected_devices",
    "wifi_status",
    "wan_status",
    "upload_speed",
    "download_speed",
    "external_ip",
    "uptime",
)

TECHNICAL_TERMS = (
    "reload",
    "reconnect",
    "restart",
    "reboot",
    "neu starten",
    "neustart",
    "update",
    "identify",
    "button.",
    "script.",
    "automation.",
)


class InfrastructureService:
    def __init__(
        self,
        ha_service: HomeAssistantService | None = None,
        config: dict[str, Any] | None = None,
        store: InfrastructureStore | None = None,
        messaging: MessagingService | None = None,
    ) -> None:
        self.ha_service = ha_service or HomeAssistantService()
        self.config = config if config is not None else load_global_config()
        infra_config = self.config.get("infrastructure") or {}
        self.enabled = bool(infra_config.get("enabled", True))
        self.store = store or InfrastructureStore(infra_config.get("database_path", "data/infrastructure/infrastructure.db"))
        self.messaging = messaging or MessagingService()

    def status(self) -> dict[str, Any]:
        now = self._now()
        entities = self._configured_entities()
        checks = {key: self._read_entity(key, entities.get(key)) for key in ENTITY_KEYS}
        if not any(check.get("configured") for check in checks.values()):
            checks.update(self._discover_checks())

        normalized = self._v1_status_from_checks(checks, now)
        self._record_state_and_events(normalized, checks, now)
        legacy_summary = self._legacy_summary_from_status(normalized, checks)
        return {
            **normalized,
            "ok": legacy_summary["status"] == "ok",
            "home_assistant": {"configured": self.ha_service.configured()},
            "configured_entities": entities,
            "checks": checks,
            "summary": legacy_summary,
        }

    def summary(self) -> dict[str, Any]:
        data = self.status()
        outages = self.store.outage_stats(24)
        internet_status = data["internet"]["status"]
        fritz_status = data["fritzbox"]["status"]
        status = self._summary_status(internet_status, fritz_status)
        title, subtitle = self._summary_text(status, internet_status, fritz_status)
        legacy = data.get("summary", {})
        return {
            "ok": status == "ok",
            "updated_at": data["updated_at"],
            "status": status,
            "title": title,
            "subtitle": subtitle,
            "connected_devices": data.get("connected_devices"),
            "outages_24h": outages["count"],
            "outage_duration_24h_seconds": outages["duration_seconds"],
            "last_outage": outages["last_outage"],
            "label": legacy.get("label") or title,
            "detail": legacy.get("detail") or subtitle,
            "router": legacy.get("router") or data["fritzbox"].get("model") or "Fritzbox",
            "wifi": data["wifi"]["status"],
            "checks": data.get("checks", {}),
        }

    def events(self, limit: int = 100) -> list[dict[str, Any]]:
        return self.store.get_events(limit)

    def recent_events(self, hours: int = 24, limit: int = 100) -> list[dict[str, Any]]:
        return self.store.get_recent_events(hours=hours, limit=limit)

    def outages(self, hours: int = 24) -> dict[str, Any]:
        return self.store.outage_stats(hours)

    def check(self) -> dict[str, Any]:
        return self.status()

    def _configured_entities(self) -> dict[str, str]:
        household_entities = ((self.config.get("household") or {}).get("entities") or {})
        infrastructure_entities = ((self.config.get("infrastructure") or {}).get("entities") or {})
        merged = {**household_entities, **infrastructure_entities}
        return {key: self._first_entity_id(merged.get(key)) for key in ENTITY_KEYS}

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
            return self._empty_check(key, configured=False)
        if self._is_technical_entity(clean_entity_id, ""):
            return self._empty_check(key, configured=True, entity_id=clean_entity_id, label="Technische Entity ignoriert")
        try:
            state = self.ha_service.fetch_entity_state(clean_entity_id)
        except Exception as exc:
            return {**self._empty_check(key, configured=True, entity_id=clean_entity_id, label="Nicht verfügbar"), "error": str(exc)}
        if not state:
            return self._empty_check(key, configured=True, entity_id=clean_entity_id, label="Unbekannt")
        return self._check_from_state(key, state, configured=True)

    def _empty_check(self, key: str, configured: bool, entity_id: str = "", label: str = "Nicht konfiguriert") -> dict[str, Any]:
        return {
            "key": key,
            "configured": configured,
            "entity_id": entity_id,
            "status": "unknown",
            "value": None,
            "label": label,
        }

    def _discover_checks(self) -> dict[str, dict[str, Any]]:
        try:
            states = self.ha_service.get_states()
        except Exception:
            return {}
        if not isinstance(states, list):
            return {}
        groups = {
            "internet_status": (("internet",), ("wan", "status"), ("dsl", "status"), ("connection", "status"), ("verbindung",)),
            "fritzbox_status": (("fritz", "status"), ("fritzbox",), ("router", "status")),
            "connected_devices": (("connected", "devices"), ("verbundene", "geräte"), ("verbundene", "geraete"), ("clients",), ("devices", "connected")),
            "wifi_status": (("wifi", "status"), ("wlan", "status")),
            "wan_status": (("wan", "status"), ("dsl", "status")),
            "upload_speed": (("upload", "speed"), ("upstream",), ("send", "rate")),
            "download_speed": (("download", "speed"), ("downstream",), ("receive", "rate")),
            "external_ip": (("external", "ip"), ("wan", "ip"), ("öffentliche", "ip"), ("oeffentliche", "ip")),
            "uptime": (("uptime",), ("laufzeit",)),
        }
        result: dict[str, dict[str, Any]] = {}
        for key, needles in groups.items():
            state = self._find_state(states, needles)
            if state:
                result[key] = self._check_from_state(key, state, configured=False, discovered=True)
        return result

    def _find_state(self, states: list[dict[str, Any]], needle_groups: tuple[tuple[str, ...], ...]) -> dict[str, Any] | None:
        candidates = []
        for state in states:
            if not isinstance(state, dict):
                continue
            entity_id = str(state.get("entity_id") or "")
            attributes = state.get("attributes") if isinstance(state.get("attributes"), dict) else {}
            friendly_name = str(attributes.get("friendly_name") or "")
            text = f"{entity_id} {friendly_name}".lower()
            if self._is_technical_entity(entity_id, friendly_name):
                continue
            if any(all(needle in text for needle in needles) for needles in needle_groups):
                candidates.append(state)
        if not candidates:
            return None
        return sorted(candidates, key=self._discovery_rank)[0]

    def _discovery_rank(self, state: dict[str, Any]) -> tuple[int, int, int]:
        entity_id = str(state.get("entity_id") or "").lower()
        value = str(state.get("state") or "").lower()
        unknown = 1 if value in {"", "unknown", "unavailable", "none"} else 0
        domain_rank = 0 if entity_id.startswith(("binary_sensor.", "sensor.")) else 1 if entity_id.startswith("switch.") else 2
        text_rank = 1 if any(term in entity_id for term in TECHNICAL_TERMS) else 0
        return (unknown, domain_rank, text_rank)

    def _check_from_state(self, key: str, state: dict[str, Any], configured: bool = False, discovered: bool = False) -> dict[str, Any]:
        entity_id = str(state.get("entity_id") or "")
        value = state.get("state")
        attributes = state.get("attributes") if isinstance(state.get("attributes"), dict) else {}
        return {
            "key": key,
            "configured": configured,
            "discovered": discovered,
            "entity_id": entity_id,
            "status": self._status_for(key, value),
            "value": value,
            "label": self._human_label(attributes.get("friendly_name") or entity_id),
            "unit": attributes.get("unit_of_measurement"),
            "attributes": self._safe_attributes(attributes),
            "updated_at": state.get("last_updated") or state.get("last_changed"),
        }

    def _v1_status_from_checks(self, checks: dict[str, dict[str, Any]], now: str) -> dict[str, Any]:
        internet_check = self._best_check(checks, "internet_status", "wan_status")
        fritz_check = checks.get("fritzbox_status") or {}
        wifi_check = checks.get("wifi_status") or {}
        devices = checks.get("connected_devices") or {}
        upload = checks.get("upload_speed") or {}
        download = checks.get("download_speed") or {}
        external_ip = checks.get("external_ip") or {}
        uptime = checks.get("uptime") or {}
        return {
            "internet": {
                "status": self._internet_status(internet_check),
                "source": internet_check.get("entity_id") or "",
                "updated_at": internet_check.get("updated_at") or now,
            },
            "fritzbox": {
                "status": self._online_status(fritz_check),
                "model": self._router_label(fritz_check),
                "uptime": uptime.get("value"),
                "external_ip": external_ip.get("value"),
            },
            "wifi": {
                "status": self._online_status(wifi_check),
            },
            "traffic": {
                "upload": self._traffic_value(upload),
                "download": self._traffic_value(download),
            },
            "connected_devices": self._int_or_none(devices.get("value")),
            "updated_at": now,
        }

    def _best_check(self, checks: dict[str, dict[str, Any]], *keys: str) -> dict[str, Any]:
        for key in keys:
            check = checks.get(key) or {}
            if check.get("status") != "unknown":
                return check
        return checks.get(keys[0]) or {}

    def _record_state_and_events(self, data: dict[str, Any], checks: dict[str, dict[str, Any]], now: str) -> None:
        previous = self.store.get_state("latest_status") or {}
        self.store.set_state("latest_status", data, updated_at=now)
        old_internet = ((previous.get("internet") or {}).get("status") if isinstance(previous, dict) else None) or "unknown"
        new_internet = data["internet"]["status"]
        if old_internet == new_internet:
            return
        if new_internet == "offline":
            self._start_event("internet", "internet_outage", "critical", "Internet offline", "Die Internetverbindung ist ausgefallen.", data, now)
        elif new_internet == "unstable":
            self._start_event("internet", "internet_unstable", "warning", "Internet instabil", "Die Internetverbindung wirkt aktuell instabil.", data, now)
        elif new_internet == "online":
            self._close_event("internet", "internet_outage", "Internet wieder online", "Die Verbindung war {duration} offline.", "info", data, now)
            self._close_event("internet", "internet_unstable", "Internet wieder stabil", "Die Internetverbindung ist wieder stabil.", "info", data, now)

        fritz_status = data["fritzbox"]["status"]
        old_fritz = ((previous.get("fritzbox") or {}).get("status") if isinstance(previous, dict) else None) or "unknown"
        if old_fritz != fritz_status and fritz_status == "offline":
            self._start_event("fritzbox", "fritzbox_offline", "critical", "FritzBox nicht erreichbar", "Die FritzBox ist aktuell nicht erreichbar.", data, now)
        elif old_fritz != fritz_status and fritz_status == "online":
            self._close_event("fritzbox", "fritzbox_offline", "FritzBox wieder erreichbar", "Die FritzBox ist wieder erreichbar.", "info", data, now)

    def _start_event(self, source: str, event_type: str, severity: str, title: str, message: str, payload: dict[str, Any], now: str) -> None:
        if self.store.get_open_event(source, event_type):
            return
        event = self.store.create_event(source, event_type, severity, title, message, status="open", started_at=now, payload=payload)
        if severity in {"warning", "critical"}:
            self._message(severity, title, self._message_for_event(event, message), payload)

    def _close_event(self, source: str, event_type: str, title: str, message_template: str, severity: str, payload: dict[str, Any], now: str) -> None:
        event = self.store.get_open_event(source, event_type)
        if not event:
            return
        closed = self.store.close_event(event["id"], ended_at=now)
        duration = self._format_duration(closed.get("duration_seconds") if closed else None)
        message = message_template.replace("{duration}", duration)
        if closed:
            self.store.close_event(event["id"], ended_at=now, message=message)
        self._message(severity, title, message, payload)

    def _message(self, severity: str, title: str, message: str, payload: dict[str, Any]) -> None:
        try:
            self.messaging.create_message(
                source="infrastructure",
                category="infrastructure",
                severity=severity,
                title=title,
                message=message,
                payload=payload,
            )
        except Exception:
            pass

    def _message_for_event(self, event: dict[str, Any], fallback: str) -> str:
        if event.get("event_type") == "internet_outage":
            started = self._format_time(event.get("started_at"))
            return f"Die Internetverbindung ist seit {started} nicht erreichbar."
        return fallback

    def _legacy_summary_from_status(self, data: dict[str, Any], checks: dict[str, dict[str, Any]]) -> dict[str, Any]:
        internet = data["internet"]["status"]
        fritz = data["fritzbox"]["status"]
        wifi = data["wifi"]["status"]
        status = self._legacy_status(internet, fritz)
        details = [
            f"{data['connected_devices']} Geräte" if data.get("connected_devices") is not None else "",
            f"WLAN {self._legacy_label(wifi)}" if wifi != "unknown" else "",
        ]
        router = data["fritzbox"].get("model") or "Fritzbox"
        return {
            "status": status,
            "label": self._legacy_label(status),
            "detail": " · ".join([item for item in details if item]) or router,
            "router": router,
            "connected_devices": data.get("connected_devices"),
            "wifi": wifi,
        }

    def _summary_status(self, internet: str, fritz: str) -> str:
        if internet == "offline" or fritz == "offline":
            return "critical"
        if internet == "unstable":
            return "warning"
        if internet == "online" or fritz == "online":
            return "ok"
        return "unknown"

    def _summary_text(self, status: str, internet: str, fritz: str) -> tuple[str, str]:
        if status == "ok":
            return "Internet OK", "FritzBox erreichbar" if fritz == "online" else "Verbindung erreichbar"
        if status == "critical":
            return "Internet gestört", "FritzBox oder Internet nicht erreichbar"
        if status == "warning":
            return "Internet instabil", "Verbindung wirkt aktuell instabil"
        return "Internet unbekannt", "Keine belastbaren Statusdaten"

    def _legacy_status(self, internet: str, fritz: str) -> str:
        if internet == "offline" or fritz == "offline":
            return "down"
        if internet == "unstable":
            return "unstable"
        if internet == "online" or fritz == "online":
            return "ok"
        return "unknown"

    def _status_for(self, key: str, value: Any) -> str:
        if key == "connected_devices":
            return "ok" if self._int_or_none(value) is not None else "unknown"
        if key in {"upload_speed", "download_speed", "external_ip", "uptime"}:
            return "ok" if str(value or "").strip().lower() not in {"", "unknown", "unavailable", "none"} else "unknown"
        text = str(value or "").strip().lower()
        if text in {"", "unknown", "unavailable", "none"}:
            return "unknown"
        if any(term in text for term in ("disconnect", "offline", "down", "failed", "problem", "gestört", "stoer", "fehler")):
            return "down"
        if text in {"off"} and key in {"internet_status", "fritzbox_status", "wifi_status", "wan_status"}:
            return "down"
        if any(term in text for term in ("unstable", "instabil", "limited", "warning", "warn", "packet", "loss")):
            return "unstable"
        if any(term in text for term in ("connected", "online", "ok", "on", "up", "available", "verbunden", "home")):
            return "ok"
        return "unknown"

    def _internet_status(self, check: dict[str, Any]) -> str:
        status = check.get("status")
        if status == "ok":
            return "online"
        if status == "down":
            return "offline"
        if status == "unstable":
            return "unstable"
        return "unknown"

    def _online_status(self, check: dict[str, Any]) -> str:
        status = check.get("status")
        if status == "ok":
            return "online"
        if status == "down":
            return "offline"
        return "unknown"

    def _legacy_label(self, status: Any) -> str:
        labels = {
            "ok": "OK",
            "online": "OK",
            "down": "Gestört",
            "offline": "Gestört",
            "critical": "Gestört",
            "unstable": "Instabil",
            "warning": "Instabil",
        }
        return labels.get(str(status), "Unbekannt")

    def _router_label(self, fritzbox: dict[str, Any]) -> str:
        label = str(fritzbox.get("label") or "").strip()
        return label if label and label not in {"Nicht konfiguriert", "Unbekannt"} else "Fritzbox"

    def _traffic_value(self, check: dict[str, Any]) -> str | None:
        value = check.get("value")
        if value is None:
            return None
        unit = check.get("unit")
        return f"{value} {unit}".strip() if unit else str(value)

    def _safe_attributes(self, attributes: dict[str, Any]) -> dict[str, Any]:
        allowed = ("friendly_name", "device_class", "unit_of_measurement", "icon", "model")
        return {key: attributes[key] for key in allowed if key in attributes}

    def _int_or_none(self, value: Any) -> int | None:
        try:
            return int(float(str(value).replace(",", ".")))
        except (TypeError, ValueError):
            return None

    def _is_technical_entity(self, entity_id: str, friendly_name: str) -> bool:
        text = f"{entity_id} {friendly_name}".lower()
        return any(term in text for term in TECHNICAL_TERMS)

    def _human_label(self, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return "Infrastructure"
        if "." in text and "_" in text:
            text = text.split(".", 1)[1]
        return text.replace("_", " ").strip().title()

    def _format_duration(self, seconds: Any) -> str:
        try:
            value = int(seconds or 0)
        except (TypeError, ValueError):
            value = 0
        minutes = max(1, round(value / 60))
        if minutes < 60:
            return f"{minutes} Minuten"
        hours = round(minutes / 60, 1)
        return f"{str(hours).replace('.', ',')} Stunden"

    def _format_time(self, value: Any) -> str:
        try:
            date = datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone()
            return date.strftime("%H:%M")
        except ValueError:
            return "unbekannt"

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")
