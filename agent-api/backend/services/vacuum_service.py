import math
import re
from datetime import datetime, timezone


FEATURES = {"start": 8192, "pause": 4, "stop": 8, "return_to_base": 16, "locate": 512, "set_fan_speed": 32}
ROLES = {
    "battery": ("batterie", "battery"), "progress": ("reinigungsfortschritt", "cleaning_progress"),
    "area": ("reinigungsbereich", "cleaning_area"), "duration": ("reinigungszeit", "cleaning_time"),
    "status": ("status",), "room": ("aktueller_raum", "current_room"),
    "error": ("staubsauger_fehler", "vacuum_error"), "last_end": ("letztes_reinigungsende", "last_clean_end"),
    "charging": ("ladestatus", "charging"), "water_low": ("wasserknappheit", "water_shortage"),
    "mop": ("mopp_angebracht", "mop_attached"),
}


def number(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (ValueError, TypeError):
        return None


def vacuum_notice(device: dict, now: datetime | None = None) -> dict | None:
    now = now or datetime.now(timezone.utc)
    state, name = device["state"], device["name"]
    metrics = device.get("metrics", {})
    fault = metrics.get("error", {}).get("state")
    if fault in {"none", "unknown", "unavailable", "0", "off"}:
        fault = None
    kind, tone, title, detail = "", "info", "", ""
    if state in {"unknown", "unavailable"}:
        kind, tone, title, detail = "unavailable", "warn", f"{name} ist nicht erreichbar", "Der aktuelle Reinigungszustand ist unbekannt."
    elif state == "error" or fault:
        kind, tone, title = "error", "warn", f"{name} braucht Hilfe"
        detail = {"lidar_blocked": "Lasersensor blockiert", "robot_trapped": "Roboter steckt fest", "main_brush_jammed": "Hauptbuerste blockiert", "no_dustbin": "Staubbehaelter fehlt"}.get(fault, str(fault or "Fehler am Roboter").replace("_", " "))
    elif metrics.get("water_low", {}).get("state") == "on":
        kind, tone, title, detail = "water_low", "warn", f"{name}: Wasser nachfuellen", "Der Roboter meldet Wasserknappheit."
    elif state == "cleaning":
        kind, title = "cleaning", f"{name} reinigt gerade"
        progress = number(metrics.get("progress", {}).get("state"))
        detail = f"Fortschritt: {round(min(100, max(0, progress)))} %" if progress is not None else "Reinigung aktiv."
    elif state == "returning":
        kind, title, detail = "returning", f"{name} kehrt zur Station zurueck", "Die Ankunft ist noch nicht bestaetigt."
    elif state == "paused":
        kind, tone, title, detail = "paused", "warn", f"{name} ist pausiert", "Die Reinigung ist unterbrochen."
    elif state in {"docked", "idle"}:
        try:
            ended = datetime.fromisoformat(str(metrics.get("last_end", {}).get("state", "")).replace("Z", "+00:00"))
            if ended.tzinfo is not None and 0 <= (now - ended).total_seconds() < 1800:
                kind, title, detail = "finished", f"{name}: Reinigung beendet", "Letztes Reinigungsende innerhalb der vergangenen 30 Minuten."
        except (ValueError, TypeError):
            pass
    if not kind:
        return None
    return {"kind": kind, "tone": tone, "title": title, "detail": detail, "summary": f"{title}."}


def vacuum_items(states: list[dict], metadata: dict, now: datetime | None = None) -> list[dict]:
    result = []
    for vacuum in states:
        entity_id = vacuum.get("entity_id", "")
        if not entity_id.startswith("vacuum."):
            continue
        attrs = vacuum.get("attributes", {})
        device = metadata.get(entity_id, {})
        device_id = device.get("device_id")
        related = [s for s in states if device_id and metadata.get(s["entity_id"], {}).get("device_id") == device_id and s["entity_id"] != entity_id]
        name = attrs.get("friendly_name") or device.get("name") or entity_id

        def item(state):
            attributes = state.get("attributes", {})
            label = str(attributes.get("friendly_name") or state["entity_id"])
            for prefix in (name, device.get("name")):
                if prefix and label.startswith(prefix):
                    label = label[len(prefix):].strip()
            return {"entity_id": state["entity_id"], "name": label, "state": state.get("state", "unknown"),
                    "unit": attributes.get("unit_of_measurement"), "options": attributes.get("options", []),
                    "last_updated": state.get("last_updated")}

        metrics = {}
        for role, suffixes in ROLES.items():
            candidates = [s for s in related if s["entity_id"].split(".")[0] in {"sensor", "binary_sensor"}
                          and not (role in {"area", "duration"} and any(word in s["entity_id"] for word in ("gesamt", "total")))
                          and any(s["entity_id"].endswith("_" + suffix) for suffix in suffixes)]
            if len(candidates) == 1:
                metrics[role] = item(candidates[0])
        battery = number(metrics.get("battery", {}).get("state", attrs.get("battery_level")))
        features = int(number(attrs.get("supported_features")) or 0)
        result.append({"entity_id": entity_id, "name": name, "state": vacuum.get("state", "unknown"),
                       "manufacturer": device.get("manufacturer"), "model": device.get("model"),
                       "last_updated": vacuum.get("last_updated"), "metadata_available": bool(device_id),
                       "battery_level": min(100, max(0, battery)) if battery is not None else None,
                       "actions": [action for action, flag in FEATURES.items() if features & flag],
                       "fan_speed": attrs.get("fan_speed"), "fan_speed_list": attrs.get("fan_speed_list", []),
                       "metrics": metrics,
                       "maps": [item(s) for s in related if s["entity_id"].startswith("image.")],
                       "selects": [item(s) for s in related if s["entity_id"].startswith("select.")],
                       "routines": [item(s) for s in related if s["entity_id"].startswith("button.")],
                       "switches": [item(s) for s in related if s["entity_id"].startswith("switch.")],
                       "maintenance": [item(s) for s in related if s["entity_id"].startswith("sensor.") and
                                       any(key in s["entity_id"] for key in ("verbleibend", "remaining"))]})
    for device in result:
        device["notice"] = vacuum_notice(device, now)
    return result


class VacuumService:
    def __init__(self, ha):
        self.ha = ha

    def device(self, entity_id):
        if not re.fullmatch(r"vacuum\.[a-z0-9_]+", entity_id):
            raise ValueError("Ungueltiger Saugroboter.")
        states = self.ha.fetch_states()
        metadata = self.ha.get_device_metadata_by_entity()
        device = next((v for v in vacuum_items(states, metadata) if v["entity_id"] == entity_id), None)
        if device is None:
            raise ValueError("Saugroboter nicht gefunden.")
        return device

    def command(self, entity_id, action, target=None, option=None):
        device = self.device(entity_id)
        if device["state"] in {"unknown", "unavailable"}:
            raise ValueError("Saugroboter ist nicht erreichbar.")
        if action in FEATURES:
            if action not in device["actions"]:
                raise ValueError("Aktion wird nicht unterstuetzt.")
            data = {"entity_id": entity_id}
            if action == "set_fan_speed":
                if option not in device["fan_speed_list"]:
                    raise ValueError("Unbekannte Saugstaerke.")
                data["fan_speed"] = option
            response = self.ha.call_service("vacuum", action, data)
        else:
            group = {"select_option": "selects", "press": "routines", "turn_on": "switches", "turn_off": "switches"}.get(action)
            control = next((c for c in device.get(group, []) if c["entity_id"] == target), None) if group else None
            if not control or control["state"] == "unavailable":
                raise ValueError("Bedienelement gehoert nicht zu diesem Roboter oder ist nicht verfuegbar.")
            if action in {"select_option", "press"} and device["state"] not in {"docked", "idle", "paused"}:
                raise ValueError("Bitte den Roboter zuerst pausieren.")
            data = {"entity_id": target}
            if action == "select_option":
                if option not in control["options"]:
                    raise ValueError("Unbekannte Einstellung.")
                data["option"] = option
            response = self.ha.call_service(target.split(".")[0], action, data)
        if not response.get("ok"):
            raise ValueError("Home Assistant hat den Auftrag nicht angenommen.")
        return {"ok": True, "status": "accepted"}

    def map_image(self, entity_id, image_id):
        if image_id not in {m["entity_id"] for m in self.device(entity_id)["maps"]}:
            raise ValueError("Karte gehoert nicht zu diesem Roboter.")
        return self.ha.get_image(image_id)
