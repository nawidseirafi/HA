import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.agents.invoices.routes import invoice_service
from backend.agents.market.report_service import MarketReportService
from backend.agents.mywellness.routes import mywellness_service
from backend.services.homeassistant_service import HomeAssistantService
from backend.services.waste_service import WasteService


router = APIRouter(prefix="/api/homeassistant", tags=["homeassistant"])
ha_service = HomeAssistantService()
waste_service = WasteService(ha_service)


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

    floor_map = _floor_area_entity_map()
    area_lookup = _entity_area_lookup(floor_map)
    lights = [_with_area_lookup(_light_item(state), area_lookup) for state in states if _domain(state) == "light"]
    covers = [_with_area_lookup(_cover_item(state), area_lookup) for state in states if _domain(state) == "cover"]
    sensors = [_with_area_lookup(_simple_item(state), area_lookup) for state in states if _domain(state) == "sensor"]
    switches = [_with_area_lookup(_simple_item(state), area_lookup) for state in states if _domain(state) == "switch"]
    media_players = [_with_area_lookup(_simple_item(state), area_lookup) for state in states if _domain(state) == "media_player"]
    climate = [_with_area_lookup(_climate_item(state), area_lookup) for state in states if _domain(state) == "climate"]
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
    climate_summary = _climate_summary()
    waste = waste_service.status()

    return {
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "home_assistant": {"configured": ha_service.configured(), "entity_count": len(states)},
        "weather": weather,
        "lights": lights,
        "light_groups": _group_lights_by_floor(lights, floor_map),
        "covers": covers,
        "sensors": sorted(sensors, key=lambda item: (item.get("area") or "", item.get("name") or "")),
        "switches": switches,
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


def _cover_item(state: dict[str, Any]) -> dict[str, Any]:
    attributes = state.get("attributes", {})
    position = attributes.get("current_position")
    return {
        **_simple_item(state),
        "position": _numeric_value(position),
        "supported_features": attributes.get("supported_features"),
        "device_class": attributes.get("device_class") or "cover",
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
    attributes = state.get("attributes", {})
    device_class = str(attributes.get("device_class") or "").lower()
    entity_id = str(state.get("entity_id") or "").lower()
    name = str(_name(state) or "").lower()
    unit = str(attributes.get("unit_of_measurement") or "").strip()
    state_value = str(state.get("state") or "").strip().lower()

    if device_class == "battery":
        return True
    if "batterie" in entity_id or "battery" in entity_id or "batterie" in name or "battery" in name:
        if "voltage" in entity_id or "batteriespannung" in entity_id or device_class == "voltage" or unit.lower() in {"v", "mv"}:
            return False
        return unit == "%" or _is_numeric_state(state_value) or state_value in {"low", "normal", "high", "ok", "unknown", "unavailable"}
    return False


def _battery_level(state: dict[str, Any]) -> float | None:
    raw_state = state.get("state")
    value = _numeric_value(raw_state)
    if value is None:
        return None
    unit = str(state.get("attributes", {}).get("unit_of_measurement") or "").strip().lower()
    if unit in {"v", "mv"}:
        return None
    if 0 <= value <= 100:
        return value
    return None


def _numeric_value(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", ".")
    if not _is_numeric_state(text):
        return None
    return float(text)


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
    return item


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
{% for floor in floors() %}
  {% set floor_ns = namespace(areas=[]) %}
  {% for area in floor_areas(floor) %}
    {% set area_ns = namespace(entities=[]) %}
    {% for entity_id in area_entities(area) %}
      {% set area_ns.entities = area_ns.entities + [entity_id] %}
    {% endfor %}
    {% set display_name = area_name(area) or area %}
    {% set floor_ns.areas = floor_ns.areas + [{'area': display_name, 'area_id': area, 'entities': area_ns.entities}] %}
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
