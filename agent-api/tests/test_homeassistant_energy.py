import unittest

from backend.services.homeassistant_service import HomeAssistantService


def state(entity_id, value, name="", **attrs):
    return {"entity_id": entity_id, "state": value, "attributes": {"friendly_name": name, **attrs}, "last_updated": "2026-08-21T07:00:00+00:00"}


class FakeHomeAssistantService(HomeAssistantService):
    def __init__(self, states):
        self._states = states
        self.base_url = "http://ha.local:8123"
        self.token = "token"

    def get_states(self):
        return self._states


class HomeAssistantEnergyTests(unittest.TestCase):
    def test_energy_overview_discovers_renamed_german_energy_sensors(self):
        service = FakeHomeAssistantService([
            state("sensor.kaffeemaschine_power", "700", "Kaffeemaschine Power", device_class="power", unit_of_measurement="W"),
            state("sensor.stromzaehler_aktuelle_leistung", "312", "Stromzähler Aktuelle Leistung", device_class="power", unit_of_measurement="W"),
            state("sensor.stromzaehler_durchschnitt", "295", "Stromzähler Durchschnitt", device_class="power", unit_of_measurement="W"),
            state("sensor.stromzaehler_l1", "101", "Stromzähler L1", device_class="power", unit_of_measurement="W"),
            state("sensor.stromzaehler_l2", "102", "Stromzähler L2", device_class="power", unit_of_measurement="W"),
            state("sensor.stromzaehler_l3", "109", "Stromzähler L3", device_class="power", unit_of_measurement="W"),
            state("sensor.stromzaehler_netzbezug", "1234.5", "Stromzähler Netzbezug", device_class="energy", unit_of_measurement="kWh"),
            state("sensor.stromzaehler_einspeisung", "12.3", "Stromzähler Einspeisung", device_class="energy", unit_of_measurement="kWh"),
            state("sensor.stromzaehler_netzbezug_heute", "4.2", "Stromzähler Netzbezug heute", device_class="energy", unit_of_measurement="kWh"),
            state("sensor.stromzaehler_einspeisung_heute", "0.8", "Stromzähler Einspeisung heute", device_class="energy", unit_of_measurement="kWh"),
        ])

        overview = service.get_energy_overview()

        self.assertEqual(overview["status"], "ok")
        self.assertEqual(overview["power"], 312)
        self.assertEqual(overview["power_avg"], 295)
        self.assertEqual(overview["phases"], {"l1": 101, "l2": 102, "l3": 109})
        self.assertEqual(overview["energy"]["meter"]["import_kwh"], 1234.5)
        self.assertEqual(overview["energy"]["meter"]["export_kwh"], 12.3)
        self.assertEqual(overview["energy"]["today"], {"import_kwh": 4.2, "export_kwh": 0.8})

    def test_energy_overview_reads_renamed_raw_ecotracker_attribute_sensor(self):
        service = FakeHomeAssistantService([
            state(
                "sensor.stromzaehler",
                "ok",
                "Stromzähler",
                power="250",
                powerAvg="245",
                powerPhase1="80",
                powerPhase2="90",
                powerPhase3="80",
                energyCounterIn="120000",
                energyCounterOut="3000",
            )
        ])

        overview = service.get_energy_overview()

        self.assertEqual(overview["power"], 250)
        self.assertEqual(overview["power_avg"], 245)
        self.assertEqual(overview["phases"], {"l1": 80, "l2": 90, "l3": 80})
        self.assertEqual(overview["energy"]["meter"]["import_kwh"], 120)
        self.assertEqual(overview["energy"]["meter"]["export_kwh"], 3)


if __name__ == "__main__":
    unittest.main()
