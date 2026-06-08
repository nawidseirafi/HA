import unittest

from backend.agents.control import AgentControlAdapter


class MyWellnessLikeService:
    def __init__(self, result_status="ok", snapshot_status="error", last_error="alter Fehler") -> None:
        self.result_status = result_status
        self.snapshot_status = snapshot_status
        self.last_error = last_error

    def run_action(self, action_type: str, dry_run: bool = False):
        return {
            "result": {
                "status": self.result_status,
                "message": f"{action_type} abgeschlossen.",
            },
            "status": {
                "status": self.snapshot_status,
                "current_status": self.snapshot_status,
                "last_status": self.snapshot_status,
                "last_error": self.last_error,
            },
        }


class AgentControlAdapterTests(unittest.TestCase):
    def test_run_uses_nested_result_status_before_status_snapshot(self):
        adapter = AgentControlAdapter("mywellness", MyWellnessLikeService())

        result = adapter.execute("run", {"mode": "prepare"})

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "active")
        self.assertEqual(result["message"], "prepare abgeschlossen.")

    def test_run_still_fails_when_nested_result_status_is_error(self):
        adapter = AgentControlAdapter("mywellness", MyWellnessLikeService(result_status="error", snapshot_status="active"))

        result = adapter.execute("run", {"mode": "book"})

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "error")


if __name__ == "__main__":
    unittest.main()
