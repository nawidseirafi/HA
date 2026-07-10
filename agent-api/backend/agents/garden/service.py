from __future__ import annotations

from datetime import datetime
from typing import Any

import yaml

from backend.config import load_agent_section
from backend.paths import AGENTS_DIR
from backend.services.homeassistant_service import HomeAssistantService

from .store import GardenStore


class GardenService:
    agent_id = "garden"

    def __init__(self) -> None:
        self._last_error: str | None = None
        self._last_successful_run: str | None = None
        self._is_running = False

    def status(self) -> dict[str, Any]:
        config = self.config()
        latest = self.latest_snapshot()
        return {
            "enabled": bool(config.get("enabled", True)),
            "is_running": self._is_running,
            "status": "running" if self._is_running else "active" if config.get("enabled", True) else "disabled",
            "current_status": "running" if self._is_running else "active" if config.get("enabled", True) else "disabled",
            "last_error": self._last_error,
            "last_successful_run": self._last_successful_run,
            "latest_snapshot": latest,
            "summary": latest.get("payload", {}).get("summary") if latest else None,
            "entities": latest.get("payload", {}).get("entities") if latest else {},
            "recommendations": latest.get("payload", {}).get("recommendations") if latest else [],
            "settings": config,
        }

    def config(self) -> dict[str, Any]:
        config = load_agent_section(self.agent_id)
        thresholds = config.get("thresholds") if isinstance(config.get("thresholds"), dict) else {}
        entities = config.get("entities") if isinstance(config.get("entities"), dict) else {}
        return {
            "enabled": bool(config.get("enabled", True)),
            "dry_run_default": bool(config.get("dry_run_default", True)),
            "database_path": str(config.get("database_path") or "data/garden/garden.db"),
            "thresholds": {
                "soil_moisture_low": _int_value(thresholds.get("soil_moisture_low"), 25),
                "soil_moisture_target": _int_value(thresholds.get("soil_moisture_target"), 45),
            },
            "schedule": config.get("schedule") if isinstance(config.get("schedule"), list) else ["07:00"],
            "entities": {
                "soil_moisture": entities.get("soil_moisture") or "auto",
                "lawn_mowers": entities.get("lawn_mowers") or "auto",
                "irrigation": entities.get("irrigation") or "auto",
                "weather": entities.get("weather") or "auto",
            },
        }

    def enable(self) -> dict[str, Any]:
        return self.update_settings({"enabled": True})

    def disable(self) -> dict[str, Any]:
        return self.update_settings({"enabled": False})

    def toggle(self) -> dict[str, Any]:
        return self.update_settings({"enabled": not self.config().get("enabled", True)})

    def update_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        current = self.config()
        next_config = {
            "enabled": bool(settings.get("enabled", current["enabled"])),
            "dry_run_default": bool(settings.get("dry_run_default", current["dry_run_default"])),
            "database_path": settings.get("database_path") or current["database_path"],
            "thresholds": dict(current["thresholds"]),
            "schedule": settings.get("schedule") if isinstance(settings.get("schedule"), list) else current["schedule"],
            "entities": dict(current["entities"]),
        }
        if isinstance(settings.get("thresholds"), dict):
            next_config["thresholds"].update(settings["thresholds"])
        if isinstance(settings.get("entities"), dict):
            next_config["entities"].update(settings["entities"])
        self._write_config(next_config)
        return self.status()

    def run(self, dry_run: bool | None = None) -> dict[str, Any]:
        config = self.config()
        effective_dry_run = config["dry_run_default"] if dry_run is None else bool(dry_run)
        started_at = datetime.now().isoformat(timespec="seconds")
        self._is_running = True
        try:
            payload = self._build_snapshot(config=config, dry_run=effective_dry_run, created_at=started_at)
            record = GardenStore(config["database_path"]).add_snapshot(
                created_at=started_at,
                status=str(payload["summary"]["status"]),
                payload=payload,
            )
            self._last_error = None
            self._last_successful_run = started_at
            return {
                "ok": True,
                "status": "active",
                "message": "Garden-Agent hat den Gartenstatus aktualisiert.",
                "snapshot": record,
                **payload,
            }
        except Exception as exc:
            self._last_error = str(exc)
            return {
                "ok": False,
                "status": "error",
                "message": str(exc),
                "created_at": started_at,
                "dry_run": effective_dry_run,
            }
        finally:
            self._is_running = False

    def history(self, limit: int = 100) -> list[dict[str, Any]]:
        return GardenStore(self.config()["database_path"]).history(limit=limit)

    def latest_snapshot(self) -> dict[str, Any] | None:
        return GardenStore(self.config()["database_path"]).latest_snapshot()

    def _build_snapshot(self, config: dict[str, Any], dry_run: bool, created_at: str) -> dict[str, Any]:
        states = HomeAssistantService().get_states()
        entities = {
            "soil_moisture": _soil_moisture_entities(states),
            "lawn_mowers": _domain_entities(states, "lawn_mower"),
            "irrigation": _irrigation_entities(states),
            "weather": _domain_entities(states, "weather"),
        }
        summary, recommendations = _assess_garden(entities, config["thresholds"])
        return {
            "created_at": created_at,
            "dry_run": dry_run,
            "summary": summary,
            "entities": entities,
            "recommendations": recommendations,
            "automation": {
                "mode": "dry_run" if dry_run else "advisory",
                "device_control": False,
            },
        }

    def _write_config(self, garden_config: dict[str, Any]) -> None:
        path = AGENTS_DIR / self.agent_id / "config.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {"garden": garden_config}
        path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _assess_garden(entities: dict[str, list[dict[str, Any]]], thresholds: dict[str, int]) -> tuple[dict[str, Any], list[str]]:
    moisture_values = [
        float(entity["value"])
        for entity in entities["soil_moisture"]
        if isinstance(entity.get("value"), int | float)
    ]
    active_irrigation = [entity for entity in entities["irrigation"] if str(entity.get("state")).lower() in {"on", "open"}]
    active_mowers = [entity for entity in entities["lawn_mowers"] if str(entity.get("state")).lower() in {"mowing", "returning"}]
    low_limit = thresholds["soil_moisture_low"]
    average = round(sum(moisture_values) / len(moisture_values), 1) if moisture_values else None
    minimum = min(moisture_values) if moisture_values else None
    recommendations: list[str] = []

    if minimum is not None and minimum <= low_limit:
        recommendations.append("Bodenfeuchte niedrig - Bewässerung prüfen.")
    if active_irrigation and active_mowers:
        recommendations.append("Mähroboter und Bewässerung nicht gleichzeitig betreiben.")
    if not entities["soil_moisture"]:
        recommendations.append("Noch keine Bodenfeuchte-Sensoren gefunden.")
    if not entities["lawn_mowers"]:
        recommendations.append("Noch kein Mähroboter in Home Assistant gefunden.")

    status = "attention" if recommendations and (minimum is None or minimum <= low_limit or active_irrigation and active_mowers) else "ready"
    return (
        {
            "status": status,
            "soil_moisture_average": average,
            "soil_moisture_min": minimum,
            "soil_moisture_low_limit": low_limit,
            "lawn_mower_count": len(entities["lawn_mowers"]),
            "active_lawn_mower_count": len(active_mowers),
            "active_irrigation_count": len(active_irrigation),
        },
        recommendations,
    )


def _soil_moisture_entities(states: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for state in states:
        entity_id = str(state.get("entity_id") or "")
        if not entity_id.startswith("sensor."):
            continue
        attrs = state.get("attributes") if isinstance(state.get("attributes"), dict) else {}
        name = str(attrs.get("friendly_name") or entity_id).lower()
        device_class = str(attrs.get("device_class") or "").lower()
        unit = str(attrs.get("unit_of_measurement") or "")
        if device_class not in {"moisture", "humidity"} and not any(
            token in f"{entity_id} {name}" for token in ("soil", "boden", "moisture", "feuchte", "plant", "pflanze")
        ):
            continue
        value = _float_value(state.get("state"))
        if value is None:
            continue
        result.append(_entity_summary(state, value=value, unit=unit or "%"))
    return result


def _irrigation_entities(states: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for state in states:
        entity_id = str(state.get("entity_id") or "")
        domain = entity_id.split(".", 1)[0]
        if domain not in {"switch", "valve", "input_boolean"}:
            continue
        attrs = state.get("attributes") if isinstance(state.get("attributes"), dict) else {}
        name = str(attrs.get("friendly_name") or entity_id).lower()
        haystack = f"{entity_id.lower()} {name}"
        if not any(token in haystack for token in ("irrigation", "watering", "sprinkler", "bewässer", "bewasser", "garten", "ventil")):
            continue
        result.append(_entity_summary(state))
    return result


def _domain_entities(states: list[dict[str, Any]], domain: str) -> list[dict[str, Any]]:
    prefix = f"{domain}."
    return [_entity_summary(state) for state in states if str(state.get("entity_id") or "").startswith(prefix)]


def _entity_summary(state: dict[str, Any], value: float | None = None, unit: str | None = None) -> dict[str, Any]:
    attrs = state.get("attributes") if isinstance(state.get("attributes"), dict) else {}
    data: dict[str, Any] = {
        "entity_id": state.get("entity_id"),
        "name": attrs.get("friendly_name") or state.get("entity_id"),
        "state": state.get("state"),
        "last_changed": state.get("last_changed"),
        "last_updated": state.get("last_updated"),
    }
    if value is not None:
        data["value"] = value
    if unit:
        data["unit"] = unit
    return data


def _float_value(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_value(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback
