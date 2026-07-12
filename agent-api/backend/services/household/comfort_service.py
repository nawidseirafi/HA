from __future__ import annotations

import json
from datetime import datetime, time, timezone
from typing import Any

from backend.config import load_global_config
from backend.services.homeassistant_service import HomeAssistantService
from backend.services.llm.factory import create_llm_client


SYSTEM_PROMPT = """Du bist ein vorsichtiger Smart-Home-Komfortassistent.

Du darfst:
- Kontext bewerten
- Empfehlungen geben
- erklaeren, ob ein Ventilator sinnvoll ist

Du darfst NICHT:
- Home-Assistant-Service-Calls erzeugen
- Entity-IDs erfinden
- Sicherheitsregeln umgehen
- selbst entscheiden, dass ein Geraet geschaltet werden muss

Die regelbasierte Freigabe ist immer massgeblich.

Antworte ausschliesslich als JSON."""


class HouseholdComfortService:
    def __init__(self, ha_service: HomeAssistantService | None = None) -> None:
        self.ha_service = ha_service or HomeAssistantService()

    def bedroom_fan_status(self, include_ai: bool = False) -> dict[str, Any]:
        return self.evaluate_bedroom_fan(apply=False, include_ai=include_ai)

    def evaluate_bedroom_fan(self, apply: bool = False, include_ai: bool | None = None) -> dict[str, Any]:
        config = self._config()
        effective_ai = config["ai_enabled"] if include_ai is None else bool(include_ai)
        now = datetime.now().astimezone()
        try:
            states = self.ha_service.get_states()
            context = self._context(states, config, now)
            decision = self._rule_decision(context, config, now)
            ai = self._ai_analysis(context, decision, config) if effective_ai else None
            service_call = self._apply_decision(decision, context, apply=apply, config=config)
            return {
                "ok": True,
                "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "enabled": config["enabled"],
                "applied": bool(service_call),
                "apply_requested": bool(apply),
                "context": context,
                "decision": decision,
                "ai": ai,
                "service_call": service_call,
            }
        except Exception as exc:
            return {
                "ok": False,
                "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "enabled": config["enabled"],
                "applied": False,
                "apply_requested": bool(apply),
                "error": str(exc),
            }

    def _config(self) -> dict[str, Any]:
        raw = load_global_config()
        household = raw.get("household") if isinstance(raw.get("household"), dict) else {}
        comfort = household.get("comfort") if isinstance(household.get("comfort"), dict) else {}
        bedroom = comfort.get("bedroom_fan") if isinstance(comfort.get("bedroom_fan"), dict) else {}
        return {
            "enabled": bool(bedroom.get("enabled", True)),
            "control_enabled": bool(bedroom.get("control_enabled", True)),
            "ai_enabled": bool(bedroom.get("ai_enabled", True)),
            "auto_discovery": bool(bedroom.get("auto_discovery", True)),
            "person_entity": str(bedroom.get("person_entity") or "").strip(),
            "temperature_entity": str(bedroom.get("temperature_entity") or "").strip(),
            "fan_entity": str(bedroom.get("fan_entity") or "").strip(),
            "presence_entity": str(bedroom.get("presence_entity") or "").strip(),
            "window_entity": str(bedroom.get("window_entity") or "").strip(),
            "turn_on_above_c": _float_value(bedroom.get("turn_on_above_c"), 24.5),
            "turn_off_below_c": _float_value(bedroom.get("turn_off_below_c"), 23.5),
            "sleep_start": str(bedroom.get("sleep_start") or "21:30"),
            "sleep_end": str(bedroom.get("sleep_end") or "07:30"),
            "min_runtime_minutes": max(0, int(_float_value(bedroom.get("min_runtime_minutes"), 15))),
        }

    def _context(self, states: list[dict[str, Any]], config: dict[str, Any], now: datetime) -> dict[str, Any]:
        auto = bool(config["auto_discovery"])
        person = self._configured_or_auto(states, config["person_entity"], self._is_person, auto)
        temperature = self._configured_or_auto(states, config["temperature_entity"], self._is_bedroom_temperature, auto)
        fan = self._configured_or_auto_bedroom_fan(states, config["fan_entity"], auto)
        presence = self._configured_or_auto(states, config["presence_entity"], self._is_bedroom_presence, auto)
        window = self._configured_or_auto(states, config["window_entity"], self._is_bedroom_window, auto)

        temp_value = _float_value(temperature.get("state") if temperature else None, None)
        at_home = str(person.get("state") if person else "").lower() == "home"
        in_sleep_window = _in_time_window(now.time(), config["sleep_start"], config["sleep_end"])
        bedroom_present = _truthy_state(presence.get("state")) if presence else None
        window_open = _truthy_state(window.get("state")) if window else None
        fan_on = _truthy_state(fan.get("state")) if fan else None

        return {
            "at_home": at_home,
            "in_sleep_window": in_sleep_window,
            "bedroom_present": bedroom_present,
            "temperature_c": temp_value,
            "window_open": window_open,
            "fan_on": fan_on,
            "entities": {
                "person": _entity_summary(person),
                "temperature": _entity_summary(temperature),
                "fan": _entity_summary(fan),
                "presence": _entity_summary(presence),
                "window": _entity_summary(window),
            },
            "thresholds": {
                "turn_on_above_c": config["turn_on_above_c"],
                "turn_off_below_c": config["turn_off_below_c"],
                "sleep_start": config["sleep_start"],
                "sleep_end": config["sleep_end"],
                "min_runtime_minutes": config["min_runtime_minutes"],
            },
        }

    def _rule_decision(self, context: dict[str, Any], config: dict[str, Any], now: datetime) -> dict[str, Any]:
        missing = [
            key
            for key in ("person", "temperature", "fan")
            if not context["entities"].get(key)
        ]
        if not config["enabled"]:
            return _decision("disabled", "none", "Comfort-Regel ist deaktiviert.", False)
        if missing:
            return _decision("incomplete", "none", f"Pflicht-Entitaeten fehlen: {', '.join(missing)}.", False)
        if not context["at_home"]:
            return _decision("away", "turn_off" if context["fan_on"] else "none", "Niemand ist zuhause.", True)
        if not context["in_sleep_window"] and context["bedroom_present"] is not True:
            return _decision("outside_window", "turn_off" if context["fan_on"] else "none", "Nicht in Schlafzeit und keine Schlafzimmerpraesenz.", True)
        temperature = context.get("temperature_c")
        if temperature is None:
            return _decision("no_temperature", "none", "Schlafzimmer-Temperatur ist nicht verfuegbar.", False)
        if context.get("window_open") is True:
            return _decision("window_open", "turn_off" if context["fan_on"] else "none", "Fenster ist offen.", True)

        fan_on = context.get("fan_on") is True
        if temperature >= config["turn_on_above_c"]:
            action = "none" if fan_on else "turn_on"
            allowed = self._runtime_allows_change(context, config, now) if action != "none" else False
            reason = f"Schlafzimmer ist mit {temperature:.1f} °C zu warm."
            return _decision("too_warm", action, reason, allowed)
        if temperature <= config["turn_off_below_c"]:
            action = "turn_off" if fan_on else "none"
            allowed = self._runtime_allows_change(context, config, now) if action != "none" else False
            reason = f"Schlafzimmer ist mit {temperature:.1f} °C wieder kuehl genug."
            return _decision("cool_enough", action, reason, allowed)
        return _decision("hold", "none", "Temperatur liegt innerhalb der Hysterese.", False)

    def _runtime_allows_change(self, context: dict[str, Any], config: dict[str, Any], now: datetime) -> bool:
        fan = context["entities"].get("fan") or {}
        changed = str(fan.get("last_changed") or "").strip()
        if not changed or config["min_runtime_minutes"] <= 0:
            return True
        try:
            changed_at = datetime.fromisoformat(changed.replace("Z", "+00:00"))
        except ValueError:
            return True
        if changed_at.tzinfo is None:
            changed_at = changed_at.replace(tzinfo=timezone.utc)
        elapsed_minutes = (now.astimezone(timezone.utc) - changed_at.astimezone(timezone.utc)).total_seconds() / 60
        return elapsed_minutes >= config["min_runtime_minutes"]

    def _apply_decision(self, decision: dict[str, Any], context: dict[str, Any], apply: bool, config: dict[str, Any]) -> dict[str, Any] | None:
        action = str(decision.get("action") or "none")
        fan = context["entities"].get("fan") or {}
        entity_id = str(fan.get("entity_id") or "").strip()
        if not apply or action not in {"turn_on", "turn_off"} or not entity_id:
            return None
        if not config["control_enabled"] or not decision.get("allowed"):
            return None
        domain = entity_id.split(".", 1)[0]
        result = self.ha_service.call_service(domain, action, {"entity_id": entity_id})
        return {
            "domain": domain,
            "service": action,
            "entity_id": entity_id,
            "result": result,
        }

    def _ai_analysis(self, context: dict[str, Any], decision: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "context": context,
            "rule_decision": decision,
            "safety_rules": {
                "ki_darf_nicht_schalten": True,
                "rule_based_decision_is_authoritative": True,
                "control_enabled": config["control_enabled"],
            },
        }
        prompt = (
            "Bewerte diese Schlafzimmer-Komfortregel fuer einen Ventilator.\n"
            "Erklaere knapp, ob die regelbasierte Entscheidung plausibel ist.\n"
            "Erzeuge keine Home-Assistant-Kommandos und keine Entity-IDs.\n"
            "Return valid JSON only with exactly this shape:\n"
            "{\n"
            '  "summary": "...",\n'
            '  "recommendation": "turn_on|turn_off|keep_on|keep_off|no_action",\n'
            '  "confidence": 0,\n'
            '  "warnings": []\n'
            "}\n\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
        )
        try:
            response = create_llm_client().generate(prompt=prompt, system=SYSTEM_PROMPT)
            return self._validate_ai_json(response.text)
        except Exception as exc:
            return {
                "summary": "KI-Einschaetzung ist nicht verfuegbar; regelbasierte Freigabe bleibt aktiv.",
                "recommendation": "no_action",
                "confidence": 0,
                "warnings": [str(exc)[:180]],
                "fallback": True,
            }

    def _validate_ai_json(self, raw: str) -> dict[str, Any]:
        text = (raw or "").strip()
        if text.startswith("```"):
            text = text.strip("`").strip()
            if text.lower().startswith("json"):
                text = text[4:].strip()
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("KI-Antwort ist kein JSON-Objekt.")
        recommendation = str(data.get("recommendation") or "no_action").strip().lower()
        if recommendation not in {"turn_on", "turn_off", "keep_on", "keep_off", "no_action"}:
            recommendation = "no_action"
        return {
            "summary": str(data.get("summary") or "Komfortregel wurde bewertet.").strip(),
            "recommendation": recommendation,
            "confidence": max(0, min(100, int(_float_value(data.get("confidence"), 0)))),
            "warnings": _string_list(data.get("warnings")),
            "fallback": False,
        }

    def _configured_or_auto(self, states: list[dict[str, Any]], entity_id: str, predicate, auto_discovery: bool) -> dict[str, Any] | None:
        if entity_id:
            return next((state for state in states if state.get("entity_id") == entity_id), None)
        if not auto_discovery:
            return None
        return next((state for state in states if predicate(state)), None)

    def _configured_or_auto_bedroom_fan(self, states: list[dict[str, Any]], entity_id: str, auto_discovery: bool) -> dict[str, Any] | None:
        if entity_id:
            return next((state for state in states if state.get("entity_id") == entity_id), None)
        if not auto_discovery:
            return None
        candidates = [(self._bedroom_fan_score(state), state) for state in states]
        candidates = [(score, state) for score, state in candidates if score > 0]
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1] if candidates else None

    def _is_person(self, state: dict[str, Any]) -> bool:
        return str(state.get("entity_id") or "").startswith("person.")

    def _is_bedroom_temperature(self, state: dict[str, Any]) -> bool:
        entity_id = str(state.get("entity_id") or "").lower()
        attrs = state.get("attributes") if isinstance(state.get("attributes"), dict) else {}
        name = str(attrs.get("friendly_name") or "").lower()
        device_class = str(attrs.get("device_class") or "").lower()
        unit = str(attrs.get("unit_of_measurement") or "").strip().lower()
        return (
            entity_id.startswith("sensor.")
            and (device_class == "temperature" or unit in {"°c", "c"})
            and _has_bedroom_token(f"{entity_id} {name}")
            and _float_value(state.get("state"), None) is not None
        )

    def _is_bedroom_fan(self, state: dict[str, Any]) -> bool:
        return self._bedroom_fan_score(state) > 0

    def _bedroom_fan_score(self, state: dict[str, Any]) -> int:
        entity_id = str(state.get("entity_id") or "").lower()
        attrs = state.get("attributes") if isinstance(state.get("attributes"), dict) else {}
        name = str(attrs.get("friendly_name") or "").lower()
        haystack = f"{entity_id} {name}"
        domain = entity_id.split(".", 1)[0]
        if domain not in {"fan", "switch"}:
            return 0
        if not _has_bedroom_token(haystack):
            return 0
        if not any(token in haystack for token in ("fan", "ventilator", "luefter", "lüfter")):
            return 0
        if any(token in haystack for token in (
            "internetzugang",
            "internet access",
            "kindersicherung",
            "ionisator",
            "summer",
            "lock",
            "reverse",
            "loudness",
            "autoplay",
            "gruppierung",
            "uberblenden",
            "überblenden",
        )):
            return 0
        score = 100 if domain == "fan" else 40
        if "schlafzimmer" in haystack or "bedroom" in haystack:
            score += 20
        if "ventilator" in haystack or "fan" in haystack:
            score += 10
        return score

    def _is_bedroom_presence(self, state: dict[str, Any]) -> bool:
        entity_id = str(state.get("entity_id") or "").lower()
        attrs = state.get("attributes") if isinstance(state.get("attributes"), dict) else {}
        name = str(attrs.get("friendly_name") or "").lower()
        device_class = str(attrs.get("device_class") or "").lower()
        return entity_id.startswith("binary_sensor.") and device_class in {"occupancy", "presence", "motion"} and _has_bedroom_token(f"{entity_id} {name}")

    def _is_bedroom_window(self, state: dict[str, Any]) -> bool:
        entity_id = str(state.get("entity_id") or "").lower()
        attrs = state.get("attributes") if isinstance(state.get("attributes"), dict) else {}
        name = str(attrs.get("friendly_name") or "").lower()
        device_class = str(attrs.get("device_class") or "").lower()
        return entity_id.startswith("binary_sensor.") and device_class in {"window", "opening"} and _has_bedroom_token(f"{entity_id} {name}")


def _decision(status: str, action: str, reason: str, allowed: bool) -> dict[str, Any]:
    return {
        "status": status,
        "action": action,
        "allowed": bool(allowed),
        "reason": reason,
    }


def _entity_summary(state: dict[str, Any] | None) -> dict[str, Any] | None:
    if not state:
        return None
    attrs = state.get("attributes") if isinstance(state.get("attributes"), dict) else {}
    return {
        "entity_id": state.get("entity_id"),
        "name": attrs.get("friendly_name") or state.get("entity_id"),
        "state": state.get("state"),
        "last_changed": state.get("last_changed"),
        "last_updated": state.get("last_updated"),
        "device_class": attrs.get("device_class"),
        "unit": attrs.get("unit_of_measurement"),
    }


def _has_bedroom_token(value: str) -> bool:
    return any(token in value for token in ("schlafzimmer", "bedroom", "sleeping", "bett"))


def _truthy_state(value: Any) -> bool:
    return str(value or "").strip().lower() in {"on", "home", "true", "open", "detected", "occupied"}


def _in_time_window(value: time, start_raw: str, end_raw: str) -> bool:
    start = _parse_time(start_raw, time(21, 30))
    end = _parse_time(end_raw, time(7, 30))
    if start <= end:
        return start <= value <= end
    return value >= start or value <= end


def _parse_time(raw: str, fallback: time) -> time:
    try:
        hour_text, minute_text = str(raw or "").split(":", 1)
        return time(max(0, min(23, int(hour_text))), max(0, min(59, int(minute_text[:2]))))
    except (TypeError, ValueError):
        return fallback


def _float_value(value: Any, fallback: float | None) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()][:8]
