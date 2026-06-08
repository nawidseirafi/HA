import json
import tempfile
import unittest
from pathlib import Path

from backend.services.update_service import UpdatePaths, UpdateService, compare_versions


class UpdateServiceTests(unittest.TestCase):
    def test_compare_versions(self):
        self.assertGreater(compare_versions("1.3.0", "1.2.9"), 0)
        self.assertEqual(compare_versions("1.2", "1.2.0"), 0)
        self.assertLess(compare_versions("1.2.0", "1.2.1"), 0)

    def test_mock_check_detects_available_update(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._paths(tmp)
            paths.version_file.write_text(json.dumps({"version": "1.2.0", "build": "test", "commit": "abc"}), encoding="utf-8")
            paths.config_path.write_text(
                "updates:\n  channel: stable\n  mock_latest:\n    latest_version: 1.3.0\n    release_notes: Test update\n",
                encoding="utf-8",
            )
            service = UpdateService(paths)
            result = service.check_for_updates()
            self.assertTrue(result["ok"])
            self.assertTrue(result["update_available"])
            self.assertEqual(result["latest_version"], "1.3.0")
            self.assertEqual(result["release_notes"], ["Test update"])

    def test_install_update_dry_run_writes_state_and_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._paths(tmp)
            (paths.api_dir / "data" / "user").mkdir(parents=True)
            (paths.api_dir / "data" / "user" / "file.txt").write_text("user-data", encoding="utf-8")
            paths.version_file.write_text(json.dumps({"version": "1.2.0", "build": "test", "commit": "abc"}), encoding="utf-8")
            paths.config_path.write_text(
                "updates:\n  execution_mode: dry_run\n  mock_latest:\n    latest_version: 1.3.0\n    release_notes: Test update\n",
                encoding="utf-8",
            )
            service = UpdateService(paths)
            service.check_for_updates()
            status = service.install_update(username="admin")
            self.assertEqual(status["status"], "success")
            self.assertEqual(status["state"], "success")
            self.assertEqual(status["progress"], 100)
            self.assertEqual(status["current_version"], "1.3.0")
            admin_status = service.admin_status()
            self.assertTrue(Path(admin_status["backup"]["path"]).exists())
            self.assertTrue(admin_status["backup"]["path"].endswith(".tar.gz"))
            self.assertIn("dry_run", json.dumps(admin_status))

    def test_install_rejects_unknown_layer(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._paths(tmp)
            paths.version_file.write_text(json.dumps({"version": "1.2.0", "build": "test", "commit": "abc"}), encoding="utf-8")
            paths.config_path.write_text(
                "updates:\n  execution_mode: dry_run\n  mock_latest:\n    latest_version: 1.3.0\n",
                encoding="utf-8",
            )
            service = UpdateService(paths)
            with self.assertRaises(ValueError):
                service.install_update(username="admin", layer="unknown")

    def test_local_manifest_is_used_before_mock(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._paths(tmp)
            paths.version_file.write_text(json.dumps({"version": "1.2.0", "build": "test", "commit": "abc"}), encoding="utf-8")
            paths.config_path.write_text(
                "updates:\n  channel: stable\n  manifest_path: update-manifest.json\n  mock_latest:\n    latest_version: 9.9.9\n",
                encoding="utf-8",
            )
            paths.manifest_file.write_text(
                json.dumps({
                    "schema_version": 1,
                    "editions": {
                        "personal": {
                            "channels": {
                                "stable": {
                                    "latest_version": "1.4.0",
                                    "download_url": "manifest://test",
                                    "mandatory": False,
                                    "release_notes": ["Manifest update"],
                                    "components": {
                                        "application": {"update": True},
                                        "homeassistant": {"update": False},
                                        "ollama": {"update": False},
                                        "system": {"update": False},
                                    },
                                }
                            }
                        }
                    },
                }),
                encoding="utf-8",
            )
            service = UpdateService(paths)
            result = service.check_for_updates()
            self.assertTrue(result["update_available"])
            self.assertEqual(result["latest_version"], "1.4.0")
            self.assertEqual(service.admin_status()["latest"]["source"], "manifest")
            self.assertEqual(result["release_notes"], ["Manifest update"])

    def test_manifest_components_control_internal_layers(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._paths(tmp)
            paths.version_file.write_text(json.dumps({"version": "1.2.0", "build": "test", "commit": "abc"}), encoding="utf-8")
            paths.config_path.write_text("updates:\n  execution_mode: dry_run\n  manifest_path: update-manifest.json\n", encoding="utf-8")
            paths.manifest_file.write_text(
                json.dumps({
                    "latest_version": "1.4.0",
                    "release_notes": ["Component update"],
                    "components": {
                        "application": {"update": True},
                        "homeassistant": {"update": False},
                        "ollama": {"update": False},
                        "system": {"update": False},
                    },
                }),
                encoding="utf-8",
            )
            service = UpdateService(paths)
            service.check_for_updates()
            service.install_update(username="admin")
            self.assertEqual(service.admin_status()["install"]["layers"], ["application"])

    def _paths(self, tmp: str) -> UpdatePaths:
        root = Path(tmp)
        return UpdatePaths(
            api_dir=root,
            config_path=root / "config.yaml",
            env_path=root / ".env",
            version_file=root / "version.json",
            manifest_file=root / "update-manifest.json",
            state_file=root / "data" / "system" / "update_state.json",
            audit_log=root / "logs" / "update_audit.jsonl",
            backup_dir=root / "data" / "backups" / "updates",
        )


if __name__ == "__main__":
    unittest.main()
