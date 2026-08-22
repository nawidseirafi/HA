import unittest

from backend.api.homeassistant_routes import _wall_household_summary


class WallCalendarTests(unittest.TestCase):
    def test_wall_household_summary_keeps_calendar_events(self):
        calendar = {
            "ok": True,
            "today_count": 1,
            "next_event": {"title": "Zahnarzt", "start": "2026-08-06T15:00:00+02:00"},
            "upcoming": [{"title": "Zahnarzt", "start": "2026-08-06T15:00:00+02:00"}],
            "source": "homeassistant:calendar.devcal",
        }

        summary = _wall_household_summary([], calendar)

        self.assertEqual(summary["calendar"], calendar)
        self.assertEqual(summary["counts"]["calendar_events_today"], 1)
        self.assertEqual(summary["state"]["next_calendar_event"]["title"], "Zahnarzt")

    def test_wall_household_summary_marks_smoke_alarm_critical(self):
        states = [{
            "entity_id": "binary_sensor.flur_rauchmelder",
            "state": "on",
            "attributes": {"friendly_name": "Flur Rauchmelder", "device_class": "smoke"},
            "last_updated": "2026-08-21T07:00:00+00:00",
        }]

        summary = _wall_household_summary(states, {"ok": True, "today_count": 0, "next_event": None, "upcoming": []})

        self.assertFalse(summary["ok"])
        self.assertEqual(summary["safety"]["active_alerts"][0]["name"], "Flur Rauchmelder")
        self.assertTrue(any(item["priority"] == "critical" for item in summary["reminders"]))


if __name__ == "__main__":
    unittest.main()
