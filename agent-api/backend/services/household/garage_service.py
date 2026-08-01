from __future__ import annotations

import unicodedata
from datetime import datetime, timezone
from typing import Any, Callable

from backend.config import load_global_config
from backend.services.context import ContextService
from backend.services.homeassistant_service import HomeAssistantService


ContextProvider = Callable[[], Any]


class HouseholdGarageService:
    def __init__(
        self,
        ha_service: HomeAssistantService | None = None,
        context_provider: ContextProvider | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.ha_service = ha_service or HomeAssistantService()
        self.context_provider = context_provider or ContextService.current
        self.now_provider = now_provider or (lambda: datetime.now().astimezone())

    def status(self) -> dict[str, Any]:
        return self.evaluate(apply=False)

    def evaluate(self, apply: bool = False) -> dict[str, Any]:
        config = self._config()
        try:
            states = self.ha_service.get_states()
            context = self._context_snapshot()
            runtime = self._runtime_context(states, context, config)
            decision = self._rule_decision(runtime, config)
            service_call = self._apply_decision(decision, runtime, apply=apply, config=config)
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
        garage = household.get("garage") if isinstance(household.get("garage"), dict) else {}
        return {
            "enabled": bool(garage.get("enabled", True)),
            "control_enabled": bool(garage.get("control_enabled", True)),
            "auto_discovery": bool(garage.get("auto_discovery", True)),
            "garage_entity": str(garage.get("garage_entity") or "").strip(),
            "allow_open": bool(garage.get("allow_open", True)),
            "allow_close": bool(garage.get("allow_close", True)),
            "min_confidence": max(0.0, min(1.0, _float_value(garage.get("min_confidence"), 0.6))),
        }

    def _context_snapshot(self) -> dict[str, Any]:
        snapshot = self.context_provider()
        if hasattr(snapshot, "as_dict"):
            return snapshot.as_dict(include_debug=False)
        if isinstance(snapshot, dict):
            return snapshot
        raise TypeError("ContextProvider liefert keinen ContextSnapshot.")

    def _runtime_context(self, states: list[dict[str, Any]], context: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        garage = self._configured_or_auto_garage(states, config["garage_entity"], config["auto_discovery"])
        garage_state = str(context.get("garage") or "").strip().upper()
        confidence = _float_value(context.get("confidence"), 0.0)
        door_state = str(garage.get("state") if garage else "").strip().lower()
        return {
            "garage": garage_state,
            "presence": str(context.get("presence") or "").strip().upper(),
            "house": str(context.get("house") or "").strip().upper(),
            "confidence": confidence,
            "door_state": door_state,
            "door_open": door_state in {"open", "opening", "on"},
            "door_closed": door_state in {"closed", "closing", "off"},
            "entities": {
                "garage": _entity_summary(garage),
            },
            "thresholds": {
                "min_confidence": config["min_confidence"],
            },
        }

    def _rule_decision(self, runtime: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        garage = runtime["entities"].get("garage") or {}
        if not config["enabled"]:
            return _decision("disabled", "none", "Garagenregel ist deaktiviert.", False)
        if not garage:
            return _decision("missing_garage", "none", "Keine Garagen-Entity konfiguriert oder sicher erkannt.", False)
        if runtime.get("confidence", 0.0) < config["min_confidence"]:
            return _decision("low_confidence", "none", "Context-Confidence ist fuer die Garagensteuerung zu niedrig.", False)
        if runtime["garage"] == "READY_TO_OPEN":
            if not config["allow_open"]:
                return _decision("open_disabled", "none", "Automatisches Oeffnen der Garage ist deaktiviert.", False)
            if runtime["door_open"]:
                return _decision("already_open", "none", "Garage ist bereits offen.", False)
            return _decision("ready_to_open", "open_cover", "ContextService meldet Heimkehr und Garage ist bereit zum Oeffnen.", True)
        if runtime["garage"] == "READY_TO_CLOSE":
            if not config["allow_close"]:
                return _decision("close_disabled", "none", "Automatisches Schliessen der Garage ist deaktiviert.", False)
            if runtime["door_closed"]:
                return _decision("already_closed", "none", "Garage ist bereits geschlossen.", False)
            return _decision("ready_to_close", "close_cover", "ContextService meldet echte Abwesenheit und Garage ist bereit zum Schliessen.", True)
        return _decision("no_action_context", "none", "ContextService meldet keine Garagenaktion.", False)

    def _apply_decision(self, decision: dict[str, Any], runtime: dict[str, Any], apply: bool, config: dict[str, Any]) -> dict[str, Any] | None:
        action = str(decision.get("action") or "none")
        entity = runtime["entities"].get("garage") or {}
        entity_id = str(entity.get("entity_id") or "").strip()
        if not apply or action not in {"open_cover", "close_cover"} or not entity_id:
            return None
        if not config["control_enabled"] or not decision.get("allowed"):
            return None
        result = self.ha_service.call_service("cover", action, {"entity_id": entity_id})
        return {
            "domain": "cover",
            "service": action,
            "entity_id": entity_id,
            "result": result,
        }

    def _configured_or_auto_garage(self, states: list[dict[str, Any]], entity_id: str, auto_discovery: bool) -> dict[str, Any] | None:
        if entity_id:
            return next((state for state in states if state.get("entity_id") == entity_id), None)
        if not auto_discovery:
            return None
        candidates = [(self._garage_score(state), state) for state in states]
        candidates = [(score, state) for score, state in candidates if score > 0]
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1] if candidates else None

    def _garage_score(self, state: dict[str, Any]) -> int:
        entity_id = str(state.get("entity_id") or "").lower()
        if not entity_id.startswith("cover."):
            return 0
        attrs = state.get("attributes") if isinstance(state.get("attributes"), dict) else {}
        name = str(attrs.get("friendly_name") or "").lower()
        haystack = _ascii_fold(f"{entity_id} {name}")
        if any(token in haystack for token in ("problem", "diagnose", "battery", "batterie")):
            return 0
        score = 0
        if "garage" in haystack:
            score += 100
        if "garagentor" in haystack:
            score += 120
        if "tor" in haystack:
            score += 30
        return score


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


def _ascii_fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(char for char in normalized if not unicodedata.combining(char)).replace("\u00df", "ss")


def _float_value(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback
