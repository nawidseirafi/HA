import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.agents.invoices.service import InvoiceService
from backend.agents.market.report_service import MarketReportService
from backend.agents.mywellness.routes import mywellness_service
from backend.services.homeassistant_service import HomeAssistantService


router = APIRouter(prefix="/api/homeassistant", tags=["homeassistant"])
ha_service = HomeAssistantService()


class ServicePayload(BaseModel):
    domain: str
    service: str
    entity_id: str | list[str] | None = None
    data: dict[str, Any] = {}


@router.get("/wall")
def wall_dashboard():
    try:
        states = ha_service.get_states()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    lights = [_light_item(state) for state in states if _domain(state) == "light"]
    switches = [_simple_item(state) for state in states if _domain(state) == "switch"]
    climate = [_climate_item(state) for state in states if _domain(state) == "climate"]
    weather = next((_simple_item(state) for state in states if _domain(state) == "weather"), None)

    battery_items = [
        _battery_item(state)
        for state in states
        if state.get("attributes", {}).get("device_class") == "battery"
    ]
    low_batteries = [
        item for item in battery_items
        if (item["level"] is not None and item["level"] <= 25) or str(item["state"]).lower() == "low"
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

    agents = _agent_summary()

    return {
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "home_assistant": {"configured": ha_service.configured(), "entity_count": len(states)},
        "weather": weather,
        "lights": lights,
        "light_groups": _group_lights_by_floor(lights),
        "switches": switches,
        "climate": climate,
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


def _agent_summary() -> dict[str, Any]:
    invoices: dict[str, Any]
    market: dict[str, Any]
    mywellness: dict[str, Any]
    try:
        invoice_summary = InvoiceService().summary()
        invoices = {
            "status": "ok",
            "total": invoice_summary.get("total_invoices", 0),
            "needs_review": invoice_summary.get("needs_review_count", 0),
            "errors": invoice_summary.get("ai_error_count", 0),
        }
    except Exception as exc:
        invoices = {"status": "error", "error": str(exc)}
    try:
        mywellness = mywellness_service.status()
    except Exception as exc:
        mywellness = {"status": "error", "error": str(exc)}
    try:
        market_summary = MarketReportService().summary()
        market = {
            "status": "ok",
            "watchlist_count": market_summary.get("watchlist_count", 0),
            "enabled_count": market_summary.get("enabled_count", 0),
            "signals": market_summary.get("signals", {}),
        }
    except Exception as exc:
        market = {"status": "error", "error": str(exc)}
    return {"invoices": invoices, "mywellness": mywellness, "market": market}


def _domain(state: dict[str, Any]) -> str:
    return str(state.get("entity_id", "")).split(".", 1)[0]


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


def _climate_item(state: dict[str, Any]) -> dict[str, Any]:
    attributes = state.get("attributes", {})
    return {
        **_simple_item(state),
        "current_temperature": attributes.get("current_temperature"),
        "target_temperature": attributes.get("temperature"),
        "humidity": attributes.get("current_humidity"),
        "hvac_action": attributes.get("hvac_action"),
    }


def _battery_item(state: dict[str, Any]) -> dict[str, Any]:
    item = _simple_item(state)
    try:
        level = float(state.get("state"))
    except (TypeError, ValueError):
        level = None
    return {**item, "level": level}


def _group_by_area(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        groups.setdefault(item.get("area") or "Haus", []).append(item)
    return [
        _light_group(area, area_items)
        for area, area_items in sorted(groups.items())
    ]


def _group_lights_by_floor(lights: list[dict[str, Any]]) -> list[dict[str, Any]]:
    floor_map = _floor_area_entity_map()
    if not floor_map:
        return _group_by_area(lights)

    by_entity = {item["entity_id"]: item for item in lights}
    assigned: set[str] = set()
    groups: list[dict[str, Any]] = []
    for floor, areas in floor_map.items():
        rooms: list[dict[str, Any]] = []
        for area, entity_ids in areas.items():
            room_lights = [by_entity[entity_id] for entity_id in entity_ids if entity_id in by_entity]
            if not room_lights:
                continue
            assigned.update(item["entity_id"] for item in room_lights)
            rooms.append(_light_room(area, room_lights))
        floor_lights = [light for room in rooms for light in room["items"]]
        if not floor_lights:
            continue
        groups.append(_light_group(floor, floor_lights, rooms=rooms))

    remaining = [item for item in lights if item["entity_id"] not in assigned]
    if remaining:
        groups.append(_light_group("Ohne Etage", remaining))
    return groups


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


def _floor_area_entity_map() -> dict[str, dict[str, list[str]]]:
    template = """
{% set ns = namespace(items=[]) %}
{% for floor in floors() %}
  {% set floor_ns = namespace(areas=[]) %}
  {% for area in floor_areas(floor) %}
    {% set area_ns = namespace(entities=[]) %}
    {% for entity_id in area_entities(area) %}
      {% set area_ns.entities = area_ns.entities + [entity_id] %}
    {% endfor %}
    {% set floor_ns.areas = floor_ns.areas + [{'area': area, 'entities': area_ns.entities}] %}
  {% endfor %}
  {% set ns.items = ns.items + [{'floor': floor, 'areas': floor_ns.areas}] %}
{% endfor %}
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
