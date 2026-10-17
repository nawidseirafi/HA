from backend.services.homeassistant_service import HomeAssistantService


class HomeAssistantBackend:
    def __init__(self, ha=None):
        self.ha = ha or HomeAssistantService()

    def state(self, entity):
        state = self.ha.get_state(entity)
        if not state or state.get("state") in {"unknown", "unavailable"}:
            raise ValueError(f"Gerät nicht verfügbar: {entity}")
        return state

    def apply(self, entity, payload):
        self.ha.call_service("light", "turn_on", {"entity_id": entity, **payload})

    def restore(self, entity, state):
        if state["state"] == "off":
            self.ha.call_service("light", "turn_off", {"entity_id": entity})
            return
        attrs = state.get("attributes", {})
        payload = {key: attrs[key] for key in ("brightness",) if attrs.get(key) is not None}
        mode = attrs.get("color_mode")
        key = {"hs": "hs_color", "xy": "xy_color", "rgb": "rgb_color", "rgbw": "rgbw_color", "rgbww": "rgbww_color", "color_temp": "color_temp_kelvin"}.get(mode)
        if key and attrs.get(key) is not None:
            payload[key] = attrs[key]
        if attrs.get("effect") and attrs["effect"] != "none":
            payload["effect"] = attrs["effect"]
        self.apply(entity, payload)
