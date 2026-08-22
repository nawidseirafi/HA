import unittest

from backend.services.household_service import HouseholdService


class FakeHomeAssistant:
    def __init__(self, states):
        self.states = states

    def get_states(self):
        return self.states

    def configured(self):
        return True


class EmptyService:
    def status(self):
        return {"ok": True, "reminders": [], "items": []}

    def summary(self):
        return {"ok": True, "status": "ok"}

    def today_summary(self):
        return {"ok": True, "today_count": 0, "next_event": None, "upcoming": []}


def ha_state(entity_id, value, name="", **attrs):
    return {
        "entity_id": entity_id,
        "state": value,
        "attributes": {"friendly_name": name, **attrs},
        "last_updated": "2026-08-21T07:00:00+00:00",
    }


class HouseholdSafetyTests(unittest.TestCase):
    def service(self, states):
        empty = EmptyService()
        return HouseholdService(
            ha_service=FakeHomeAssistant(states),
            waste_service=empty,
            infrastructure_service=empty,
            calendar_service=empty,
            vacation_status_provider=lambda: {"vacation_mode": False, "reminders": []},
        )

    def test_safety_status_detects_active_smoke_alarm(self):
        service = self.service([
            ha_state("binary_sensor.flur_rauchmelder", "on", "Flur Rauchmelder", device_class="smoke"),
        ])

        status = service.status()

        self.assertFalse(status["ok"])
        self.assertEqual(status["safety"]["total"], 1)
        self.assertEqual(status["safety"]["active_alerts"][0]["name"], "Flur Rauchmelder")
        self.assertTrue(any(item["priority"] == "critical" and "Rauchalarm" in item["message"] for item in status["reminders"]))

    def test_inactive_smoke_detector_is_not_critical(self):
        service = self.service([
            ha_state("binary_sensor.flur_rauchmelder", "off", "Flur Rauchmelder", device_class="smoke"),
        ])

        status = service.status()

        self.assertTrue(status["ok"])
        self.assertEqual(status["safety"]["total"], 1)
        self.assertEqual(status["safety"]["active_alerts"], [])


if __name__ == "__main__":
    unittest.main()
