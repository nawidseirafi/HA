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
    def test_obsolete_manifest_default_tasks_are_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SchedulerStore(database_path=Path(tmp) / "scheduler.db")
            obsolete = store.create_task({
                "name": "Market Analyse 06:00",
                "description": "Alter Default.",
                "enabled": True,
                "schedule_type": "recurring",
                "schedule": {"time": "06:00"},
                "target_agent": "market",
                "target_action": "run",
                "action_type": "execute_action",
                "source": "manifest:market",
                "default_key": "market:analysis:0600",
            })
            manual = store.create_task({
                "name": "Market Manuell",
                "description": "Bleibt erhalten.",
                "enabled": True,
                "schedule_type": "recurring",
                "schedule": {"time": "09:00"},
                "target_agent": "market",
                "target_action": "run",
                "action_type": "execute_action",
                "source": "manual",
            })

            store._remove_obsolete_default_tasks([
                {
                    "source": "manifest:market",
                    "default_key": "market:analysis:1800",
                }
            ])

            self.assertIsNone(store.get_task(obsolete["id"]))
            self.assertIsNotNone(store.get_task(manual["id"]))

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

    def test_execute_task_skips_unavailable_target_agent(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SchedulerStore(database_path=Path(tmp) / "scheduler.db")
            task = store.create_task({
                "name": "Market Analyse Test",
                "description": "Alter Task aus einer anderen Edition.",
                "enabled": True,
                "schedule_type": "recurring",
                "schedule": {"time": "18:00"},
                "target_agent": "market",
                "target_action": "run",
                "action_type": "execute_action",
            })
            service = SchedulerService(store=store)
            with patch("backend.agents.registry.get_agent_control", return_value=None):
                result = service.execute_task(task)
            self.assertEqual(result["status"], "skipped")
            self.assertIn("nicht verfuegbar", result["message"])
            updated = store.get_task(task["id"])
            self.assertEqual(updated["status"], "paused")
            self.assertEqual(updated["failure_count"], 0)
            self.assertIsNone(updated["last_error"])


if __name__ == "__main__":
    unittest.main()
