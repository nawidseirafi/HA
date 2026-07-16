from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .models import GardenReason, ZoneDecision, ZoneEvaluationInput


class GardenDecisionEngine:
    def evaluate_zone(self, data: ZoneEvaluationInput) -> ZoneDecision:
        cfg = data.config
        moisture_cfg = cfg.get("moisture", {})
        temperature_cfg = cfg.get("temperature", {})
        irrigation_cfg = cfg.get("irrigation", {})
        mower_cfg = cfg.get("mower", {})
        weather_cfg = cfg.get("weather", {})

        dry_below = _float(moisture_cfg.get("dry_below"), 25)
        critical_below = _float(moisture_cfg.get("critical_below"), 15)
        wet_above = _float(moisture_cfg.get("wet_above"), 60)
        default_duration = int(_float(irrigation_cfg.get("default_duration_minutes"), 20))
        max_duration = int(_float(irrigation_cfg.get("max_duration_minutes"), 30))

        reasons: list[GardenReason] = []
        blocks: list[GardenReason] = []

        status = "unknown"
        decision = "monitor"
        duration = min(default_duration, max_duration)

        if not data.agent_enabled:
            blocks.append(_reason("agent_disabled", "Der Garden Agent ist deaktiviert."))
        if not data.moisture_available:
            blocks.append(_reason("soil_moisture_unavailable", "Der Bodenfeuchtesensor ist nicht verfügbar."))
        if data.moisture is None or not 0 <= data.moisture <= 100:
            blocks.append(_reason("soil_moisture_invalid", "Die Bodenfeuchte ist nicht numerisch plausibel."))
        if _is_stale(data.moisture_last_updated, int(_float(irrigation_cfg.get("sensor_max_age_minutes"), 180)), data.evaluated_at):
            blocks.append(_reason("soil_moisture_stale", "Der Bodenfeuchtewert ist veraltet."))

        if data.moisture is not None and 0 <= data.moisture <= 100:
            if data.moisture < critical_below:
                status = "critically_dry"
                decision = "irrigate"
                reasons.append(_reason(
                    "soil_moisture_critical",
                    f"Die Bodenfeuchte liegt mit {data.moisture:g} % unter dem kritischen Grenzwert von {critical_below:g} %.",
                ))
            elif data.moisture < dry_below:
                status = "dry"
                decision = "irrigate"
                reasons.append(_reason(
                    "soil_moisture_below_threshold",
                    f"Die Bodenfeuchte liegt mit {data.moisture:g} % unter dem Grenzwert von {dry_below:g} %.",
                ))
            elif data.moisture > wet_above:
                status = "wet"
                decision = "no_action"
                reasons.append(_reason("soil_wet", f"Die Bodenfeuchte liegt mit {data.moisture:g} % über {wet_above:g} %."))
            else:
                status = "healthy"
                decision = "no_action"
                reasons.append(_reason("soil_moisture_ok", f"Die Bodenfeuchte liegt mit {data.moisture:g} % im Zielbereich."))

        if data.soil_warning is True:
            reasons.append(_reason("soil_warning_active", "Der Sensor meldet eine Bodenwarnung."))

        if data.soil_temperature is not None:
            min_temp = _float(temperature_cfg.get("irrigation_min_c"), 5)
            max_temp = _float(temperature_cfg.get("irrigation_max_c"), 32)
            if data.soil_temperature < min_temp:
                blocks.append(_reason("soil_temperature_too_low", f"Die Bodentemperatur liegt mit {data.soil_temperature:g} °C unter {min_temp:g} °C."))
            if data.soil_temperature > max_temp:
                blocks.append(_reason("soil_temperature_too_high", f"Die Bodentemperatur liegt mit {data.soil_temperature:g} °C über {max_temp:g} °C."))

        if data.irrigation_active is True:
            if decision == "irrigate":
                decision = "no_action"
            blocks.append(_reason("irrigation_already_active", "Die Bewässerung ist bereits aktiv."))
        if not data.irrigation_available:
            blocks.append(_reason("irrigation_unavailable", "Das Bewässerungsventil ist nicht verfügbar."))

        block_states = set(mower_cfg.get("irrigation_block_states") or ["mowing", "starting", "returning"])
        if bool(mower_cfg.get("enabled", True)) and data.mower_status in block_states:
            blocks.append(_reason("mower_active", "Der Mähroboter ist aktiv oder fährt zurück. Bewässerung ist blockiert."))

        if bool(weather_cfg.get("rain_block_enabled", True)):
            if data.rain_active is True:
                blocks.append(_reason("rain_active", "Es regnet aktuell."))
            probability_limit = _float(weather_cfg.get("rain_probability_block_above"), 60)
            if data.rain_probability is not None and data.rain_probability >= probability_limit:
                blocks.append(_reason("rain_expected", f"Die Regenwahrscheinlichkeit liegt bei {data.rain_probability:g} %."))

        if data.open_irrigation_run:
            blocks.append(_reason("open_irrigation_run", "Es existiert bereits ein offener Bewässerungslauf."))

        if _pause_active(data.last_irrigation_ended_at, _float(irrigation_cfg.get("minimum_pause_hours"), 12), data.evaluated_at):
            blocks.append(_reason("minimum_pause_active", "Die Mindestpause seit der letzten Bewässerung ist noch nicht abgelaufen."))

        automatic_enabled = bool(irrigation_cfg.get("automatic_enabled", False))
        if decision == "irrigate":
            if not data.control_enabled:
                blocks.append(_reason("control_disabled", "Die Garden-Gerätesteuerung ist deaktiviert."))
            if not automatic_enabled:
                blocks.append(_reason("automatic_control_disabled", "Die automatische Bewässerung ist deaktiviert."))
        else:
            duration = None

        apply_allowed = decision == "irrigate" and not blocks
        if decision == "irrigate" and blocks:
            visible_decision = "irrigate"
        elif blocks and status in {"unknown", "error"}:
            visible_decision = "blocked"
        else:
            visible_decision = decision

        return ZoneDecision(
            zone_id=data.zone_id,
            status=status,  # type: ignore[arg-type]
            decision=visible_decision,  # type: ignore[arg-type]
            recommended_duration_minutes=duration,
            apply_allowed=apply_allowed,
            reasons=reasons,
            blocks=blocks,
            evaluated_at=data.evaluated_at,
            input_snapshot={
                "moisture": data.moisture,
                "soil_temperature": data.soil_temperature,
                "battery": data.battery,
                "soil_warning": data.soil_warning,
                "irrigation_active": data.irrigation_active,
                "mower_status": data.mower_status,
                "rain_active": data.rain_active,
                "rain_probability": data.rain_probability,
                "last_irrigation_ended_at": data.last_irrigation_ended_at,
                "open_irrigation_run": data.open_irrigation_run,
                "control_enabled": data.control_enabled,
                "automatic_enabled": automatic_enabled,
            },
        )


def _reason(code: str, message: str) -> GardenReason:
    return GardenReason(code=code, message=message)


def _float(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _is_stale(last_updated: str | None, max_age_minutes: int, now_raw: str) -> bool:
    if max_age_minutes <= 0:
        return False
    last = _parse_dt(last_updated)
    now = _parse_dt(now_raw) or datetime.now(timezone.utc)
    if not last:
        return True
    return (now.astimezone(timezone.utc) - last.astimezone(timezone.utc)).total_seconds() > max_age_minutes * 60


def _pause_active(ended_at: str | None, minimum_pause_hours: float, now_raw: str) -> bool:
    if minimum_pause_hours <= 0:
        return False
    ended = _parse_dt(ended_at)
    now = _parse_dt(now_raw) or datetime.now(timezone.utc)
    if not ended:
        return False
    return (now.astimezone(timezone.utc) - ended.astimezone(timezone.utc)).total_seconds() < minimum_pause_hours * 3600
