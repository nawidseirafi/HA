import unittest

from backend.services.household_service import HouseholdService


class FakeHomeAssistant:
    def __init__(self, states, presence="home"):
        self.states = states
        self.presence = presence
        self.calls = []

    def get_states(self):
        return self.states

    def fetch_entity_state(self, entity_id):
        return ha_state(entity_id, self.presence, "Presence")

    def configured(self):
        return True

    def call_service(self, domain, service, payload):
        call = {"domain": domain, "service": service, "payload": payload}
        self.calls.append(call)
        return {"ok": True, **call}


class EmptyService:
    def status(self):
        return {"ok": True, "reminders": [], "items": []}

    def summary(self):
        return {"ok": True, "status": "ok"}

    def today_summary(self):
        return {"ok": True, "today_count": 0, "next_event": None, "upcoming": []}


class FakeMessaging:
    def __init__(self):
        self.messages = []

    def create_message(self, source, category, severity, title, message, payload=None):
        item = {
            "id": len(self.messages) + 1,
            "source": source,
            "category": category,
            "severity": severity,
            "title": title,
            "message": message,
            "payload": payload or {},
            "read": False,
            "created_at": "2026-08-21T07:00:00+00:00",
        }
        self.messages.append(item)
        return item

    def get_messages_by_source(self, source, limit=100):
        return [message for message in reversed(self.messages) if message["source"] == source][:limit]


def ha_state(entity_id, value, name="", **attrs):
    return {
        "entity_id": entity_id,
        "state": value,
        "attributes": {"friendly_name": name, **attrs},
        "last_updated": "2026-08-21T07:00:00+00:00",
    }


class HouseholdSafetyTests(unittest.TestCase):
    def service(self, states, presence="home", messaging=None):
        empty = EmptyService()
        return HouseholdService(
            ha_service=FakeHomeAssistant(states, presence=presence),
            waste_service=empty,
            infrastructure_service=empty,
            calendar_service=empty,
            messaging_service=messaging,
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

    def test_check_alerts_delivers_critical_smoke_to_all_channels(self):
        messaging = FakeMessaging()
        service = self.service([
            ha_state("binary_sensor.flur_rauchmelder", "on", "Flur Rauchmelder", device_class="smoke"),
        ], messaging=messaging)

        service._send_alert_telegram = lambda alert: {"ok": True, "sent": [{"chat_id": "1"}]}

        result = service.check_alerts()

        self.assertFalse(result["ok"])
        self.assertTrue(result["notified"])
        self.assertEqual(messaging.messages[0]["title"], "Rauchalarm erkannt")
        self.assertEqual(messaging.messages[0]["severity"], "critical")
        self.assertIn("mobile_push", result["delivered"][0]["channels"])
        self.assertIn("telegram", result["delivered"][0]["channels"])

    def test_check_alerts_detects_water_leak(self):
        messaging = FakeMessaging()
        service = self.service([
            ha_state("binary_sensor.kueche_wasser", "on", "Kueche Wasser", device_class="moisture"),
        ], messaging=messaging)
        service._send_alert_telegram = lambda alert: {"ok": True}

        result = service.check_alerts()

        self.assertEqual(result["active_alerts"][0]["title"], "Wasserleck erkannt")
        self.assertEqual(messaging.messages[0]["payload"]["alert"]["kind"], "water_leak")

    def test_check_alerts_detects_air_quality_warning(self):
        service = self.service([
            ha_state("sensor.wohnzimmer_co2", "1650", "Wohnzimmer CO2", device_class="carbon_dioxide", unit_of_measurement="ppm"),
        ])

        result = service.alerts_status()

        self.assertTrue(result["ok"])
        self.assertEqual(result["active_alerts"][0]["severity"], "warning")
        self.assertEqual(result["active_alerts"][0]["title"], "Luftqualität auffällig")

    def test_warning_alert_uses_telegram_and_push_only_when_away(self):
        messaging = FakeMessaging()
        service = self.service([
            ha_state("sensor.wohnzimmer_co2", "1650", "Wohnzimmer CO2", device_class="carbon_dioxide", unit_of_measurement="ppm"),
        ], presence="not_home", messaging=messaging)
        service._send_alert_telegram = lambda alert: {"ok": True}

        result = service.check_alerts()

        self.assertIn("mobile_push", result["delivered"][0]["channels"])
        self.assertIn("telegram", result["delivered"][0]["channels"])

    def test_check_alerts_deduplicates_existing_unread_alert(self):
        messaging = FakeMessaging()
        service = self.service([
            ha_state("binary_sensor.flur_rauchmelder", "on", "Flur Rauchmelder", device_class="smoke"),
        ], messaging=messaging)
        service._send_alert_telegram = lambda alert: {"ok": True}

        first = service.check_alerts()
        second = service.check_alerts()

        self.assertTrue(first["notified"])
        self.assertFalse(second["notified"])
        self.assertEqual(len(messaging.messages), 1)
        self.assertEqual(second["suppressed"][0]["reason"], "deduplicated")


if __name__ == "__main__":
    unittest.main()
