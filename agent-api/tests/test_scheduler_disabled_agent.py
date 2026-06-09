import tempfile
import unittest
from datetime import datetime, timezone
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
    def test_infrastructure_default_runs_once_daily_at_0700(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SchedulerStore(database_path=Path(tmp) / "scheduler.db")
            task = next(
                item
                for item in store.list_tasks()
                if item.get("default_key") == "platform:infrastructure:health-check"
            )
            self.assertEqual(task["schedule_type"], "cron")
            self.assertEqual(task["schedule"], {"cron": "0 7 * * *", "timezone": "Europe/Berlin"})

    def test_scheduler_cron_interprets_timezone_as_local_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SchedulerStore(database_path=Path(tmp) / "scheduler.db")
            next_run = store.compute_next_run(
                "cron",
                {"cron": "0 7 * * *", "timezone": "Europe/Berlin"},
                datetime(2026, 6, 9, 4, 0, tzinfo=timezone.utc),
            )
            self.assertEqual(next_run, "2026-06-09T05:00:00+00:00")

    def test_platform_healthcheck_success_does_not_notify_message_center(self):
        service = SchedulerService()
        self.assertFalse(service._should_notify_success({
            "source": "platform",
            "action_type": "infrastructure_check",
        }))
        self.assertTrue(service._should_notify_success({
            "source": "manual",
            "action_type": "infrastructure_check",
        }))

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
