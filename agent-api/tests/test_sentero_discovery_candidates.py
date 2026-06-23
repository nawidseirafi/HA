from datetime import datetime, timezone

from backend.agents.sentero.device_mapping_service import score_candidates


def state(entity_id, *, device_class, device_id="device-1", state_value="off", last_updated="2026-06-23T10:00:00+00:00"):
    return {
        "entity_id": entity_id,
        "domain": entity_id.split(".", 1)[0],
        "state": state_value,
        "friendly_name": entity_id.replace("_", " "),
        "device_class": device_class,
        "device_id": device_id,
        "last_changed": last_updated,
        "last_updated": last_updated,
    }


def test_discovery_ignores_existing_changed_sensor():
    started_at = datetime(2026, 6, 23, 9, 59, tzinfo=timezone.utc)
    baseline = [
        state("binary_sensor.bad_praesenz", device_class="motion", state_value="off", device_id="old-motion"),
    ]
    current = [
        state("binary_sensor.bad_praesenz", device_class="motion", state_value="on", device_id="old-motion"),
    ]

    assert score_candidates(baseline, current, "bathroom_presence", "bathroom", started_at) == []


def test_discovery_accepts_new_matching_presence_sensor():
    started_at = datetime(2026, 6, 23, 9, 59, tzinfo=timezone.utc)
    current = [
        state("binary_sensor.bad_praesenz", device_class="motion", state_value="on", device_id="new-motion"),
    ]

    candidates = score_candidates([], current, "bathroom_presence", "bathroom", started_at)

    assert [candidate["entity_id"] for candidate in candidates] == ["binary_sensor.bad_praesenz"]


def test_discovery_rejects_vibration_sensor_for_door_contact():
    started_at = datetime(2026, 6, 23, 9, 59, tzinfo=timezone.utc)
    current = [
        state("binary_sensor.flur_vibration", device_class="vibration", state_value="on", device_id="new-vibration"),
    ]

    assert score_candidates([], current, "hallway_door", "hallway", started_at) == []


def test_discovery_accepts_new_matching_door_contact():
    started_at = datetime(2026, 6, 23, 9, 59, tzinfo=timezone.utc)
    current = [
        state("binary_sensor.flur_tuer", device_class="door", state_value="on", device_id="new-door"),
    ]

    candidates = score_candidates([], current, "hallway_door", "hallway", started_at)

    assert [candidate["entity_id"] for candidate in candidates] == ["binary_sensor.flur_tuer"]
