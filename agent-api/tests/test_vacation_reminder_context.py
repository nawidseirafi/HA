import unittest

from backend.agents.vacation.service import VacationService


class VacationReminderContextTests(unittest.TestCase):
    def setUp(self):
        self.service = VacationService.__new__(VacationService)

    def test_internet_unknown_does_not_create_vacation_reminder_without_vacation_context(self):
        reminders = self.service._reminder_candidates(
            [
                {
                    "entity_id": "sensor.fritzbox_wan_status",
                    "state": "unknown",
                    "attributes": {"friendly_name": "FritzBox WAN Status"},
                }
            ],
            vacation_mode=False,
            period={},
            pre_departure=False,
        )

        self.assertEqual(reminders, [])

    def test_internet_unknown_creates_vacation_reminder_in_pre_departure_context(self):
        reminders = self.service._reminder_candidates(
            [
                {
                    "entity_id": "sensor.fritzbox_wan_status",
                    "state": "unknown",
                    "attributes": {"friendly_name": "FritzBox WAN Status"},
                }
            ],
            vacation_mode=False,
            period={"start_date": "2026-06-11", "end_date": "2026-06-14"},
            pre_departure=True,
        )

        self.assertTrue(any(item.get("reminder_type") == "internet" for item in reminders))

    def test_low_battery_does_not_create_vacation_reminder_without_vacation_context(self):
        reminders = self.service._reminder_candidates(
            [
                {
                    "entity_id": "sensor.door_sensor_battery",
                    "state": "10",
                    "attributes": {"friendly_name": "Türsensor Batterie", "device_class": "battery"},
                }
            ],
            vacation_mode=False,
            period={},
            pre_departure=False,
        )

        self.assertEqual(reminders, [])

    def test_future_vacation_period_is_not_preparation_context_by_itself(self):
        self.service.config = lambda: {"pre_departure_days": 3}

        self.assertFalse(
            self.service._has_vacation_context(
                vacation_mode=False,
                period={"start_date": "2026-09-10", "end_date": "2026-10-09"},
                pre_departure=False,
            )
        )

    def test_waste_reminders_are_skipped_without_vacation_context(self):
        reminders = self.service._waste_reminders_from_service(
            {"start_date": "2026-09-10", "end_date": "2026-10-09"},
            has_vacation_context=False,
            pre_departure=False,
        )

        self.assertEqual(reminders, [])

    def test_active_smoke_alarm_creates_critical_vacation_reminder(self):
        reminders = self.service._reminder_candidates(
            [
                {
                    "entity_id": "binary_sensor.flur_rauchmelder",
                    "state": "on",
                    "attributes": {"friendly_name": "Flur Rauchmelder", "device_class": "smoke"},
                }
            ],
            vacation_mode=True,
            period={"start_date": "2026-06-11", "end_date": "2026-06-14"},
            pre_departure=False,
        )

        reminder = next(item for item in reminders if item.get("reminder_type") == "safety_alarm")
        self.assertEqual(reminder["severity"], "critical")
        self.assertIn("Flur Rauchmelder", reminder["message"])


if __name__ == "__main__":
    unittest.main()
