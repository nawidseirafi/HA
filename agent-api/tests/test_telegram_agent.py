import tempfile
import unittest
from pathlib import Path
from typing import Any
from dataclasses import replace

from backend.agents.telegram.service import TelegramConfig, TelegramService, TelegramStore, _home_assistant_snapshot


class RecordingTelegramClient:
    def __init__(self) -> None:
        self.config = TelegramConfig()
        self.sent: list[dict[str, Any]] = []
        self.updates: list[dict[str, Any]] = []

    def get_updates(self, offset):
        self.last_offset = offset
        return self.updates

    def send_message(self, chat_id, text):
        self.sent.append({"chat_id": chat_id, "text": text})
        return {"message_id": len(self.sent)}

    def get_me(self):
        return {"id": 1, "username": "roboter_steve_bot"}


class FakeMessaging:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    def create_message(self, source, category, severity, title, message, payload=None):
        self.messages.append({"source": source, "category": category, "severity": severity, "title": title, "message": message, "payload": payload})
        return self.messages[-1]


class TestTelegramService(TelegramService):
    def __init__(self, config, **kwargs):
        super().__init__(**kwargs)
        self.fixed_config = config

    def config(self):
        return self.fixed_config

    def update_settings(self, settings):
        self.fixed_config = replace(
            self.fixed_config,
            allowed_chat_ids=tuple(settings.get("allowed_chat_ids", self.fixed_config.allowed_chat_ids)),
        )
        return self.status()

    def answer(self, question):
        return f"Antwort auf: {question}"


class TelegramAgentTests(unittest.TestCase):
    def test_authorized_chat_receives_answer_and_query_is_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = RecordingTelegramClient()
            service = self._service(tmp, client)

            result = service.process_update(update("Wie geht es dem Haus?"))

            self.assertEqual(result["status"], "sent")
            self.assertEqual(client.sent[-1]["chat_id"], "6516768203")
            self.assertIn("Antwort auf: Wie geht es dem Haus?", client.sent[-1]["text"])
            rows = service.store().recent_messages()
            self.assertEqual(rows[0]["status"], "sent")
            self.assertEqual(rows[0]["chat_id"], "6516768203")

    def test_unknown_chat_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = RecordingTelegramClient()
            service = self._service(tmp, client)

            result = service.process_update(update("Hallo", chat_id="999"))

            self.assertEqual(result["status"], "rejected")
            self.assertEqual(result["error"], "unknown_chat")
            self.assertIn("nicht für Roboter Steve freigeschaltet", client.sent[-1]["text"])

    def test_poll_once_marks_update_offset(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = RecordingTelegramClient()
            client.updates = [update("Status?", update_id=2001)]
            service = self._service(tmp, client)

            result = service.poll_once()

            self.assertEqual(result["processed"], 1)
            self.assertEqual(service.store().next_offset(), 2002)

    def test_disabled_service_does_not_poll(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = RecordingTelegramClient()
            config = TelegramConfig(enabled=False, bot_token="secret", allowed_chat_ids=("6516768203",), database_path=str(Path(tmp) / "telegram.db"))
            service = TestTelegramService(config, store=TelegramStore(config.database_path), client=client, messaging=FakeMessaging())

            result = service.poll_once()

            self.assertEqual(result["skipped"], "disabled")
            self.assertEqual(client.sent, [])

    def test_first_chat_is_auto_paired_when_no_chat_id_is_configured(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = RecordingTelegramClient()
            config = TelegramConfig(enabled=True, bot_token="secret", allowed_chat_ids=(), database_path=str(Path(tmp) / "telegram.db"))
            service = TestTelegramService(config, store=TelegramStore(config.database_path), client=client, messaging=FakeMessaging())

            result = service.process_update(update("Hallo"))

            self.assertEqual(result["status"], "sent")
            self.assertEqual(service.config().allowed_chat_ids, ("6516768203",))
            self.assertIn("jetzt mit Roboter Steve verbunden", client.sent[0]["text"])
            self.assertIn("Antwort auf: Hallo", client.sent[1]["text"])

    def test_bot_id_from_token_is_not_treated_as_allowed_chat(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = RecordingTelegramClient()
            config = TelegramConfig(
                enabled=True,
                bot_token="8984402842:secret",
                allowed_chat_ids=("8984402842",),
                database_path=str(Path(tmp) / "telegram.db"),
            )
            service = TestTelegramService(config, store=TelegramStore(config.database_path), client=client, messaging=FakeMessaging())

            result = service.process_update(update("Hallo", chat_id="6516768203"))

            self.assertEqual(result["status"], "sent")
            self.assertEqual(service.config().allowed_chat_ids, ("6516768203",))
            self.assertIn("jetzt mit Roboter Steve verbunden", client.sent[0]["text"])

    def test_homeassistant_snapshot_includes_temperature_and_alert_sensors(self):
        snapshot = _home_assistant_snapshot([
            ha_state("sensor.wohnzimmer_temperatur", "22.4", "Wohnzimmer Temperatur", device_class="temperature", unit_of_measurement="°C"),
            ha_state("sensor.bad_luftfeuchtigkeit", "48", "Bad Luftfeuchtigkeit", device_class="humidity", unit_of_measurement="%"),
            ha_state("binary_sensor.flur_rauchmelder", "off", "Flur Rauchmelder", device_class="smoke"),
            ha_state("binary_sensor.kueche_problem", "on", "Kueche Problem", device_class="problem"),
            ha_state("sensor.tuerkontakt_battery", "21", "Tuerkontakt Batterie", device_class="battery", unit_of_measurement="%"),
        ])

        self.assertEqual(snapshot["entity_count"], 5)
        self.assertEqual(snapshot["temperatures"][0]["value"], 22.4)
        self.assertEqual(snapshot["humidity"][0]["value"], 48)
        self.assertEqual(snapshot["smoke_alerts"][0]["name"], "Flur Rauchmelder")
        self.assertEqual(snapshot["active_problems"][0]["name"], "Kueche Problem")
        self.assertEqual(snapshot["low_batteries"][0]["level"], 21)

    def test_fallback_answer_uses_homeassistant_temperatures_for_temperature_questions(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = self._service(tmp, RecordingTelegramClient())
            context = {
                "home_assistant": {
                    "temperatures": [
                        {"entity_id": "sensor.wohnzimmer_temperatur", "name": "Wohnzimmer Temperatur", "value": 22.4, "unit": "°C"}
                    ]
                }
            }

            answer = service._fallback_answer("Wie ist die Temperatur?", context)

            self.assertIn("Wohnzimmer Temperatur: 22.4 °C", answer)

    def test_fallback_answer_uses_house_status_sensors(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = self._service(tmp, RecordingTelegramClient())
            context = {
                "home_assistant": {
                    "smoke_alerts": [{"entity_id": "binary_sensor.flur_rauchmelder", "name": "Flur Rauchmelder", "state": "off", "active": False}],
                    "openings": [{"entity_id": "binary_sensor.kueche_fenster", "name": "Kueche Fenster", "state": "on", "active": True}],
                    "active_problems": [],
                    "low_batteries": [],
                    "temperatures": [{"entity_id": "sensor.wohnzimmer_temperatur", "name": "Wohnzimmer Temperatur", "value": 22.4, "unit": "°C"}],
                    "humidity": [{"entity_id": "sensor.bad_luftfeuchtigkeit", "name": "Bad Luftfeuchtigkeit", "value": 48, "unit": "%"}],
                }
            }

            answer = service._fallback_answer("Wie ist der Status des Hauses, Temperatur und Feuchtigkeit?", context)

            self.assertIn("Rauch/Gas/CO: kein aktiver Alarm", answer)
            self.assertIn("Offen: Kueche Fenster", answer)
            self.assertIn("Wohnzimmer Temperatur: 22.4 °C", answer)
            self.assertIn("Bad Luftfeuchtigkeit: 48 %", answer)

    def test_fallback_answer_warns_about_active_smoke_alarm(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = self._service(tmp, RecordingTelegramClient())
            context = {
                "home_assistant": {
                    "smoke_alerts": [{"entity_id": "binary_sensor.flur_rauchmelder", "name": "Flur Rauchmelder", "state": "on", "active": True}],
                }
            }

            answer = service._fallback_answer("Rauchmelder status?", context)

            self.assertIn("Sicherheitsalarm: Flur Rauchmelder", answer)

    def _service(self, tmp, client):
        config = TelegramConfig(enabled=True, bot_token="secret", allowed_chat_ids=("6516768203",), database_path=str(Path(tmp) / "telegram.db"))
        return TestTelegramService(config, store=TelegramStore(config.database_path), client=client, messaging=FakeMessaging())


def update(text, chat_id="6516768203", update_id=1001):
    return {
        "update_id": update_id,
        "message": {
            "message_id": 42,
            "chat": {"id": chat_id},
            "from": {"is_bot": False},
            "text": text,
        },
    }


def ha_state(entity_id, value, name="", **attrs):
    return {
        "entity_id": entity_id,
        "state": value,
        "attributes": {"friendly_name": name, **attrs},
        "last_updated": "2026-08-21T07:00:00+00:00",
    }


if __name__ == "__main__":
    unittest.main()
