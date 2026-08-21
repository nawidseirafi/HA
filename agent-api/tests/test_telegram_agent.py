import tempfile
import unittest
from pathlib import Path
from typing import Any
from dataclasses import replace

from backend.agents.telegram.service import TelegramConfig, TelegramService, TelegramStore


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


if __name__ == "__main__":
    unittest.main()
