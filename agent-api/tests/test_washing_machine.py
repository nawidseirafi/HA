import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.agents.telegram.service import TelegramService, _home_assistant_snapshot, _house_status_answer
from backend.services.context.service import ContextService
from backend.services.washing_machine import STATUS_ENTITY, washing_machine_status


class WashingMachineTests(unittest.TestCase):
    def states(self, value):
        return [{"entity_id": STATUS_ENTITY, "state": value, "attributes": {}}]

    def test_status_and_context_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = ContextService(database_path=Path(tmp) / "context.db")
            for value, expected in [("Läuft", "running"), ("Beendet", "finished"), ("Standby", "standby"), ("unavailable", "unknown")]:
                with self.subTest(value=value):
                    snapshot = service.evaluate(self.states(value))
                    laundry = snapshot.as_dict()["washing_machine"]
                    self.assertEqual(laundry["state"], expected)
                    if expected in {"running", "finished"}:
                        self.assertIn(laundry["summary"], snapshot.summary)
                    else:
                        self.assertNotIn(laundry["summary"], snapshot.summary)

    def test_missing_sensor_does_not_use_stored_cycle_or_power(self):
        states = [
            {"entity_id": "input_select.laundry_room_washing_machine_cycle", "state": "Läuft"},
            {"entity_id": "sensor.laundry_room_washing_machine_plug_power", "state": "1500"},
        ]
        self.assertEqual(washing_machine_status(states)["state"], "unknown")

    def test_telegram_reads_current_state_without_llm(self):
        service = TelegramService(messaging=object())
        with patch("backend.services.home_hub.service.HomeHub.default") as hub, patch("backend.services.llm.factory.create_llm_client") as llm:
            hub.return_value.healthy.return_value = True
            for question, value, text in [
                ("Läuft die Waschmaschine?", "Läuft", "läuft gerade"),
                ("Ist die Waschmaschine fertig?", "Beendet", "ist fertig"),
                ("Läuft die Waschmaschine oder nicht?", "Standby", "läuft nicht"),
                ("Ist die Wäsche fertig?", "unavailable", "nicht verfügbar"),
            ]:
                hub.return_value.states.return_value = self.states(value)
                self.assertIn(text, service.answer(question))
            hub.return_value.healthy.return_value = False
            self.assertIn("nicht verfügbar", service.answer("Läuft die Waschmaschine?"))
            llm.assert_not_called()

    def test_general_house_summary_includes_laundry(self):
        snapshot = _home_assistant_snapshot(self.states("Beendet"))
        self.assertEqual(snapshot["washing_machine"]["state"], "finished")
        self.assertIn("Waschmaschine ist fertig", _house_status_answer("Wie geht es dem Haus?", {"home_assistant": snapshot}))
