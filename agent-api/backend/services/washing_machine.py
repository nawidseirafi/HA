from typing import Any


STATUS_ENTITY = "sensor.laundry_room_washing_machine_status"


def washing_machine_status(states: list[dict[str, Any]]) -> dict[str, Any]:
    sensor = next((item for item in states if item.get("entity_id") == STATUS_ENTITY), {})
    value = str(sensor.get("state") or "").strip().casefold()
    status, summary = {
        "läuft": ("running", "Die Waschmaschine läuft gerade."),
        "beendet": ("finished", "Die Waschmaschine ist fertig. Die Wäsche kann entnommen werden."),
        "standby": ("standby", "Die Waschmaschine läuft nicht und ist im Standby."),
    }.get(value, ("unknown", "Der Waschmaschinenstatus ist derzeit nicht verfügbar."))
    return {
        "state": status,
        "summary": summary,
        "entity_id": STATUS_ENTITY,
        "updated_at": sensor.get("last_updated") or sensor.get("last_changed"),
    }
