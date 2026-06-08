import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.agents.scheduler.service import SchedulerService
from backend.agents.scheduler.store import SchedulerStore


class DisabledAgentControl:
    called_run = False

    def capabilities(self):
        return ["status", "run"]

    def execute(self, action, payload=None):
        if action == "status":
            return {"ok": True, "status": "disabled", "data": {"enabled": False, "current_status": "disabled"}}
        if action == "run":
            self.called_run = True
            return {"ok": True, "status": "active", "data": {"enabled": True}}
        return {"ok": False, "status": "unsupported", "data": {}}


class SchedulerDisabledAgentTests(unittest.TestCase):
    def test_execute_task_skips_disabled_target_agent(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SchedulerStore(database_path=Path(tmp) / "scheduler.db")
            task = store.create_task({
                "name": "Market Analyse Test",
                "description": "Soll bei deaktiviertem Agent nicht laufen.",
                "enabled": True,
                "schedule_type": "recurring",
                "schedule": {"time": "18:00"},
                "target_agent": "market",
                "target_action": "run",
                "action_type": "execute_action",
            })
            control = DisabledAgentControl()
            service = SchedulerService(store=store)
            with patch("backend.agents.registry.get_agent_control", return_value=control):
                result = service.execute_task(task)
            self.assertEqual(result["status"], "skipped")
            self.assertFalse(control.called_run)
            updated = store.get_task(task["id"])
            self.assertEqual(updated["status"], "paused")
            self.assertEqual(updated["failure_count"], 0)


if __name__ == "__main__":
    unittest.main()
