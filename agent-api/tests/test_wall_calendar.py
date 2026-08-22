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

    def test_wall_household_summary_links_smoke_detector_test_button(self):
        states = [
            {
                "entity_id": "binary_sensor.flur_rauchmelder",
                "state": "off",
                "attributes": {"friendly_name": "Flur Rauchmelder", "device_class": "smoke"},
                "last_updated": "2026-08-21T07:00:00+00:00",
            },
            {
                "entity_id": "button.flur_test",
                "state": "unknown",
                "attributes": {"friendly_name": "Flur Rauchmelder Test"},
                "last_updated": "2026-08-21T07:00:00+00:00",
            },
        ]

        summary = _wall_household_summary(states, {"ok": True, "today_count": 0, "next_event": None, "upcoming": []})

        self.assertEqual(summary["safety"]["detectors"][0]["test_entity_id"], "button.flur_test")

    def test_wall_smoke_alerts_only_include_smoke_alarm_binary_sensors(self):
        from backend.api.homeassistant_routes import _is_smoke_detector_smoke_item, _safety_item

        states = [
            {
                "entity_id": "binary_sensor.living_room_smoke_detector_smoke",
                "state": "off",
                "attributes": {"friendly_name": "Living Room Smoke Detector Smoke", "device_class": "smoke"},
            },
            {
                "entity_id": "binary_sensor.living_room_smoke_detector_gas",
                "state": "off",
                "attributes": {"friendly_name": "Living Room Smoke Detector Gas", "device_class": "gas"},
            },
            {
                "entity_id": "binary_sensor.living_room_smoke_detector_problem",
                "state": "off",
                "attributes": {"friendly_name": "Living Room Smoke Detector Problem", "device_class": "problem"},
            },
        ]
        items = [_safety_item(state, states) for state in states]

        smoke_items = [item for item in items if _is_smoke_detector_smoke_item(item)]

        self.assertEqual([item["entity_id"] for item in smoke_items], ["binary_sensor.living_room_smoke_detector_smoke"])


if __name__ == "__main__":
    unittest.main()
