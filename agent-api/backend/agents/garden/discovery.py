from __future__ import annotations

from typing import Any, Callable

from .models import EntityBinding


DIAGNOSTIC_TOKENS = (
    "calibration",
    "calibrate",
    "sampling",
    "interval",
    "configuration",
    "config",
    "sensitivity",
    "diagnostic",
    "linkquality",
    "identify",
)

IRRIGATION_TOKENS = (
    "irrigation",
    "watering",
    "sprinkler",
    "sprenganlage",
    "rasensprenger",
    "bewässer",
    "bewasser",
    "garten",
    "ventil",
    "eve_aqua",
    "eve aqua",
)


class GardenEntityDiscovery:
    def bind_zone_entities(self, states: list[dict[str, Any]], zone: dict[str, Any], auto_discovery: bool = True) -> dict[str, EntityBinding]:
        configured = zone.get("entities") if isinstance(zone.get("entities"), dict) else {}
        return {
            "moisture": self._bind(states, configured.get("moisture"), self._is_moisture, auto_discovery),
            "temperature": self._bind(states, configured.get("temperature"), self._is_soil_temperature, auto_discovery),
            "battery": self._bind(states, configured.get("battery"), self._is_battery, auto_discovery),
            "soil_warning": self._bind(states, configured.get("soil_warning"), self._is_soil_warning, auto_discovery),
            "mower": self._bind(states, configured.get("mower"), lambda state: self._domain(state) == "lawn_mower", auto_discovery),
            "irrigation": self._bind(states, configured.get("irrigation"), self._is_irrigation, auto_discovery),
            "weather": self._bind(states, configured.get("weather"), lambda state: self._domain(state) == "weather", auto_discovery),
            "rain": self._bind(states, configured.get("rain"), self._is_rain, auto_discovery),
        }

    def _bind(self, states: list[dict[str, Any]], configured: Any, predicate: Callable[[dict[str, Any]], bool], auto: bool) -> EntityBinding:
        entity_id = str(configured or "").strip()
        if entity_id:
            state = next((item for item in states if item.get("entity_id") == entity_id), None)
            if (state is None or not self._state_available(state)) and auto:
                return self._auto_bind(states, predicate)
            return self._binding(state, "configured", entity_id)
        if not auto:
            return EntityBinding()
        return self._auto_bind(states, predicate)

    def _auto_bind(self, states: list[dict[str, Any]], predicate: Callable[[dict[str, Any]], bool]) -> EntityBinding:
        matches = [state for state in states if predicate(state)]
        available_matches = [state for state in matches if self._state_available(state)]
        if available_matches:
            matches = available_matches
        if len(matches) == 1:
            return self._binding(matches[0], "auto")
        if len(matches) > 1:
            scored = sorted(((self._score(state), state) for state in matches), key=lambda item: item[0], reverse=True)
            if scored and (len(scored) == 1 or scored[0][0] > scored[1][0]):
                return self._binding(scored[0][1], "auto")
            return EntityBinding(source="ambiguous", available=False)
        return EntityBinding()

    def _binding(self, state: dict[str, Any] | None, source: str, fallback_entity_id: str = "") -> EntityBinding:
        if not state:
            return EntityBinding(entity_id=fallback_entity_id, source=source, available=False, domain=self._domain({"entity_id": fallback_entity_id}))
        attrs = state.get("attributes") if isinstance(state.get("attributes"), dict) else {}
        entity_id = str(state.get("entity_id") or fallback_entity_id)
        state_value = state.get("state")
        return EntityBinding(
            entity_id=entity_id,
            source=source,
            available=self._state_available(state),
            state=state_value,
            name=str(attrs.get("friendly_name") or entity_id),
            last_updated=state.get("last_updated") or state.get("last_changed"),
            domain=self._domain(state),
        )

    def _is_moisture(self, state: dict[str, Any]) -> bool:
        if self._domain(state) != "sensor" or self._is_diagnostic(state):
            return False
        haystack = self._haystack(state)
        if "warning" in haystack or "calibration" in haystack or "humidity calibration" in haystack or "soil calibration" in haystack:
            return False
        attrs = state.get("attributes") if isinstance(state.get("attributes"), dict) else {}
        device_class = str(attrs.get("device_class") or "").lower()
        unit = str(attrs.get("unit_of_measurement") or "").strip()
        return (
            device_class in {"moisture", "humidity"}
            or any(token in haystack for token in ("soil moisture", "soil humidity", "bodenfeuchte", "bodenfeuchtigkeit", "moisture", "feuchte", "feuchtigkeit"))
        ) and unit in {"%", ""}

    def _is_soil_temperature(self, state: dict[str, Any]) -> bool:
        if self._domain(state) != "sensor" or self._is_diagnostic(state):
            return False
        haystack = self._haystack(state)
        attrs = state.get("attributes") if isinstance(state.get("attributes"), dict) else {}
        return (str(attrs.get("device_class") or "").lower() == "temperature" or str(attrs.get("unit_of_measurement") or "").lower() in {"°c", "c"}) and any(
            token in haystack for token in ("soil", "boden", "rasen", "lawn")
        )

    def _is_battery(self, state: dict[str, Any]) -> bool:
        if self._domain(state) != "sensor":
            return False
        attrs = state.get("attributes") if isinstance(state.get("attributes"), dict) else {}
        haystack = self._haystack(state)
        return str(attrs.get("device_class") or "").lower() == "battery" or "battery" in haystack or "batterie" in haystack

    def _is_soil_warning(self, state: dict[str, Any]) -> bool:
        if self._domain(state) not in {"binary_sensor", "sensor"}:
            return False
        haystack = self._haystack(state)
        return "soil" in haystack and "warning" in haystack

    def _is_irrigation(self, state: dict[str, Any]) -> bool:
        if self._domain(state) not in {"switch", "valve", "input_boolean"}:
            return False
        return any(token in self._haystack(state) for token in IRRIGATION_TOKENS)

    def _is_rain(self, state: dict[str, Any]) -> bool:
        if self._domain(state) not in {"binary_sensor", "sensor"}:
            return False
        haystack = self._haystack(state)
        return "rain" in haystack or "regen" in haystack

    def _is_diagnostic(self, state: dict[str, Any]) -> bool:
        haystack = self._haystack(state)
        return any(token in haystack for token in DIAGNOSTIC_TOKENS)

    def _haystack(self, state: dict[str, Any]) -> str:
        attrs = state.get("attributes") if isinstance(state.get("attributes"), dict) else {}
        return f"{state.get('entity_id') or ''} {attrs.get('friendly_name') or ''}".lower()

    def _domain(self, state: dict[str, Any]) -> str:
        return str(state.get("entity_id") or "").split(".", 1)[0]

    def _state_available(self, state: dict[str, Any] | None) -> bool:
        if not state:
            return False
        return state.get("state") not in {None, "", "unknown", "unavailable"}

    def _score(self, state: dict[str, Any]) -> int:
        haystack = self._haystack(state)
        score = 0
        for token in ("rasen", "lawn", "garden", "garten"):
            if token in haystack:
                score += 10
        for token in ("soil", "boden"):
            if token in haystack:
                score += 5
        return score
