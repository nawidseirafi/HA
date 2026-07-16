from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import yaml

from backend.agents.scheduler.store import SchedulerStore
from backend.config import load_agent_section
from backend.paths import AGENTS_DIR
from backend.services.homeassistant_service import HomeAssistantService
from backend.services.messaging import MessagingService

from .adapter import GardenIrrigationAdapter
from .decision import GardenDecisionEngine
from .discovery import GardenEntityDiscovery
from .models import EntityBinding, ZoneDecision, ZoneEvaluationInput, normalize_mower_status, utc_now
from .store import GardenStore


logger = logging.getLogger(__name__)

MANUAL_START_HARD_BLOCKS = {"irrigation_unavailable", "mower_active", "open_irrigation_run", "irrigation_already_active"}


class GardenSafetyBlocked(RuntimeError):
    def __init__(self, message: str, decision: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.decision = decision or {}


class GardenNotFound(KeyError):
    pass


class GardenService:
    agent_id = "garden"

    def __init__(
        self,
        ha_service: HomeAssistantService | None = None,
        store: GardenStore | None = None,
        messaging: MessagingService | None = None,
    ) -> None:
        self.ha_service = ha_service or HomeAssistantService()
        self._store = store
        self.messaging = messaging or MessagingService()
        self.discovery = GardenEntityDiscovery()
        self.engine = GardenDecisionEngine()
        self._last_error: str | None = None
        self._last_successful_run: str | None = None
        self._is_running = False

    def config(self) -> dict[str, Any]:
        raw = load_agent_section(self.agent_id)
        zones = raw.get("zones") if isinstance(raw.get("zones"), dict) else {}
        legacy_entities = raw.get("entities") if isinstance(raw.get("entities"), dict) else {}
        legacy_thresholds = raw.get("thresholds") if isinstance(raw.get("thresholds"), dict) else {}
        if not zones:
            zones = {
                "lawn": {
                    "name": "Rasen",
                    "entities": {
                        "moisture": _legacy_entity(legacy_entities.get("soil_moisture")),
                        "mower": _legacy_entity(legacy_entities.get("lawn_mowers")),
                        "irrigation": _legacy_entity(legacy_entities.get("irrigation")),
                        "weather": _legacy_entity(legacy_entities.get("weather")),
                    },
                    "moisture": {
                        "dry_below": _int_value(legacy_thresholds.get("soil_moisture_low"), 25),
                        "target_min": _int_value(legacy_thresholds.get("soil_moisture_target"), 35),
                    },
                }
            }
        normalized_zones = {
            str(zone_id): self._zone_config(str(zone_id), zone if isinstance(zone, dict) else {})
            for zone_id, zone in zones.items()
        }
        return {
            "enabled": bool(raw.get("enabled", True)),
            "control_enabled": bool(raw.get("control_enabled", False)),
            "auto_discovery": bool(raw.get("auto_discovery", True)),
            "dry_run_default": bool(raw.get("dry_run_default", True)),
            "database_path": str(raw.get("database_path") or "data/garden/garden.db"),
            "schedule": raw.get("schedule") if isinstance(raw.get("schedule"), list) else ["07:00"],
            "zones": normalized_zones,
        }

    def status(self) -> dict[str, Any]:
        config = self.config()
        store = self.store(config)
        latest = self.latest_snapshot()
        zones = []
        try:
            zones = self.evaluate_all(save=False, apply=False)["zones"]
            self._last_error = None
        except Exception as exc:
            self._last_error = str(exc)
        return {
            "enabled": config["enabled"],
            "control_enabled": config["control_enabled"],
            "is_running": self._is_running,
            "status": "running" if self._is_running else "active" if config["enabled"] else "disabled",
            "current_status": "running" if self._is_running else "active" if config["enabled"] else "disabled",
            "last_error": self._last_error,
            "last_successful_run": self._last_successful_run,
            "latest_snapshot": latest,
            "summary": self._summary_from_zones(zones),
            "zones": zones,
            "settings": config,
            "history": {
                "latest_irrigation_runs": {
                    zone_id: store.latest_completed_irrigation_run(zone_id)
                    for zone_id in config["zones"]
                }
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
        next_config = {**current, **{key: value for key, value in settings.items() if value is not None}}
        if isinstance(settings.get("zones"), dict):
            merged_zones = dict(current["zones"])
            for zone_id, zone in settings["zones"].items():
                if isinstance(zone, dict):
                    merged_zones[str(zone_id)] = self._zone_config(str(zone_id), {**merged_zones.get(str(zone_id), {}), **zone})
            next_config["zones"] = merged_zones
        self._write_config(next_config)
        return self.status()

    def run(
        self,
        dry_run: bool | None = None,
        action: str | None = None,
        zone_id: str | None = None,
        source: str = "scheduler",
        duration_minutes: int | None = None,
    ) -> dict[str, Any]:
        if action == "irrigation_stop":
            if not zone_id:
                raise ValueError("zone_id fehlt.")
            return self.stop_irrigation(zone_id, source=source, stop_reason="scheduled_stop")
        config = self.config()
        apply = bool(config["control_enabled"]) and not (config["dry_run_default"] if dry_run is None else bool(dry_run))
        return self.evaluate_all(save=True, apply=apply, source=source)

    def zones(self) -> list[dict[str, Any]]:
        return self.evaluate_all(save=False, apply=False)["zones"]

    def zone(self, zone_id: str) -> dict[str, Any]:
        config = self.config()
        if zone_id not in config["zones"]:
            raise GardenNotFound(zone_id)
        return self._evaluate_zone(zone_id, config, self._states(), save=False)

    def evaluate_all(self, save: bool = True, apply: bool = False, source: str = "scheduler") -> dict[str, Any]:
        config = self.config()
        states = self._states()
        store = self.store(config)
        now = utc_now()
        self._is_running = True
        zones = []
        try:
            for zone_id, zone_cfg in config["zones"].items():
                try:
                    store.upsert_zone(zone_id, zone_cfg["name"], zone_cfg.get("enabled", True), now)
                    zone = self._evaluate_zone(zone_id, config, states, save=save)
                    zones.append(zone)
                    if apply and zone["decision"]["apply_allowed"]:
                        self.start_irrigation(zone_id, duration_minutes=zone["decision"].get("recommended_duration_minutes"), source=source)
                    self._stop_overdue_if_needed(zone_id, zone_cfg, states, source="safety")
                except Exception as exc:
                    logger.exception("Garden zone %s failed.", zone_id)
                    zones.append({"zone_id": zone_id, "name": zone_cfg.get("name", zone_id), "error": str(exc)})
            payload = {
                "ok": True,
                "status": "active",
                "created_at": now,
                "zones": zones,
                "summary": self._summary_from_zones(zones),
            }
            if save:
                store.add_snapshot(now, str(payload["summary"].get("status") or "unknown"), payload)
            self._last_successful_run = now
            self._last_error = None
            return payload
        except Exception as exc:
            self._last_error = str(exc)
            return {"ok": False, "status": "error", "message": str(exc), "zones": zones}
        finally:
            self._is_running = False

    def evaluate_zone(self, zone_id: str, save: bool = True) -> dict[str, Any]:
        config = self.config()
        if zone_id not in config["zones"]:
            raise GardenNotFound(zone_id)
        return self._evaluate_zone(zone_id, config, self._states(), save=save)

    def start_irrigation(self, zone_id: str, duration_minutes: int | None = None, source: str = "manual") -> dict[str, Any]:
        config = self.config()
        if zone_id not in config["zones"]:
            raise GardenNotFound(zone_id)
        states = self._states()
        zone = self._evaluate_zone(zone_id, config, states, save=True)
        decision = zone["decision"]
        zone_cfg = config["zones"][zone_id]
        max_duration = int(zone_cfg["irrigation"]["max_duration_minutes"])
        duration = int(duration_minutes or decision.get("recommended_duration_minutes") or zone_cfg["irrigation"]["default_duration_minutes"])
        if duration < 1 or duration > max_duration:
            raise ValueError(f"Dauer muss zwischen 1 und {max_duration} Minuten liegen.")
        if not self._irrigation_start_allowed(decision, source):
            raise GardenSafetyBlocked("Bewässerung ist durch Sicherheitsregeln blockiert.", decision)

        binding = zone["entities"]["irrigation"]
        entity_id = str(binding.get("entity_id") or "")
        if not entity_id:
            raise GardenSafetyBlocked("Kein Bewässerungsventil zugeordnet.", decision)
        store = self.store(config)
        requested_at = utc_now()
        action = store.create_action(zone_id, "irrigation_start", source, requested_at, {"decision": decision})
        try:
            adapter_result = GardenIrrigationAdapter(self.ha_service).start(entity_id)
            completed_at = utc_now()
            completed = store.complete_action(
                action["id"], completed_at, True, entity_id, adapter_result["domain"], adapter_result["service"], adapter_result
            )
            planned_end = (datetime.fromisoformat(completed_at.replace("Z", "+00:00")) + timedelta(minutes=duration)).isoformat(timespec="seconds")
            run = store.start_irrigation_run(
                zone_id=zone_id,
                started_at=completed_at,
                planned_end_at=planned_end,
                planned_duration_minutes=duration,
                source=source,
                start_moisture=zone["values"].get("moisture"),
                start_action_id=completed["id"],
            )
            self._schedule_irrigation_stop(zone_id, planned_end, run["id"])
            return {"ok": True, "status": "started", "action": completed, "irrigation_run": run, "decision": decision}
        except Exception as exc:
            completed = store.complete_action(action["id"], utc_now(), False, entity_id, details={}, error=str(exc))
            self._message("critical", "Bewässerung konnte nicht gestartet werden", str(exc), {"zone_id": zone_id, "action_id": completed["id"]})
            raise

    def stop_irrigation(self, zone_id: str, source: str = "manual", stop_reason: str = "manual") -> dict[str, Any]:
        config = self.config()
        if zone_id not in config["zones"]:
            raise GardenNotFound(zone_id)
        states = self._states()
        zone = self._evaluate_zone(zone_id, config, states, save=True)
        binding = zone["entities"]["irrigation"]
        entity_id = str(binding.get("entity_id") or "")
        store = self.store(config)
        open_run = store.open_irrigation_run(zone_id)
        if not entity_id:
            raise GardenSafetyBlocked("Kein Bewässerungsventil zugeordnet.", zone["decision"])
        action = store.create_action(zone_id, "irrigation_stop", source, utc_now(), {"stop_reason": stop_reason})
        if zone["values"].get("irrigation_active") is False:
            completed = store.complete_action(
                action["id"],
                utc_now(),
                True,
                entity_id,
                str(binding.get("domain") or ""),
                "",
                {"already_off": True, "stop_reason": stop_reason},
            )
            closed_run = None
            if open_run:
                closed_run = store.close_irrigation_run(
                    open_run["id"], utc_now(), zone["values"].get("moisture"), "external_stop", completed["id"], "completed"
                )
            return {"ok": True, "status": "already_stopped", "action": completed, "irrigation_run": closed_run}
        try:
            adapter_result = GardenIrrigationAdapter(self.ha_service).stop(entity_id)
            completed = store.complete_action(
                action["id"], utc_now(), True, entity_id, adapter_result["domain"], adapter_result["service"], adapter_result
            )
            closed_run = None
            if open_run:
                closed_run = store.close_irrigation_run(
                    open_run["id"], utc_now(), zone["values"].get("moisture"), stop_reason, completed["id"], "completed"
                )
            return {"ok": True, "status": "stopped", "action": completed, "irrigation_run": closed_run}
        except Exception as exc:
            completed = store.complete_action(action["id"], utc_now(), False, entity_id, details={}, error=str(exc))
            self._message("critical", "Bewässerung konnte nicht beendet werden", str(exc), {"zone_id": zone_id, "action_id": completed["id"]})
            raise

    def decisions(self, zone_id: str, limit: int = 100) -> list[dict[str, Any]]:
        if zone_id not in self.config()["zones"]:
            raise GardenNotFound(zone_id)
        return self.store().list_decisions(zone_id, limit)

    def irrigation_runs(self, zone_id: str, limit: int = 100) -> list[dict[str, Any]]:
        if zone_id not in self.config()["zones"]:
            raise GardenNotFound(zone_id)
        return self.store().list_irrigation_runs(zone_id, limit)

    def history(self, limit: int = 100) -> list[dict[str, Any]]:
        return self.store().history(limit=limit)

    def latest_snapshot(self) -> dict[str, Any] | None:
        return self.store().latest_snapshot()

    def store(self, config: dict[str, Any] | None = None) -> GardenStore:
        if self._store is not None:
            return self._store
        return GardenStore((config or self.config())["database_path"])

    def _evaluate_zone(self, zone_id: str, config: dict[str, Any], states: list[dict[str, Any]], save: bool = True) -> dict[str, Any]:
        zone_cfg = config["zones"][zone_id]
        bindings = self.discovery.bind_zone_entities(states, zone_cfg, auto_discovery=config["auto_discovery"])
        store = self.store(config)
        decision_input = self._decision_input(zone_id, zone_cfg, bindings, store)
        if decision_input.open_irrigation_run and decision_input.irrigation_active is False:
            store.close_irrigation_run(
                int(decision_input.open_irrigation_run["id"]),
                utc_now(),
                decision_input.moisture,
                "external_stop",
                None,
                "completed",
            )
            decision_input = self._decision_input(zone_id, zone_cfg, bindings, store)
        decision = self.engine.evaluate_zone(decision_input).public_dict()
        if save:
            store.save_decision(decision)
        return {
            "zone_id": zone_id,
            "name": zone_cfg["name"],
            "enabled": zone_cfg.get("enabled", True),
            "entities": {key: binding.public_dict() for key, binding in bindings.items()},
            "values": {
                "moisture": decision_input.moisture,
                "soil_temperature": decision_input.soil_temperature,
                "battery": decision_input.battery,
                "soil_warning": decision_input.soil_warning,
                "irrigation_active": decision_input.irrigation_active,
                "mower_status": decision_input.mower_status,
                "rain_active": decision_input.rain_active,
                "rain_probability": decision_input.rain_probability,
            },
            "decision": decision,
            "latest_irrigation_run": store.latest_completed_irrigation_run(zone_id),
            "open_irrigation_run": store.open_irrigation_run(zone_id),
            "automatic_enabled": zone_cfg["irrigation"]["automatic_enabled"],
        }

    def _irrigation_start_allowed(self, decision: dict[str, Any], source: str) -> bool:
        if decision.get("apply_allowed"):
            return True
        if source != "manual":
            return False
        blocks = decision.get("blocks") or []
        blocking_codes = {
            str(block.get("code"))
            for block in blocks
            if isinstance(block, dict) and block.get("code") in MANUAL_START_HARD_BLOCKS
        }
        return not blocking_codes

    def _decision_input(self, zone_id: str, zone_cfg: dict[str, Any], bindings: dict[str, EntityBinding], store: GardenStore) -> ZoneEvaluationInput:
        moisture = _float_value(bindings["moisture"].state)
        soil_temp = _float_value(bindings["temperature"].state)
        battery = _float_value(bindings["battery"].state)
        soil_warning = _bool_state(bindings["soil_warning"].state) if bindings["soil_warning"].entity_id else None
        irrigation_active = _active_state(bindings["irrigation"].state) if bindings["irrigation"].entity_id else None
        mower_status = normalize_mower_status(bindings["mower"].state)
        rain_active = _bool_state(bindings["rain"].state) if bindings["rain"].entity_id else self._weather_rain_active(bindings["weather"].state)
        rain_probability = _float_value(bindings["rain"].state) if bindings["rain"].domain == "sensor" else None
        latest = store.latest_completed_irrigation_run(zone_id)
        open_run = store.open_irrigation_run(zone_id)
        return ZoneEvaluationInput(
            zone_id=zone_id,
            zone_name=zone_cfg["name"],
            moisture=moisture,
            soil_temperature=soil_temp,
            battery=battery,
            soil_warning=soil_warning,
            moisture_available=bindings["moisture"].available,
            moisture_last_updated=bindings["moisture"].last_updated,
            irrigation_active=irrigation_active,
            irrigation_available=bindings["irrigation"].available,
            mower_status=mower_status,
            rain_active=rain_active,
            rain_probability=rain_probability,
            last_irrigation_ended_at=latest.get("ended_at") if latest else None,
            open_irrigation_run=open_run,
            config=zone_cfg,
            control_enabled=self.config()["control_enabled"],
            agent_enabled=self.config()["enabled"] and zone_cfg.get("enabled", True),
        )

    def _stop_overdue_if_needed(self, zone_id: str, zone_cfg: dict[str, Any], states: list[dict[str, Any]], source: str) -> None:
        store = self.store()
        open_run = store.open_irrigation_run(zone_id)
        if not open_run:
            return
        try:
            planned = datetime.fromisoformat(str(open_run["planned_end_at"]).replace("Z", "+00:00"))
        except ValueError:
            return
        max_minutes = int(zone_cfg["irrigation"]["max_duration_minutes"])
        hard_stop = planned + timedelta(minutes=max(1, max_minutes))
        if datetime.now(timezone.utc) > hard_stop.astimezone(timezone.utc):
            self._message("critical", "Bewässerung läuft zu lange", "Die maximale Laufzeit wurde überschritten. Stop wird versucht.", {"zone_id": zone_id, "run_id": open_run["id"]})
            self.stop_irrigation(zone_id, source=source, stop_reason="max_duration_exceeded")

    def _schedule_irrigation_stop(self, zone_id: str, planned_end_at: str, run_id: int) -> None:
        try:
            SchedulerStore().create_task({
                "name": f"Garden Bewässerung Stop {zone_id} #{run_id}",
                "description": "Stoppt eine geplante Garden-Bewässerung.",
                "enabled": True,
                "schedule_type": "once",
                "schedule": {"run_at": planned_end_at},
                "target_agent": self.agent_id,
                "target_action": "run",
                "action_type": "execute_action",
                "action_payload": {"action": "irrigation_stop", "zone_id": zone_id, "source": "scheduler"},
                "source": "manual",
            })
        except Exception as exc:
            self._message("warning", "Bewässerungs-Stop konnte nicht geplant werden", str(exc), {"zone_id": zone_id, "run_id": run_id})

    def _states(self) -> list[dict[str, Any]]:
        return self.ha_service.get_states()

    def _zone_config(self, zone_id: str, zone: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": zone_id,
            "name": str(zone.get("name") or "Rasen"),
            "enabled": bool(zone.get("enabled", True)),
            "entities": _merge_dict({
                "moisture": "",
                "temperature": "",
                "battery": "",
                "soil_warning": "",
                "mower": "",
                "irrigation": "",
                "weather": "",
                "rain": "",
            }, zone.get("entities")),
            "moisture": _merge_dict({"critical_below": 15, "dry_below": 25, "target_min": 35, "wet_above": 60}, zone.get("moisture")),
            "temperature": _merge_dict({"irrigation_min_c": 5, "irrigation_max_c": 32}, zone.get("temperature")),
            "irrigation": _merge_dict({
                "enabled": True,
                "automatic_enabled": False,
                "default_duration_minutes": 20,
                "max_duration_minutes": 30,
                "minimum_pause_hours": 12,
                "stop_on_sensor_failure": True,
                "sensor_max_age_minutes": 180,
            }, zone.get("irrigation")),
            "mower": _merge_dict({
                "enabled": True,
                "block_during_irrigation": True,
                "irrigation_block_states": ["mowing", "starting", "returning"],
            }, zone.get("mower")),
            "weather": _merge_dict({
                "enabled": True,
                "rain_block_enabled": True,
                "rain_probability_block_above": 60,
                "forecast_hours": 12,
            }, zone.get("weather")),
        }

    def _write_config(self, garden_config: dict[str, Any]) -> None:
        path = AGENTS_DIR / self.agent_id / "config.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {"garden": garden_config}
        path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")

    def _weather_rain_active(self, state: Any) -> bool | None:
        if state is None:
            return None
        return str(state).lower() in {"rainy", "pouring", "lightning-rainy"}

    def _message(self, severity: str, title: str, message: str, payload: dict[str, Any]) -> None:
        try:
            self.messaging.create_message("garden", "garden", severity, title, message, payload)
        except Exception:
            logger.exception("Garden message could not be created.")

    def _summary_from_zones(self, zones: list[dict[str, Any]]) -> dict[str, Any]:
        statuses = [zone.get("decision", {}).get("status") for zone in zones if isinstance(zone.get("decision"), dict)]
        if any(status == "critically_dry" for status in statuses):
            status = "critically_dry"
        elif any(status == "dry" for status in statuses):
            status = "dry"
        elif any(status == "unknown" for status in statuses):
            status = "unknown"
        else:
            status = "healthy" if statuses else "unknown"
        return {"status": status, "zone_count": len(zones)}


def _merge_dict(defaults: dict[str, Any], value: Any) -> dict[str, Any]:
    result = dict(defaults)
    if isinstance(value, dict):
        result.update(value)
    return result


def _legacy_entity(value: Any) -> str:
    text = str(value or "").strip()
    return "" if text == "auto" else text


def _int_value(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _float_value(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bool_state(value: Any) -> bool:
    return str(value or "").strip().lower() in {"on", "true", "1", "yes", "problem"}


def _active_state(value: Any) -> bool:
    return str(value or "").strip().lower() in {"on", "open", "opening", "true", "1"}
