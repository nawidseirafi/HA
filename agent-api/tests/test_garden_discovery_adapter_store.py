import tempfile
import unittest
from pathlib import Path

from backend.agents.garden.adapter import GardenIrrigationAdapter
from backend.agents.garden.discovery import GardenEntityDiscovery
from backend.agents.garden.store import GardenStore


def state(entity_id, value, name="", **attrs):
    return {"entity_id": entity_id, "state": value, "attributes": {"friendly_name": name, **attrs}, "last_updated": "2026-07-14T10:00:00+00:00"}


class FakeHA:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def call_service(self, domain, service, payload):
        if self.fail:
            raise RuntimeError("HA Fehler")
        self.calls.append((domain, service, payload))
        return {"ok": True}


class GardenDiscoveryAdapterStoreTests(unittest.TestCase):
    def test_discovery_ignores_diagnostics_and_binds_core_entities(self):
        states = [
            state("sensor.rasen_soil_moisture", "22", "Rasen Soil Moisture", device_class="moisture", unit_of_measurement="%"),
            state("sensor.rasen_soil_calibration", "5", "Rasen Soil calibration", unit_of_measurement="%"),
            state("sensor.rasen_humidity_calibration", "5", "Rasen Humidity calibration", unit_of_measurement="%"),
            state("binary_sensor.rasen_soil_warning", "off", "Rasen Soil warning"),
            state("sensor.rasen_temperature_sampling", "60", "Rasen Temperature sampling"),
            state("sensor.rasen_battery", "91", "Rasen Battery", device_class="battery", unit_of_measurement="%"),
            state("switch.eve_aqua_123a", "off", "Eve Aqua"),
            state("lawn_mower.garden_mower", "docked", "Garden Mower"),
        ]
        bindings = GardenEntityDiscovery().bind_zone_entities(states, {"entities": {}}, auto_discovery=True)
        self.assertEqual(bindings["moisture"].entity_id, "sensor.rasen_soil_moisture")
        self.assertEqual(bindings["soil_warning"].entity_id, "binary_sensor.rasen_soil_warning")
        self.assertEqual(bindings["battery"].entity_id, "sensor.rasen_battery")
        self.assertEqual(bindings["irrigation"].entity_id, "switch.eve_aqua_123a")
        self.assertEqual(bindings["mower"].entity_id, "lawn_mower.garden_mower")

    def test_discovery_falls_back_when_configured_entity_was_renamed(self):
        states = [
            state("sensor.alter_bodenfeuchtesensor", "unavailable", "Alter Bodenfeuchtesensor", device_class="moisture", unit_of_measurement="%"),
            state("sensor.rasen_bodenfeuchtigkeit", "22", "Rasen Bodenfeuchtigkeit", unit_of_measurement="%"),
            state("switch.rasensprenganlage_power", "off", "Rasensprenganlage Power"),
        ]
        bindings = GardenEntityDiscovery().bind_zone_entities(
            states,
            {"entities": {"moisture": "sensor.alter_bodenfeuchtesensor", "irrigation": "switch.eve_aqua_123a"}},
            auto_discovery=True,
        )
        self.assertEqual(bindings["moisture"].entity_id, "sensor.rasen_bodenfeuchtigkeit")
        self.assertEqual(bindings["moisture"].source, "auto")
        self.assertEqual(bindings["irrigation"].entity_id, "switch.rasensprenganlage_power")
        self.assertEqual(bindings["irrigation"].source, "auto")

    def test_irrigation_adapter_switch(self):
        self._assert_adapter("switch.eve_aqua", "turn_on", "turn_off")

    def test_irrigation_adapter_valve(self):
        self._assert_adapter("valve.eve_aqua", "open_valve", "close_valve")

    def test_irrigation_adapter_input_boolean(self):
        self._assert_adapter("input_boolean.eve_aqua", "turn_on", "turn_off")

    def test_irrigation_adapter_rejects_unsupported_domain(self):
        with self.assertRaises(ValueError):
            GardenIrrigationAdapter(FakeHA()).start("light.eve_aqua")

    def test_irrigation_adapter_surfaces_ha_error(self):
        with self.assertRaises(RuntimeError):
            GardenIrrigationAdapter(FakeHA(fail=True)).start("switch.eve_aqua")

    def test_store_persists_decision_and_irrigation_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = GardenStore(Path(tmp) / "garden.db")
            decision = store.save_decision({
                "zone_id": "lawn",
                "evaluated_at": "2026-07-14T10:00:00+00:00",
                "status": "dry",
                "decision": "irrigate",
                "recommended_duration_minutes": 20,
                "apply_allowed": False,
                "reasons": [{"code": "dry", "message": "trocken"}],
                "blocks": [],
                "input_snapshot": {"moisture": 22},
            })
            self.assertGreater(decision["id"], 0)
            self.assertEqual(store.list_decisions("lawn")[0]["status"], "dry")
            action = store.create_action("lawn", "irrigation_start", "test", "2026-07-14T10:00:00+00:00")
            run = store.start_irrigation_run("lawn", "2026-07-14T10:00:00+00:00", "2026-07-14T10:20:00+00:00", 20, "test", 22, action["id"])
            self.assertEqual(store.open_irrigation_run("lawn")["id"], run["id"])
            stop = store.create_action("lawn", "irrigation_stop", "test", "2026-07-14T10:20:00+00:00")
            closed = store.close_irrigation_run(run["id"], "2026-07-14T10:20:00+00:00", 28, "planned", stop["id"])
            self.assertEqual(closed["status"], "completed")
            self.assertIsNone(store.open_irrigation_run("lawn"))

    def _assert_adapter(self, entity_id, start_service, stop_service):
        ha = FakeHA()
        adapter = GardenIrrigationAdapter(ha)
        adapter.start(entity_id)
        adapter.stop(entity_id)
        self.assertEqual(ha.calls[0][1], start_service)
        self.assertEqual(ha.calls[1][1], stop_service)


if __name__ == "__main__":
    unittest.main()
