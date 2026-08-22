import unittest

from backend.api.orchestrator_routes import orchestrator_map


class OrchestratorMapTests(unittest.TestCase):
    def test_telegram_agent_exposes_runtime_dependencies(self):
        data = orchestrator_map(live=False)
        edge_ids = {edge["id"] for edge in data["edges"]}

        self.assertIn("orchestrator-telegram", edge_ids)
        self.assertIn("telegram-database", edge_ids)
        self.assertIn("telegram-openai", edge_ids)
        self.assertIn("telegram-homeassistant", edge_ids)
        self.assertIn("telegram-messaging", edge_ids)


if __name__ == "__main__":
    unittest.main()
