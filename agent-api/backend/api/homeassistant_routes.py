import json
from datetime import datetime, timezone
from importlib import import_module
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.services.homeassistant_service import HomeAssistantService
from backend.services.waste_service import MAILBOX_ENTITY_ID, VACATION_ENTITY_ID, WASTE_ENTITY_ID, WasteService


router = APIRouter(prefix="/api/homeassistant", tags=["homeassistant"])
ha_service = HomeAssistantService()
LOW_BATTERY_THRESHOLD = 40
WALL_DEVICE_DOMAIN_PRIORITY = [
    "humidifier",
    "climate",
    "water_heater",
    "vacuum",
    "lawn_mower",
    "cover",
    "lock",
    "camera",
    "media_player",
    "light",
    "fan",
    "switch",
    "sensor",
]
WALL_DEVICE_DOMAIN_RANK = {domain: index for index, domain in enumerate(WALL_DEVICE_DOMAIN_PRIORITY)}


class ServicePayload(BaseModel):
    domain: str
    service: str
    entity_id: str | list[str] | None = None
    data: dict[str, Any] = {}


@router.get("/wall")
def wall_dashboard():
    ha_error = None
    try:
        states = ha_service.get_states()
    except Exception as exc:
        states = []
        ha_error = str(exc)

    floor_map = _floor_area_entity_map()
    area_lookup = _entity_area_lookup(floor_map)
    wall_device_groups = _wall_device_groups(states)
    lights = [_with_area_lookup(_light_item(state), area_lookup) for state in states if _wall_state_is_primary(state, wall_device_groups, "light")]
    covers = [_with_area_lookup(_cover_item(state), area_lookup) for state in states if _wall_state_is_primary(state, wall_device_groups, "cover")]
    sensors = [_with_area_lookup(_simple_item(state), area_lookup) for state in states if _wall_state_is_primary(state, wall_device_groups, "sensor")]
    switches = [_with_area_lookup(_simple_item(state), area_lookup) for state in states if _wall_state_is_primary(state, wall_device_groups, "switch")]
    fans = [_with_area_lookup(_fan_item(state), area_lookup) for state in states if _wall_state_is_primary(state, wall_device_groups, "fan")]
    humidifiers = [_with_area_lookup(_humidifier_item(state, wall_device_groups.get(_wall_device_key(state), [])), area_lookup) for state in states if _wall_state_is_primary(state, wall_device_groups, "humidifier")]
    lawn_mowers = [_with_area_lookup(_lawn_mower_item(state), area_lookup) for state in states if _wall_state_is_primary(state, wall_device_groups, "lawn_mower")]
    media_players = [_with_area_lookup(_simple_item(state), area_lookup) for state in states if _wall_state_is_primary(state, wall_device_groups, "media_player")]
    climate = [_with_area_lookup(_climate_item(state), area_lookup) for state in states if _wall_state_is_primary(state, wall_device_groups, "climate")]
    temperature_sensors = [_with_area_lookup(item, area_lookup) for item in _temperature_items(states)]
    weather = next((_weather_item(state) for state in states if _domain(state) == "weather"), None)
    post = next(
        (_simple_item(state) for state in states if state.get("entity_id") == "input_boolean.post_im_briefkasten"),
        None,
    )
    battery_items = [
        _battery_item(state)
        for state in states
        if _is_battery_state(state)
    ]
    low_batteries = [
        item for item in battery_items
        if (item["level"] is not None and item["level"] < LOW_BATTERY_THRESHOLD) or str(item["state"]).lower() == "low"
    ]
    unavailable = [
        _simple_item(state)
        for state in states
        if state.get("state") in {"unavailable", "unknown"}
    ][:40]
    problems = [
        _simple_item(state)
        for state in states
        if state.get("attributes", {}).get("device_class") == "problem" and state.get("state") == "on"
    ]
    openings = [
        _simple_item(state)
        for state in states
        if _domain(state) == "binary_sensor"
        and state.get("attributes", {}).get("device_class") in {"door", "window", "opening"}
    ]

    climate_summary = _climate_summary()
    calendar = _calendar_summary()
    household = _wall_household_summary(states, calendar)
    agents = _agent_summary(household.get("vacation"))
    waste = household.get("waste") or _waste_status()
    post = (household.get("post") or {}).get("entity") or post

    return {
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "home_assistant": {"configured": ha_service.configured(), "entity_count": len(states), "status": "error" if ha_error else "ok", "error": ha_error},
        "weather": weather,
        "lights": lights,
        "light_groups": _group_lights_by_floor(lights, floor_map),
        "covers": covers,
        "sensors": sorted(sensors, key=lambda item: (item.get("area") or "", item.get("name") or "")),
        "switches": switches,
        "fans": sorted(fans, key=lambda item: (item.get("area") or "", item.get("name") or "")),
        "humidifiers": sorted(humidifiers, key=lambda item: (item.get("area") or "", item.get("name") or "")),
        "lawn_mowers": sorted(lawn_mowers, key=lambda item: (item.get("area") or "", item.get("name") or "")),
        "media_players": media_players,
        "climate": climate,
        "temperature_sensors": sorted(temperature_sensors, key=lambda item: (item.get("area") or "", item.get("name") or "")),
        "climate_summary": climate_summary,
        "security": {
            "openings_total": len(openings),
            "openings_open": len([item for item in openings if item["state"] == "on"]),
            "openings": openings,
            "problems": problems,
        },
        "health": {
            "battery_total": len(battery_items),
            "batteries": sorted(battery_items, key=lambda item: (item.get("level") is None, item.get("level") or 999, item.get("name") or "")),
            "low_batteries": low_batteries[:30],
            "unavailable": unavailable,
        },
        "agents": agents,
        "post": post,
        "waste": waste,
        "calendar": calendar,
        "household": household,
    }


@router.get("/energy")
def energy_overview():
    try:
        return ha_service.get_energy_overview()
    except Exception as exc:
        return {
            "power": None,
            "power_avg": None,
            "phases": {"l1": None, "l2": None, "l3": None},
            "energy": {"meter": {"import_kwh": None, "export_kwh": None}, "today": None},
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "status": "unavailable",
            "error": str(exc),
            "pv_power": None,
            "battery_power": None,
            "battery_soc": None,
            "grid_power": None,
            "ev_charger_power": None,
            "cost_today": None,
            "forecast": None,
        }


@router.post("/service")
def call_homeassistant_service(payload: ServicePayload):
    data = dict(payload.data or {})
    if payload.entity_id:
        data["entity_id"] = payload.entity_id
    try:
        return ha_service.call_service(payload.domain, payload.service, data)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def _agent_summary(vacation_context: dict[str, Any] | None = None) -> dict[str, Any]:
    invoices: dict[str, Any]
    market: dict[str, Any]
    mywellness: dict[str, Any]
    vacation: dict[str, Any]
    try:
        invoice_service = import_module("backend.agents.invoices.routes").invoice_service
        invoice_summary = invoice_service.summary()
        invoice_status = invoice_service.status()
        invoices = {
            "status": "ok",
            "total": invoice_summary.get("total_invoices", 0),
            "needs_review": invoice_summary.get("needs_review_count", 0),
            "errors": invoice_summary.get("ai_error_count", 0),
            "enabled": invoice_status.get("enabled", False),
            "is_running": invoice_status.get("is_running", False),
            "next_scheduled_run": invoice_status.get("next_scheduled_run"),
            "schedule": invoice_status.get("schedule", []),
            "last_status": invoice_status.get("last_status"),
        }
    except Exception as exc:
        invoices = {"status": "error", "error": str(exc)}
    try:
        mywellness_service = import_module("backend.agents.mywellness.routes").mywellness_service
        mywellness = mywellness_service.status()
    except Exception as exc:
        mywellness = {"status": "error", "error": str(exc)}
    try:
        MarketReportService = import_module("backend.agents.market.report_service").MarketReportService
        market_summary = MarketReportService().summary()
        market = {
            "status": "paused",
            "watchlist_count": market_summary.get("watchlist_count", 0),
            "enabled_count": market_summary.get("enabled_count", 0),
            "signals": market_summary.get("signals", {}),
        }
    except Exception as exc:
        market = {"status": "error", "error": str(exc)}
    vacation = _wall_vacation_agent_summary(vacation_context)
    return {"invoices": invoices, "mywellness": mywellness, "market": market, "vacation": vacation}


def _wall_vacation_agent_summary(vacation_context: dict[str, Any] | None = None) -> dict[str, Any]:
    active = vacation_context.get("vacation_mode") if isinstance(vacation_context, dict) else None
    summary = {
        "status": "active",
        "enabled": True,
        "is_running": False,
        "vacation_mode": {"active": active, "source": VACATION_ENTITY_ID},
        "vacation_mode_active": active,
    }
    try:
        vacation_service = import_module("backend.agents.vacation.routes").vacation_service
        config = vacation_service.config()
        summary["enabled"] = bool(config.get("enabled", True))
        summary["status"] = "active" if summary["enabled"] else "disabled"
        summary["schedule_times"] = config.get("schedule_times", [])
    except Exception as exc:
        summary["error"] = str(exc)
    return summary


def _household_summary() -> dict[str, Any]:
    try:
        WasteService = import_module("backend.services.waste_service").WasteService
        HouseholdService = import_module("backend.services.household_service").HouseholdService
        waste_service = WasteService(ha_service)
        vacation_status_provider = None
        try:
            vacation_status_provider = import_module("backend.agents.vacation.routes").vacation_service.status
        except Exception:
            vacation_status_provider = None
        return HouseholdService(
            ha_service=ha_service,
            waste_service=waste_service,
            vacation_status_provider=vacation_status_provider,
        ).summary()
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _wall_household_summary(states: list[dict[str, Any]], calendar: dict[str, Any] | None = None) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    by_entity = {str(state.get("entity_id") or ""): state for state in states}
    post = _wall_post_status(by_entity.get(MAILBOX_ENTITY_ID))
    vacation = _wall_vacation_status(by_entity.get(VACATION_ENTITY_ID))
    waste = _wall_waste_status(by_entity.get(WASTE_ENTITY_ID), vacation.get("vacation_mode"), post.get("has_mail"))
    infrastructure = {
        "ok": True,
        "updated_at": now,
        "status": "unknown",
        "label": "Netzwerk",
        "detail": "Wird separat aktualisiert",
        "router": "Fritzbox",
        "connected_devices": None,
        "wifi": "unknown",
        "checks": {},
    }
    calendar = calendar or _calendar_summary()
    comfort = {"bedroom_fan": {"ok": True, "status": "unknown", "decision": {"status": "unknown"}}}
    reminders = _wall_reminders(waste, post, vacation, infrastructure)
    return {
        "ok": True,
        "updated_at": now,
        "waste": waste,
        "post": post,
        "vacation": vacation,
        "infrastructure": infrastructure,
        "calendar": calendar,
        "comfort": comfort,
        "reminders": reminders,
        "counts": {
            "reminders": len(reminders),
            "high_priority": len([item for item in reminders if item.get("priority") == "high"]),
            "waste_items": len(waste.get("items", [])) if isinstance(waste, dict) else 0,
            "calendar_events_today": int(calendar.get("today_count") or 0) if isinstance(calendar, dict) else 0,
        },
        "state": {
            "mailbox_has_mail": post.get("has_mail"),
            "vacation_mode": vacation.get("vacation_mode"),
            "next_waste": waste.get("next") if isinstance(waste, dict) else None,
            "next_calendar_event": calendar.get("next_event") if isinstance(calendar, dict) else None,
            "infrastructure_status": "unknown",
            "bedroom_fan_status": "unknown",
        },
    }


def _wall_post_status(state: dict[str, Any] | None) -> dict[str, Any]:
    if not state:
        return {"ok": True, "entity_id": MAILBOX_ENTITY_ID, "has_mail": None, "entity": None}
    value = str(state.get("state") or "").lower()
    return {
        "ok": True,
        "entity_id": MAILBOX_ENTITY_ID,
        "has_mail": value == "on" if value not in {"", "unknown", "unavailable"} else None,
        "entity": _simple_item(state),
    }


def _wall_vacation_status(state: dict[str, Any] | None) -> dict[str, Any]:
    if not state:
        return {"ok": True, "available": False, "vacation_mode": None}
    value = str(state.get("state") or "").lower()
    return {
        "ok": True,
        "available": True,
        "vacation_mode": value == "on" if value not in {"", "unknown", "unavailable"} else None,
        "source": VACATION_ENTITY_ID,
        "updated_at": state.get("last_changed") or state.get("last_updated"),
    }


def _wall_waste_status(state: dict[str, Any] | None, vacation_mode: bool | None, mailbox_has_mail: bool | None) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if not state:
        return {
            "ok": False,
            "updated_at": now,
            "next": None,
            "items": [],
            "context": {"vacation_mode": vacation_mode, "mailbox_has_mail": mailbox_has_mail},
            "reminders": [],
            "source_entity": WASTE_ENTITY_ID,
            "error": f"Home Assistant Entity nicht gefunden: {WASTE_ENTITY_ID}",
        }
    try:
        normalized = WasteService(ha_service).normalize({**state, "attributes": state.get("attributes") or {}})
        context = {"vacation_mode": vacation_mode, "mailbox_has_mail": mailbox_has_mail}
        reminders = WasteService(ha_service).reminders(normalized.get("items", []), context)
        return {
            "ok": True,
            "updated_at": now,
            "next": normalized.get("next"),
            "items": normalized.get("items", []),
            "context": context,
            "reminders": reminders,
            "source_entity": WASTE_ENTITY_ID,
            "raw": normalized.get("raw"),
        }
    except Exception as exc:
        return {
            "ok": False,
            "updated_at": now,
            "next": None,
            "items": [],
            "context": {"vacation_mode": vacation_mode, "mailbox_has_mail": mailbox_has_mail},
            "reminders": [],
            "source_entity": WASTE_ENTITY_ID,
            "error": str(exc),
        }


def _wall_reminders(waste: dict[str, Any], post: dict[str, Any], vacation: dict[str, Any], infrastructure: dict[str, Any]) -> list[dict[str, str]]:
    reminders: list[dict[str, str]] = []
    for item in waste.get("reminders", []) if isinstance(waste, dict) else []:
        if isinstance(item, dict):
            reminders.append({
                "priority": str(item.get("priority") or "medium"),
                "message": str(item.get("message") or ""),
                "reason": str(item.get("reason") or "Abfallstatus"),
                "source": "waste",
            })
    if post.get("has_mail") is True:
        reminders.append({"priority": "medium", "message": "Post im Briefkasten", "reason": "Briefkasten meldet Post.", "source": "post"})
    if vacation.get("vacation_mode") is True and post.get("has_mail") is True:
        reminders.append({
            "priority": "high",
            "message": "Post trotz Urlaubsmodus beachten",
            "reason": "Urlaubsmodus ist aktiv und Briefkasten meldet Post.",
            "source": "household",
        })
    infrastructure_status = str(infrastructure.get("status") or "")
    if infrastructure_status in {"down", "critical"}:
        reminders.append({"priority": "high", "message": "Internet oder Netzwerk gestört", "reason": str(infrastructure.get("detail") or ""), "source": "infrastructure"})
    elif infrastructure_status in {"unstable", "warning"}:
        reminders.append({"priority": "medium", "message": "Internet oder Netzwerk instabil", "reason": str(infrastructure.get("detail") or ""), "source": "infrastructure"})
    return reminders


def _waste_status() -> dict[str, Any]:
    try:
        WasteService = import_module("backend.services.waste_service").WasteService
        return WasteService(ha_service).status()
    except Exception as exc:
        return {"ok": False, "items": [], "reminders": [], "error": str(exc)}


def _calendar_summary() -> dict[str, Any]:
    try:
        CalendarService = import_module("backend.services.calendar_service").CalendarService
        return CalendarService().today_summary()
    except Exception as exc:
        return {"ok": False, "today_count": 0, "next_event": None, "upcoming": [], "source": "stub", "error": str(exc)}


def _domain(state: dict[str, Any]) -> str:
    return str(state.get("entity_id", "")).split(".", 1)[0]


def _wall_device_groups(states: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for state in states:
        domain = _domain(state)
        if domain not in WALL_DEVICE_DOMAIN_RANK:
            continue
        groups.setdefault(_wall_device_key(state), []).append(state)
    return groups


def _wall_state_is_primary(state: dict[str, Any], groups: dict[str, list[dict[str, Any]]], expected_domain: str) -> bool:
    domain = _domain(state)
    if domain != expected_domain:
        return False
    group = groups.get(_wall_device_key(state), [state])
    return _wall_primary_domain(group) == expected_domain


def _wall_primary_domain(states: list[dict[str, Any]]) -> str:
    domains = {_domain(state) for state in states}
    return min(domains, key=lambda domain: WALL_DEVICE_DOMAIN_RANK.get(domain, 999))


def _wall_device_key(state: dict[str, Any]) -> str:
    attributes = state.get("attributes", {})
    for key in ("device_id", "device"):
        value = attributes.get(key) or state.get(key)
        if value:
            return f"device:{value}"
    domain = _domain(state)
    object_id = str(state.get("entity_id") or "").split(".", 1)[-1]
    return f"name:{_wall_base_object_id(object_id, domain)}"


def _wall_base_object_id(object_id: str, domain: str = "") -> str:
    text = str(object_id or "").lower()
    suffixes = [
        "current_humidity",
        "target_humidity",
        "relative_humidity",
        "air_humidity",
        "humidity",
        "luftfeuchtigkeit",
        "current_temperature",
        "temperature",
        "temperatur",
        "water_tank",
        "tank_status",
        "tank_full",
        "tank",
        "water",
        "mode",
        "preset_mode",
        "fan_mode",
        "fan",
        "power",
        "switch",
        "status",
        "state",
    ]
    changed = True
    while changed:
        changed = False
        for suffix in suffixes:
            token = f"_{suffix}"
            if text.endswith(token) and len(text) > len(token) + 2:
                text = text[: -len(token)]
                changed = True
    if not text and domain:
        text = str(object_id or "").lower()
    return text or str(object_id or "").lower()


def _name(state: dict[str, Any]) -> str:
    attributes = state.get("attributes", {})
    return attributes.get("friendly_name") or str(state.get("entity_id", "")).replace("_", " ")


def _area_name(state: dict[str, Any]) -> str:
    attributes = state.get("attributes", {})
    for key in ("area", "area_id", "room", "room_name"):
        value = attributes.get(key)
        if value:
            return _label(str(value))
    entity_id = str(state.get("entity_id", ""))
    slug = entity_id.split(".", 1)[-1]
    first = slug.split("_", 1)[0]
    if first and first not in {"light", "switch", "sensor", "binary"}:
        return _label(first)
    return "Haus"


def _label(value: str) -> str:
    return value.replace("_", " ").replace("-", " ").strip().title()


def _simple_item(state: dict[str, Any]) -> dict[str, Any]:
    attributes = state.get("attributes", {})
    return {
        "entity_id": state.get("entity_id"),
        "name": _name(state),
        "state": state.get("state"),
        "area": _area_name(state),
        "device_class": attributes.get("device_class"),
        "unit": attributes.get("unit_of_measurement"),
    }


def _light_item(state: dict[str, Any]) -> dict[str, Any]:
    attributes = state.get("attributes", {})
    brightness = attributes.get("brightness")
    brightness_pct = round((int(brightness) / 255) * 100) if brightness is not None else None
    return {
        **_simple_item(state),
        "on": state.get("state") == "on",
        "brightness_pct": brightness_pct,
        "supported_color_modes": attributes.get("supported_color_modes") or [],
    }


def _cover_item(state: dict[str, Any]) -> dict[str, Any]:
    attributes = state.get("attributes", {})
    position = attributes.get("current_position")
    return {
        **_simple_item(state),
        "position": _numeric_value(position),
        "supported_features": attributes.get("supported_features"),
        "device_class": attributes.get("device_class") or "cover",
    }


def _fan_item(state: dict[str, Any]) -> dict[str, Any]:
    attributes = state.get("attributes", {})
    return {
        **_simple_item(state),
        "percentage": _numeric_value(attributes.get("percentage")),
        "percentage_step": _numeric_value(attributes.get("percentage_step")),
        "preset_mode": attributes.get("preset_mode"),
        "preset_modes": attributes.get("preset_modes") or [],
        "oscillating": attributes.get("oscillating"),
        "direction": attributes.get("direction"),
        "supported_features": attributes.get("supported_features"),
    }


def _humidifier_item(state: dict[str, Any], group_states: list[dict[str, Any]]) -> dict[str, Any]:
    attributes = state.get("attributes", {})
    fan_state = next((item for item in group_states if _domain(item) == "fan"), None)
    sensor_states = [item for item in group_states if _domain(item) == "sensor"]
    switch_state = next((item for item in group_states if _domain(item) == "switch"), None)
    tank_state = _find_related_sensor(sensor_states, ("tank", "water", "wasser", "behälter", "behaelter"))
    temperature_state = _find_related_sensor(sensor_states, ("temperature", "temperatur"))
    humidity_state = _find_related_sensor(sensor_states, ("humidity", "luftfeuchtigkeit", "feuchtigkeit"))
    fan_item = _fan_item(fan_state) if fan_state else None
    return {
        **_simple_item(state),
        "device_type": "Luftentfeuchter",
        "current_humidity": _first_numeric(
            attributes.get("current_humidity"),
            attributes.get("humidity"),
            humidity_state.get("state") if humidity_state else None,
        ),
        "target_humidity": _first_numeric(
            attributes.get("humidity"),
            attributes.get("target_humidity"),
            attributes.get("target_humidity_high"),
        ),
        "min_humidity": _numeric_value(attributes.get("min_humidity")),
        "max_humidity": _numeric_value(attributes.get("max_humidity")),
        "temperature": _first_numeric(
            attributes.get("temperature"),
            attributes.get("current_temperature"),
            temperature_state.get("state") if temperature_state else None,
        ),
        "tank_status": _tank_status(tank_state),
        "mode": attributes.get("mode") or attributes.get("preset_mode"),
        "modes": attributes.get("available_modes") or attributes.get("modes") or [],
        "supported_features": attributes.get("supported_features"),
        "fan": fan_item,
        "fan_entity_id": fan_state.get("entity_id") if fan_state else None,
        "fan_state": fan_state.get("state") if fan_state else None,
        "switch_entity_id": switch_state.get("entity_id") if switch_state else None,
        "associated_entity_ids": sorted(
            str(item.get("entity_id"))
            for item in group_states
            if item.get("entity_id") and item.get("entity_id") != state.get("entity_id")
        ),
    }


def _find_related_sensor(states: list[dict[str, Any]], needles: tuple[str, ...]) -> dict[str, Any] | None:
    for state in states:
        text = f"{state.get('entity_id', '')} {_name(state)} {state.get('attributes', {}).get('device_class', '')}".lower()
        if any(needle in text for needle in needles):
            return state
    return None


def _first_numeric(*values: Any) -> float | None:
    for value in values:
        numeric = _numeric_value(value)
        if numeric is not None:
            return numeric
    return None


def _tank_status(state: dict[str, Any] | None) -> str | None:
    if not state:
        return None
    value = str(state.get("state") or "").strip()
    if not value:
        return None
    normalized = value.lower()
    if normalized in {"on", "full", "problem", "detected"}:
        return "Voll"
    if normalized in {"off", "ok", "clear", "empty"}:
        return "OK"
    return value


def _lawn_mower_item(state: dict[str, Any]) -> dict[str, Any]:
    attributes = state.get("attributes", {})
    supported_features = attributes.get("supported_features")
    return {
        **_simple_item(state),
        "battery_level": _lawn_mower_battery_level(attributes),
        "raw_status": attributes.get("status"),
        "supported_features": supported_features if isinstance(supported_features, int) else _numeric_int(supported_features),
        "last_updated": state.get("last_updated") or state.get("last_changed"),
        "available": state.get("state") not in {"unavailable", "unknown"},
    }


def _climate_item(state: dict[str, Any]) -> dict[str, Any]:
    attributes = state.get("attributes", {})
    return {
        **_simple_item(state),
        "current_temperature": attributes.get("current_temperature"),
        "target_temperature": attributes.get("temperature"),
        "humidity": attributes.get("current_humidity"),
        "hvac_action": attributes.get("hvac_action"),
        "hvac_modes": attributes.get("hvac_modes") if isinstance(attributes.get("hvac_modes"), list) else [],
    }


def _weather_item(state: dict[str, Any]) -> dict[str, Any]:
    attributes = state.get("attributes", {})
    return {
        **_simple_item(state),
        "temperature": _numeric_value(attributes.get("temperature")),
        "humidity": _numeric_value(attributes.get("humidity")),
    }


def _temperature_item(state: dict[str, Any]) -> dict[str, Any]:
    item = _simple_item(state)
    return {**item, "temperature": _numeric_value(state.get("state")), "humidity": None}


def _humidity_item(state: dict[str, Any]) -> dict[str, Any]:
    item = _simple_item(state)
    return {**item, "temperature": None, "humidity": _numeric_value(state.get("state"))}


def _temperature_items(states: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_area: dict[str, list[dict[str, Any]]] = {}
    for state in states:
        if _is_temperature_state(state):
            item = _temperature_item(state)
        elif _is_humidity_state(state):
            item = _humidity_item(state)
        else:
            continue
        by_area.setdefault(item.get("area") or "Haus", []).append(item)

    combined = []
    for items in by_area.values():
        combined.extend(items)
    return combined


def _is_temperature_state(state: dict[str, Any]) -> bool:
    attributes = state.get("attributes", {})
    if _domain(state) != "sensor":
        return False
    device_class = str(attributes.get("device_class") or "").lower()
    unit = str(attributes.get("unit_of_measurement") or "").strip().lower()
    if device_class != "temperature" and unit not in {"°c", "c", "°f", "f"}:
        return False
    return _numeric_value(state.get("state")) is not None


def _is_humidity_state(state: dict[str, Any]) -> bool:
    attributes = state.get("attributes", {})
    if _domain(state) != "sensor":
        return False
    device_class = str(attributes.get("device_class") or "").lower()
    unit = str(attributes.get("unit_of_measurement") or "").strip().lower()
    if device_class != "humidity":
        text = f"{state.get('entity_id', '')} {_name(state)}".lower()
        if unit != "%" or not any(needle in text for needle in ("humidity", "luftfeuchtigkeit", "feuchtigkeit")):
            return False
    return _numeric_value(state.get("state")) is not None


def _battery_item(state: dict[str, Any]) -> dict[str, Any]:
    item = _simple_item(state)
    level = _battery_level(state)
    return {**item, "level": level}


def _is_battery_state(state: dict[str, Any]) -> bool:
    entity_id = str(state.get("entity_id") or "").lower()
    if not entity_id.startswith("sensor."):
        return False
    object_id = entity_id.split(".", 1)[1]
    if not object_id.endswith(("_battery", "_batterie")):
        return False
    attributes = state.get("attributes", {})
    unit = str(attributes.get("unit_of_measurement") or "").strip()
    state_value = str(state.get("state") or "").strip().lower()
    return unit == "%" or _is_numeric_state(state_value) or state_value in {
        "critical",
        "empty",
        "low",
        "medium",
        "normal",
        "high",
        "full",
        "ok",
        "charging",
        "unknown",
        "unavailable",
    }


def _battery_level(state: dict[str, Any]) -> float | None:
    raw_state = state.get("state")
    value = _numeric_value(raw_state)
    if value is None:
        return _text_battery_level(raw_state)
    unit = str(state.get("attributes", {}).get("unit_of_measurement") or "").strip().lower()
    if unit in {"v", "mv"}:
        return None
    if 0 <= value <= 100:
        return value
    return None


def _text_battery_level(value: Any) -> float | None:
    text = str(value or "").strip().lower()
    mapping = {
        "critical": 5.0,
        "empty": 5.0,
        "low": 10.0,
        "medium": 50.0,
        "normal": 75.0,
        "high": 100.0,
        "full": 100.0,
        "ok": 100.0,
        "charging": 100.0,
    }
    return mapping.get(text)


def _numeric_value(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", ".")
    if not _is_numeric_state(text):
        return None
    return float(text)


def _numeric_int(value: Any) -> int | None:
    numeric = _numeric_value(value)
    if numeric is None:
        return None
    return int(numeric)


def _lawn_mower_battery_level(attributes: dict[str, Any]) -> float | None:
    for key in ("battery_level", "battery", "battery_percent", "battery_percentage"):
        value = _numeric_value(attributes.get(key))
        if value is not None and 0 <= value <= 100:
            return value
    return None


def _is_numeric_state(value: str) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def _group_by_area(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        groups.setdefault(item.get("area") or "Haus", []).append(item)
    return [
        _light_group(area, area_items)
        for area, area_items in sorted(groups.items())
    ]


def _group_lights_by_floor(lights: list[dict[str, Any]], floor_map: dict[str, dict[str, list[str]]] | None = None) -> list[dict[str, Any]]:
    floor_map = floor_map or _floor_area_entity_map()
    if not floor_map:
        return _group_by_area(lights)

    by_entity = {item["entity_id"]: item for item in lights}
    assigned: set[str] = set()
    groups: list[dict[str, Any]] = []
    for floor, areas in floor_map.items():
        rooms: list[dict[str, Any]] = []
        for area, entity_ids in areas.items():
            room_lights = [by_entity[entity_id] for entity_id in entity_ids if entity_id in by_entity]
            assigned.update(item["entity_id"] for item in room_lights)
            rooms.append(_light_room(area, room_lights))
        floor_lights = [light for room in rooms for light in room["items"]]
        if not rooms:
            continue
        groups.append(_light_group(floor, floor_lights, rooms=rooms))

    remaining = [item for item in lights if item["entity_id"] not in assigned]
    if remaining:
        groups.append(_light_group("Ohne Etage", remaining))
    return groups


def _entity_area_lookup(floor_map: dict[str, dict[str, list[str]]]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for areas in floor_map.values():
        for area, entity_ids in areas.items():
            for entity_id in entity_ids:
                lookup[entity_id] = area
    return lookup


def _with_area_lookup(item: dict[str, Any], area_lookup: dict[str, str]) -> dict[str, Any]:
    entity_id = str(item.get("entity_id") or "")
    area = area_lookup.get(entity_id)
    if area:
        return {**item, "area": area}
    inferred_area = _infer_area_from_known_rooms(item, area_lookup.values())
    if inferred_area:
        return {**item, "area": inferred_area}
    return item


def _infer_area_from_known_rooms(item: dict[str, Any], known_areas: Any) -> str:
    entity_id = str(item.get("entity_id") or "")
    name = str(item.get("name") or "")
    text = f" {_normalize_area_text(entity_id)} {_normalize_area_text(name)} "
    for area in sorted({str(value) for value in known_areas if value}, key=len, reverse=True):
        normalized_area = _normalize_area_text(area)
        if len(normalized_area) < 3:
            continue
        if f" {normalized_area} " in text:
            return area
    return ""


def _normalize_area_text(value: str) -> str:
    return " ".join(
        str(value or "")
        .lower()
        .replace(".", " ")
        .replace("_", " ")
        .replace("-", " ")
        .split()
    )


def _light_group(label: str, lights: list[dict[str, Any]], rooms: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "area": _label(label),
        "total": len(lights),
        "on": len([item for item in lights if item.get("on")]),
        "items": sorted(lights, key=lambda item: item.get("name") or ""),
        "rooms": sorted(rooms or _rooms_from_lights(lights), key=lambda item: item.get("area") or ""),
    }


def _light_room(label: str, lights: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "area": _label(label),
        "total": len(lights),
        "on": len([item for item in lights if item.get("on")]),
        "items": sorted(lights, key=lambda item: item.get("name") or ""),
    }


def _rooms_from_lights(lights: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rooms: dict[str, list[dict[str, Any]]] = {}
    for light in lights:
        rooms.setdefault(light.get("area") or "Raum", []).append(light)
    return [_light_room(area, room_lights) for area, room_lights in rooms.items()]


def _climate_summary() -> dict[str, float | None]:
    template = """
{% set basement_temps = namespace(values=[]) %}
{% set basement_hums = namespace(values=[]) %}
{% for area in floor_areas('Basement') %}
  {% for entity_id in area_entities(area) %}
    {% set state = states(entity_id) %}
    {% if state not in ['unknown', 'unavailable', 'none'] %}
      {% if state_attr(entity_id, 'device_class') == 'temperature' %}
        {% set val = state | float(none) %}
        {% if val is not none %}
          {% set basement_temps.values = basement_temps.values + [val] %}
        {% endif %}
      {% endif %}
      {% if state_attr(entity_id, 'device_class') == 'humidity' %}
        {% set val = state | float(none) %}
        {% if val is not none %}
          {% set basement_hums.values = basement_hums.values + [val] %}
        {% endif %}
      {% endif %}
      {% set h_temp = state_attr(entity_id, 'current_temperature') %}
      {% if h_temp is not none %}
        {% set basement_temps.values = basement_temps.values + [h_temp | float] %}
      {% endif %}
      {% set h_hum = state_attr(entity_id, 'current_humidity') %}
      {% if h_hum is not none %}
        {% set basement_hums.values = basement_hums.values + [h_hum | float] %}
      {% endif %}
    {% endif %}
  {% endfor %}
{% endfor %}
{% set house_temps = namespace(values=[]) %}
{% set house_hums = namespace(values=[]) %}
{% for floor in floors() %}
  {% if floor != 'Basement' %}
    {% for area in floor_areas(floor) %}
      {% for entity_id in area_entities(area) %}
        {% set state = states(entity_id) %}
        {% if state not in ['unknown', 'unavailable', 'none'] %}
          {% if state_attr(entity_id, 'device_class') == 'temperature' %}
            {% set val = state | float(none) %}
            {% if val is not none %}
              {% set house_temps.values = house_temps.values + [val] %}
            {% endif %}
          {% endif %}
          {% if state_attr(entity_id, 'device_class') == 'humidity' %}
            {% set val = state | float(none) %}
            {% if val is not none %}
              {% set house_hums.values = house_hums.values + [val] %}
            {% endif %}
          {% endif %}
          {% set h_temp = state_attr(entity_id, 'current_temperature') %}
          {% if h_temp is not none %}
            {% set house_temps.values = house_temps.values + [h_temp | float] %}
          {% endif %}
          {% set h_hum = state_attr(entity_id, 'current_humidity') %}
          {% if h_hum is not none %}
            {% set house_hums.values = house_hums.values + [h_hum | float] %}
          {% endif %}
        {% endif %}
      {% endfor %}
    {% endfor %}
  {% endif %}
{% endfor %}
{{ {
  'house_temp': ((house_temps.values | sum) / (house_temps.values | length)) | round(1) if house_temps.values | length > 0 else none,
  'house_humidity': ((house_hums.values | sum) / (house_hums.values | length)) | round(0) if house_hums.values | length > 0 else none,
  'basement_temp': ((basement_temps.values | sum) / (basement_temps.values | length)) | round(1) if basement_temps.values | length > 0 else none,
  'basement_humidity': ((basement_hums.values | sum) / (basement_hums.values | length)) | round(0) if basement_hums.values | length > 0 else none
} | to_json }}
"""
    try:
        rendered = ha_service.render_template(template).strip()
        data = json.loads(rendered)
    except Exception:
        return {"house_temp": None, "house_humidity": None, "basement_temp": None, "basement_humidity": None}
    if not isinstance(data, dict):
        return {"house_temp": None, "house_humidity": None, "basement_temp": None, "basement_humidity": None}
    return {
        "house_temp": _numeric_value(data.get("house_temp")),
        "house_humidity": _numeric_value(data.get("house_humidity")),
        "basement_temp": _numeric_value(data.get("basement_temp")),
        "basement_humidity": _numeric_value(data.get("basement_humidity")),
    }


def _floor_area_entity_map() -> dict[str, dict[str, list[str]]]:
    template = """
{% set ns = namespace(items=[]) %}
{% set assigned = namespace(ids=[]) %}
{% for floor in floors() %}
  {% set floor_ns = namespace(areas=[]) %}
  {% for area in floor_areas(floor) %}
    {% set assigned.ids = assigned.ids + [area] %}
    {% set area_ns = namespace(entities=[]) %}
    {% for entity_id in area_entities(area) %}
      {% set area_ns.entities = area_ns.entities + [entity_id] %}
    {% endfor %}
    {% set display_name = area_name(area) or area %}
    {% set floor_ns.areas = floor_ns.areas + [{'area': display_name, 'area_id': area, 'entities': area_ns.entities}] %}
  {% endfor %}
  {% set ns.items = ns.items + [{'floor': floor, 'areas': floor_ns.areas}] %}
{% endfor %}
{% set unassigned = namespace(areas=[]) %}
{% for area in areas() %}
  {% if area not in assigned.ids %}
    {% set area_ns = namespace(entities=[]) %}
    {% for entity_id in area_entities(area) %}
      {% set area_ns.entities = area_ns.entities + [entity_id] %}
    {% endfor %}
    {% if area_ns.entities | length > 0 %}
      {% set display_name = area_name(area) or area %}
      {% set unassigned.areas = unassigned.areas + [{'area': display_name, 'area_id': area, 'entities': area_ns.entities}] %}
    {% endif %}
  {% endif %}
{% endfor %}
{% if unassigned.areas | length > 0 %}
  {% set ns.items = ns.items + [{'floor': 'Ohne Etage', 'areas': unassigned.areas}] %}
{% endif %}
{{ ns.items | to_json }}
"""
    try:
        rendered = ha_service.render_template(template).strip()
        data = json.loads(rendered)
    except Exception:
        return {}
    if not isinstance(data, list):
        return {}
    result: dict[str, dict[str, list[str]]] = {}
    for item in data:
        if not isinstance(item, dict):
            continue
        floor = str(item.get("floor") or "").strip()
        areas = item.get("areas")
        if not floor or not isinstance(areas, list):
            continue
        result[floor] = {}
        for area_item in areas:
            if not isinstance(area_item, dict):
                continue
            area = str(area_item.get("area") or "").strip()
            entities = area_item.get("entities")
            if area and isinstance(entities, list):
                result[floor][area] = [str(entity_id) for entity_id in entities if entity_id]
    return result
