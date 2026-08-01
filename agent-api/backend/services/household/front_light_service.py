from __future__ import annotations

import json
import unicodedata
from datetime import datetime, time, timezone
from pathlib import Path
from typing import Any, Callable

from backend.config import load_global_config, resolve_api_path
from backend.services.context import ContextService
from backend.services.homeassistant_service import HomeAssistantService


ContextProvider = Callable[[], Any]


class HouseholdFrontLightService:
    def __init__(
        self,
        ha_service: HomeAssistantService | None = None,
        context_provider: ContextProvider | None = None,
        state_path: str | Path | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.ha_service = ha_service or HomeAssistantService()
        self.context_provider = context_provider or ContextService.current
        self.state_path = resolve_api_path(state_path, "data/household/front_light_state.json")
        self.now_provider = now_provider or (lambda: datetime.now().astimezone())

    def status(self) -> dict[str, Any]:
        return self.evaluate(apply=False)

    def evaluate(self, apply: bool = False) -> dict[str, Any]:
        config = self._config()
        now = self.now_provider()
        try:
            states = self.ha_service.get_states()
            context = self._context_snapshot()
            runtime = self._runtime_context(states, context, config, now)
            decision = self._rule_decision(runtime, config, now)
            service_call = self._apply_decision(decision, runtime, apply=apply, config=config, now=now)
            return {
                "ok": True,
                "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "enabled": config["enabled"],
                "applied": bool(service_call),
                "apply_requested": bool(apply),
                "context": runtime,
                "decision": decision,
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
        front_light = household.get("front_light") if isinstance(household.get("front_light"), dict) else {}
        return {
            "enabled": bool(front_light.get("enabled", True)),
            "control_enabled": bool(front_light.get("control_enabled", True)),
            "auto_discovery": bool(front_light.get("auto_discovery", True)),
            "light_entity": str(front_light.get("light_entity") or "").strip(),
            "evening_start": str(front_light.get("evening_start") or "18:00"),
            "morning_end": str(front_light.get("morning_end") or "07:00"),
            "turn_off_after_minutes": max(1, int(_float_value(front_light.get("turn_off_after_minutes"), 10))),
            "min_confidence": max(0.0, min(1.0, _float_value(front_light.get("min_confidence"), 0.55))),
            "arrival_states": _string_set(front_light.get("arrival_states"), {"COMING_HOME"}),
            "arrival_garage_states": _string_set(front_light.get("arrival_garage_states"), {"READY_TO_OPEN"}),
        }

    def _context_snapshot(self) -> dict[str, Any]:
        snapshot = self.context_provider()
        if hasattr(snapshot, "as_dict"):
            return snapshot.as_dict(include_debug=False)
        if isinstance(snapshot, dict):
            return snapshot
        raise TypeError("ContextProvider liefert keinen ContextSnapshot.")

    def _runtime_context(self, states: list[dict[str, Any]], context: dict[str, Any], config: dict[str, Any], now: datetime) -> dict[str, Any]:
        light = self._configured_or_auto_light(states, config["light_entity"], config["auto_discovery"])
        owned = self._read_owner_state(now)
        light_on = _truthy_state(light.get("state")) if light else None
        in_evening_window = _in_time_window(now.time(), config["evening_start"], config["morning_end"])
        presence = str(context.get("presence") or "").strip().upper()
        garage = str(context.get("garage") or "").strip().upper()
        confidence = _float_value(context.get("confidence"), 0.0)
        arrival_detected = presence in config["arrival_states"] or garage in config["arrival_garage_states"]
        return {
            "in_evening_window": in_evening_window,
            "arrival_detected": arrival_detected,
            "presence": presence,
            "garage": garage,
            "house": str(context.get("house") or "").strip().upper(),
            "sleep": str(context.get("sleep") or "").strip().upper(),
            "confidence": confidence,
            "light_on": light_on,
            "entities": {
                "front_light": _entity_summary(light),
            },
            "owner_state": owned,
            "thresholds": {
                "evening_start": config["evening_start"],
                "morning_end": config["morning_end"],
                "turn_off_after_minutes": config["turn_off_after_minutes"],
                "min_confidence": config["min_confidence"],
            },
        }

    def _rule_decision(self, runtime: dict[str, Any], config: dict[str, Any], now: datetime) -> dict[str, Any]:
        light = runtime["entities"].get("front_light") or {}
        owner = runtime.get("owner_state") if isinstance(runtime.get("owner_state"), dict) else None

        if owner and _owner_elapsed_minutes(owner, now) >= config["turn_off_after_minutes"]:
            return _decision("owned_timeout", "turn_off", "Frontlicht wurde nach der Ankunft lange genug eingeschaltet gelassen.", True)
        if owner and runtime.get("light_on") is False:
            return _decision("already_off", "clear_owner_state", "Frontlicht ist bereits aus; Steve gibt die Steuerung frei.", True)

        if not config["enabled"]:
            return _decision("disabled", "none", "Frontlicht-Regel ist deaktiviert.", False)
        if not light:
            return _decision("missing_light", "none", "Kein Front- oder Eingangslicht konfiguriert oder sicher erkannt.", False)
        if not runtime.get("in_evening_window"):
            return _decision("daytime", "none", "Ankunft liegt nicht im Abend- oder Nachtfenster.", False)
        if not runtime.get("arrival_detected"):
            return _decision("no_arrival", "none", "ContextService meldet keine Heimkehr.", False)
        if runtime.get("confidence", 0.0) < config["min_confidence"]:
            return _decision("low_confidence", "none", "Kontext-Confidence ist fuer eine automatische Lichtregel zu niedrig.", False)
        if runtime.get("light_on") is True:
            return _decision("already_on", "mark_owner_state", "Frontlicht ist bei Heimkehr bereits an; Steve merkt sich keinen manuellen Ursprung.", False)
        return _decision("arrival_evening", "turn_on", "ContextService meldet abendliche Heimkehr; Frontlicht wird zeitlich begrenzt eingeschaltet.", True)

    def _apply_decision(
        self,
        decision: dict[str, Any],
        runtime: dict[str, Any],
        apply: bool,
        config: dict[str, Any],
        now: datetime,
    ) -> dict[str, Any] | None:
        action = str(decision.get("action") or "none")
        light = runtime["entities"].get("front_light") or {}
        entity_id = str(light.get("entity_id") or "").strip()

        if action == "clear_owner_state" and apply:
            self._clear_owner_state()
            return None
        if not apply or action not in {"turn_on", "turn_off"} or not entity_id:
            return None
        if not config["control_enabled"] or not decision.get("allowed"):
            return None

        result = self.ha_service.call_service("light", action, {"entity_id": entity_id})
        if action == "turn_on":
            self._write_owner_state(entity_id, now, config, decision)
        else:
            self._clear_owner_state()
        return {
            "domain": "light",
            "service": action,
            "entity_id": entity_id,
            "result": result,
        }

    def _configured_or_auto_light(self, states: list[dict[str, Any]], entity_id: str, auto_discovery: bool) -> dict[str, Any] | None:
        if entity_id:
            return next((state for state in states if state.get("entity_id") == entity_id), None)
        if not auto_discovery:
            return None
        candidates = [(self._front_light_score(state), state) for state in states]
        candidates = [(score, state) for score, state in candidates if score > 0]
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1] if candidates else None

    def _front_light_score(self, state: dict[str, Any]) -> int:
        entity_id = str(state.get("entity_id") or "").lower()
        if not entity_id.startswith("light."):
            return 0
        attrs = state.get("attributes") if isinstance(state.get("attributes"), dict) else {}
        name = str(attrs.get("friendly_name") or "").lower()
        area = str(attrs.get("area") or attrs.get("area_id") or "").lower()
        haystack = _ascii_fold(f"{entity_id} {name} {area}")
        score = 0
        for token, weight in {
            "front": 100,
            "eingang": 100,
            "haustuer": 95,
            "vordertuer": 90,
            "porch": 90,
            "entry": 85,
            "vorne": 80,
            "aussen": 65,
            "outdoor": 65,
        }.items():
            if token in haystack:
                score = max(score, weight)
        if score <= 0:
            return 0
        if any(token in haystack for token in ("wohnzimmer", "schlafzimmer", "kueche", "kuche", "bad", "terrasse", "garten")):
            score -= 60
        return max(0, score)

    def _read_owner_state(self, now: datetime) -> dict[str, Any] | None:
        if not self.state_path.exists():
            return None
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict):
            return None
        turned_on_at = _parse_datetime(data.get("turned_on_at"))
        if not turned_on_at:
            return None
        data["elapsed_minutes"] = max(0.0, (now.astimezone(timezone.utc) - turned_on_at.astimezone(timezone.utc)).total_seconds() / 60)
        return data

    def _write_owner_state(self, entity_id: str, now: datetime, config: dict[str, Any], decision: dict[str, Any]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            json.dumps(
                {
                    "entity_id": entity_id,
                    "turned_on_at": now.astimezone(timezone.utc).isoformat(),
                    "turn_off_after_minutes": config["turn_off_after_minutes"],
                    "reason": decision.get("reason"),
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

    def _clear_owner_state(self) -> None:
        try:
            self.state_path.unlink(missing_ok=True)
        except OSError:
            return


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
    }


def _truthy_state(value: Any) -> bool:
    return str(value or "").strip().lower() in {"on", "home", "true", "open", "detected", "occupied"}


def _ascii_fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(char for char in normalized if not unicodedata.combining(char)).replace("\u00df", "ss")


def _in_time_window(value: time, start_raw: str, end_raw: str) -> bool:
    start = _parse_time(start_raw, time(18, 0))
    end = _parse_time(end_raw, time(7, 0))
    if start <= end:
        return start <= value <= end
    return value >= start or value <= end


def _parse_time(raw: str, fallback: time) -> time:
    try:
        hour_text, minute_text = str(raw or "").split(":", 1)
        return time(max(0, min(23, int(hour_text))), max(0, min(59, int(minute_text[:2]))))
    except (TypeError, ValueError):
        return fallback


def _parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _owner_elapsed_minutes(owner: dict[str, Any], now: datetime) -> float:
    if "elapsed_minutes" in owner:
        return _float_value(owner.get("elapsed_minutes"), 0.0)
    turned_on_at = _parse_datetime(owner.get("turned_on_at"))
    if not turned_on_at:
        return 0.0
    return max(0.0, (now.astimezone(timezone.utc) - turned_on_at.astimezone(timezone.utc)).total_seconds() / 60)


def _float_value(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _string_set(value: Any, fallback: set[str]) -> set[str]:
    if not isinstance(value, list):
        return set(fallback)
    items = {str(item or "").strip().upper() for item in value if str(item or "").strip()}
    return items or set(fallback)
