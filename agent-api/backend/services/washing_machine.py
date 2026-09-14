from typing import Any


STATUS_ENTITY = "sensor.laundry_room_washing_machine_status"
CYCLE_ENTITY = "input_select.laundry_room_washing_machine_cycle"


def acknowledge_washing_machine(ha) -> dict[str, Any]:
    state = (ha.get_state(CYCLE_ENTITY) or {}).get("state")
    if state == "Standby":
        return {"ok": True, "state": "standby"}
    if state != "Beendet":
        raise ValueError("Nur ein beendeter Waschgang kann als entnommen bestaetigt werden.")
    # Call the script synchronously; its own condition also protects a newly started cycle.
    result = ha.call_service("script", "laundry_room_washing_machine_reset", {})
    if not result.get("ok") or (ha.get_state(CYCLE_ENTITY) or {}).get("state") != "Standby":
        raise ValueError("Zuruecksetzen wurde nicht bestaetigt. Bitte den Waschmaschinenstatus pruefen.")
    return {"ok": True, "state": "standby"}


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
