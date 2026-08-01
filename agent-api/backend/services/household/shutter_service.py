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


class HouseholdShutterService:
    def __init__(
        self,
        ha_service: HomeAssistantService | None = None,
        context_provider: ContextProvider | None = None,
        state_path: str | Path | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.ha_service = ha_service or HomeAssistantService()
        self.context_provider = context_provider or ContextService.current
        self.state_path = resolve_api_path(state_path, "data/household/shutter_state.json")
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
        shutters = household.get("shutters") if isinstance(household.get("shutters"), dict) else {}
        return {
            "enabled": bool(shutters.get("enabled", True)),
            "control_enabled": bool(shutters.get("control_enabled", True)),
            "auto_discovery": bool(shutters.get("auto_discovery", True)),
            "ground_floor_entities": _string_list(shutters.get("ground_floor_entities")),
            "open_after_sunrise": bool(shutters.get("open_after_sunrise", True)),
            "fallback_open_after": str(shutters.get("fallback_open_after") or "07:30"),
            "min_confidence": max(0.0, min(1.0, _float_value(shutters.get("min_confidence"), 0.6))),
            "close_states": _string_set(shutters.get("close_states"), {"SLEEPING"}),
            "block_house_states": _string_set(shutters.get("block_house_states"), {"OUTSIDE", "GUESTS", "RELAXING"}),
        }

    def _context_snapshot(self) -> dict[str, Any]:
        snapshot = self.context_provider()
        if hasattr(snapshot, "as_dict"):
            return snapshot.as_dict(include_debug=False)
        if isinstance(snapshot, dict):
            return snapshot
        raise TypeError("ContextProvider liefert keinen ContextSnapshot.")

    def _runtime_context(self, states: list[dict[str, Any]], context: dict[str, Any], config: dict[str, Any], now: datetime) -> dict[str, Any]:
        covers = self._configured_or_auto_shutters(states, config["ground_floor_entities"], config["auto_discovery"])
        owner = self._read_owner_state()
        sun = next((state for state in states if state.get("entity_id") == "sun.sun"), None)
        house = str(context.get("house") or "").strip().upper()
        sleep = str(context.get("sleep") or "").strip().upper()
        guest = bool(context.get("guest"))
        confidence = _float_value(context.get("confidence"), 0.0)
        sunrise_ready = self._sunrise_ready(sun, config, now)
        open_covers = [item for item in covers if _cover_open(item)]
        closed_covers = [item for item in covers if _cover_closed(item)]
        owner_entities = [entity for entity in owner.get("closed_entities", []) if isinstance(entity, str)] if owner else []
        owned_current = [item for item in covers if str(item.get("entity_id") or "") in owner_entities]
        owned_closed = [item for item in owned_current if _cover_closed(item)]
        return {
            "house": house,
            "sleep": sleep,
            "guest": guest,
            "confidence": confidence,
            "sun": _entity_summary(sun),
            "sunrise_ready": sunrise_ready,
            "entities": {
                "ground_floor_shutters": [_entity_summary(item) for item in covers],
            },
            "counts": {
                "total": len(covers),
                "open": len(open_covers),
                "closed": len(closed_covers),
                "owned": len(owner_entities),
                "owned_closed": len(owned_closed),
            },
            "owner_state": owner,
            "thresholds": {
                "fallback_open_after": config["fallback_open_after"],
                "min_confidence": config["min_confidence"],
            },
        }

    def _rule_decision(self, runtime: dict[str, Any], config: dict[str, Any], now: datetime) -> dict[str, Any]:
        shutters = runtime["entities"].get("ground_floor_shutters") or []
        if not config["enabled"]:
            return _decision("disabled", "none", "Rolloregel ist deaktiviert.", False, [])
        if not shutters:
            return _decision("missing_shutters", "none", "Keine Erdgeschoss-Rollos konfiguriert oder sicher erkannt.", False, [])
        if runtime.get("confidence", 0.0) < config["min_confidence"]:
            return _decision("low_confidence", "none", "Context-Confidence ist fuer die Rollosteuerung zu niedrig.", False, [])

        owner = runtime.get("owner_state") if isinstance(runtime.get("owner_state"), dict) else None
        owner_entities = [entity for entity in owner.get("closed_entities", []) if isinstance(entity, str)] if owner else []
        if owner_entities and runtime.get("sunrise_ready"):
            targets = [
                str(item.get("entity_id") or "")
                for item in shutters
                if str(item.get("entity_id") or "") in owner_entities and not _cover_open(item)
            ]
            if targets:
                return _decision("morning_open", "open_cover", "Sonnenaufgang ist erreicht; Steve oeffnet nur die zuvor selbst geschlossenen Erdgeschoss-Rollos.", True, targets)
            return _decision("owned_already_open", "clear_owner_state", "Die von Steve geschlossenen Rollos sind bereits offen.", True, [])

        if runtime["guest"]:
            return _decision("guests_block_close", "none", "Gaeste erkannt; Nachtautomatik bleibt aus.", False, [])
        if runtime["house"] in config["block_house_states"]:
            return _decision("house_state_blocks_close", "none", "Hauskontext blockiert Rolloschliessen.", False, [])
        if runtime["sleep"] not in config["close_states"]:
            return _decision("not_sleeping", "none", "ContextService meldet noch keinen Schlafkontext.", False, [])

        targets = [str(item.get("entity_id") or "") for item in shutters if not _cover_closed(item)]
        if not targets:
            return _decision("already_closed", "none", "Erdgeschoss-Rollos sind bereits geschlossen.", False, [])
        return _decision("sleeping_close", "close_cover", "ContextService meldet Schlafkontext ohne Gaeste; Erdgeschoss-Rollos koennen geschlossen werden.", True, targets)

    def _apply_decision(
        self,
        decision: dict[str, Any],
        runtime: dict[str, Any],
        apply: bool,
        config: dict[str, Any],
        now: datetime,
    ) -> dict[str, Any] | None:
        action = str(decision.get("action") or "none")
        targets = _string_list(decision.get("targets"))
        if action == "clear_owner_state" and apply:
            self._clear_owner_state()
            return None
        if not apply or action not in {"open_cover", "close_cover"} or not targets:
            return None
        if not config["control_enabled"] or not decision.get("allowed"):
            return None
        result = self.ha_service.call_service("cover", action, {"entity_id": targets})
        if action == "close_cover":
            self._write_owner_state(targets, now, decision)
        else:
            self._clear_owner_state()
        return {
            "domain": "cover",
            "service": action,
            "entity_id": targets,
            "result": result,
        }

    def _configured_or_auto_shutters(self, states: list[dict[str, Any]], configured: list[str], auto_discovery: bool) -> list[dict[str, Any]]:
        if configured:
            by_entity = {str(state.get("entity_id") or ""): state for state in states}
            return [by_entity[entity_id] for entity_id in configured if entity_id in by_entity]
        if not auto_discovery:
            return []
        candidates = [(self._shutter_score(state), state) for state in states]
        candidates = [(score, state) for score, state in candidates if score > 0]
        candidates.sort(key=lambda item: item[0], reverse=True)
        return [state for _, state in candidates]

    def _shutter_score(self, state: dict[str, Any]) -> int:
        entity_id = str(state.get("entity_id") or "").lower()
        if not entity_id.startswith("cover."):
            return 0
        attrs = state.get("attributes") if isinstance(state.get("attributes"), dict) else {}
        name = str(attrs.get("friendly_name") or "").lower()
        device_class = str(attrs.get("device_class") or "").lower()
        area = str(attrs.get("area") or attrs.get("area_id") or "").lower()
        haystack = _ascii_fold(f"{entity_id} {name} {area} {device_class}")
        if any(token in haystack for token in ("garage", "garagentor", "markise", "awning")):
            return 0
        shutter_token = any(token in haystack for token in ("rollo", "rollladen", "jalousie", "shutter", "blind", "cover"))
        ground_floor_token = any(token in haystack for token in ("erdgeschoss", "eg_", "eg ", "_eg", "ground floor", "unten"))
        if not shutter_token or not ground_floor_token:
            return 0
        score = 100
        if "erdgeschoss" in haystack or "ground floor" in haystack:
            score += 30
        return score

    def _sunrise_ready(self, sun: dict[str, Any] | None, config: dict[str, Any], now: datetime) -> bool:
        if config["open_after_sunrise"] and sun:
            state = str(sun.get("state") or "").strip().lower()
            if state == "above_horizon":
                return True
        return now.time() >= _parse_time(config["fallback_open_after"], time(7, 30))

    def _read_owner_state(self) -> dict[str, Any] | None:
        if not self.state_path.exists():
            return None
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return data if isinstance(data, dict) else None

    def _write_owner_state(self, entity_ids: list[str], now: datetime, decision: dict[str, Any]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            json.dumps(
                {
                    "closed_entities": entity_ids,
                    "closed_at": now.astimezone(timezone.utc).isoformat(),
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


def _decision(status: str, action: str, reason: str, allowed: bool, targets: list[str]) -> dict[str, Any]:
    return {
        "status": status,
        "action": action,
        "allowed": bool(allowed),
        "reason": reason,
        "targets": targets,
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
    }


def _cover_open(state: dict[str, Any]) -> bool:
    return str(state.get("state") or "").strip().lower() in {"open", "opening", "on"}


def _cover_closed(state: dict[str, Any]) -> bool:
    return str(state.get("state") or "").strip().lower() in {"closed", "closing", "off"}


def _ascii_fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(char for char in normalized if not unicodedata.combining(char)).replace("\u00df", "ss")


def _parse_time(raw: str, fallback: time) -> time:
    try:
        hour_text, minute_text = str(raw or "").split(":", 1)
        return time(max(0, min(23, int(hour_text))), max(0, min(59, int(minute_text[:2]))))
    except (TypeError, ValueError):
        return fallback


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


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]
