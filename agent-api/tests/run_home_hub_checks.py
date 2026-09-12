"""Run house integration tests with temporary data and no external network."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend import config


def main():
    original_resolve = config.resolve_api_path
    with tempfile.TemporaryDirectory() as tmp:
        def resolve(path, fallback):
            resolved = original_resolve(path, fallback)
            try:
                relative = resolved.relative_to(ROOT / "data")
            except ValueError:
                return resolved
            return Path(tmp) / relative

        with patch.object(config, "resolve_api_path", side_effect=resolve), patch("socket.socket.connect", side_effect=RuntimeError("External network disabled in tests")):
            suite = unittest.TestSuite()
            for pattern in ("test_home_hub.py", "test_telegram_agent.py", "test_household_safety.py", "test_household_front_light.py", "test_context_service.py", "test_agent_control.py", "test_scheduler_disabled_agent.py", "test_homeassistant_energy.py", "test_washing_machine.py"):
                suite.addTests(unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern=pattern))
            result = unittest.TextTestRunner(verbosity=1).run(suite)
            return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
