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


if __name__ == "__main__":
    unittest.main()
