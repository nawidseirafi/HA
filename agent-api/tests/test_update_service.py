import json
import hashlib
import tempfile
import unittest
import zipfile
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

    def test_static_manifest_url_is_supported(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._paths(tmp)
            paths.version_file.write_text(json.dumps({"version": "1.2.0", "build": "test", "commit": "abc"}), encoding="utf-8")
            manifest = paths.api_dir / "latest.json"
            manifest.write_text(
                json.dumps({
                    "latest_version": "1.4.0",
                    "download_url": "https://updates.example.com/releases/app.zip",
                    "sha256": "0" * 64,
                    "release_notes": ["Static manifest"],
                    "components": {"application": {"update": True}},
                }),
                encoding="utf-8",
            )
            paths.config_path.write_text(f"updates:\n  manifest_url: {manifest.as_uri()}\n", encoding="utf-8")
            service = UpdateService(paths)
            result = service.check_for_updates()
            self.assertTrue(result["update_available"])
            self.assertEqual(result["latest_version"], "1.4.0")
            self.assertEqual(service.admin_status()["latest"]["source"], "manifest_url")

    def test_application_zip_update_downloads_verifies_and_installs(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._paths(tmp)
            paths.version_file.write_text(json.dumps({"version": "1.2.0", "build": "test", "commit": "abc"}), encoding="utf-8")
            source_zip = paths.api_dir / "release.zip"
            with zipfile.ZipFile(source_zip, "w") as archive:
                archive.writestr("release/backend/new_feature.txt", "installed")
                archive.writestr("release/data/private.db", "must-not-copy")
            sha256 = hashlib.sha256(source_zip.read_bytes()).hexdigest()
            paths.config_path.write_text(
                "updates:\n  execution_mode: local\n  manifest_path: update-manifest.json\n",
                encoding="utf-8",
            )
            paths.manifest_file.write_text(
                json.dumps({
                    "product": "personal",
                    "latest_version": "1.4.0",
                    "download_url": source_zip.as_uri(),
                    "sha256": sha256,
                    "release_notes": ["Zip update"],
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
            status = service.install_update(username="admin")
            self.assertEqual(status["current_version"], "1.4.0")
            self.assertEqual((paths.api_dir / "backend" / "new_feature.txt").read_text(encoding="utf-8"), "installed")
            self.assertFalse((paths.api_dir / "data" / "private.db").exists())
            command_results = service.admin_status()["install"]["command_results"]
            self.assertEqual(command_results[0]["status"], "installed")

    def test_application_zip_rejects_wrong_product(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._paths(tmp)
            paths.version_file.write_text(json.dumps({"version": "1.2.0", "build": "test", "commit": "abc"}), encoding="utf-8")
            source_zip = paths.api_dir / "release.zip"
            with zipfile.ZipFile(source_zip, "w") as archive:
                archive.writestr("backend/new_feature.txt", "installed")
            sha256 = hashlib.sha256(source_zip.read_bytes()).hexdigest()
            paths.config_path.write_text("updates:\n  execution_mode: local\n  manifest_path: update-manifest.json\n", encoding="utf-8")
            paths.manifest_file.write_text(
                json.dumps({
                    "product": "seniorcare",
                    "latest_version": "1.4.0",
                    "download_url": source_zip.as_uri(),
                    "sha256": sha256,
                    "components": {"application": {"update": True}},
                }),
                encoding="utf-8",
            )
            service = UpdateService(paths)
            service.check_for_updates()
            with self.assertRaises(RuntimeError):
                service.install_update(username="admin")

    def test_application_zip_rejects_too_old_current_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._paths(tmp)
            paths.version_file.write_text(json.dumps({"version": "1.2.0", "build": "test", "commit": "abc"}), encoding="utf-8")
            source_zip = paths.api_dir / "release.zip"
            with zipfile.ZipFile(source_zip, "w") as archive:
                archive.writestr("backend/new_feature.txt", "installed")
            sha256 = hashlib.sha256(source_zip.read_bytes()).hexdigest()
            paths.config_path.write_text("updates:\n  execution_mode: local\n  manifest_path: update-manifest.json\n", encoding="utf-8")
            paths.manifest_file.write_text(
                json.dumps({
                    "product": "personal",
                    "latest_version": "1.4.0",
                    "minimum_version": "1.3.0",
                    "download_url": source_zip.as_uri(),
                    "sha256": sha256,
                    "components": {"application": {"update": True}},
                }),
                encoding="utf-8",
            )
            service = UpdateService(paths)
            service.check_for_updates()
            with self.assertRaises(RuntimeError):
                service.install_update(username="admin")

    def test_application_zip_requires_matching_sha256(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._paths(tmp)
            paths.version_file.write_text(json.dumps({"version": "1.2.0", "build": "test", "commit": "abc"}), encoding="utf-8")
            source_zip = paths.api_dir / "release.zip"
            with zipfile.ZipFile(source_zip, "w") as archive:
                archive.writestr("backend/new_feature.txt", "installed")
            paths.config_path.write_text(
                "updates:\n  execution_mode: local\n  manifest_path: update-manifest.json\n",
                encoding="utf-8",
            )
            paths.manifest_file.write_text(
                json.dumps({
                    "latest_version": "1.4.0",
                    "download_url": source_zip.as_uri(),
                    "sha256": "0" * 64,
                    "release_notes": ["Zip update"],
                    "components": {"application": {"update": True}},
                }),
                encoding="utf-8",
            )
            service = UpdateService(paths)
            service.check_for_updates()
            with self.assertRaises(RuntimeError):
                service.install_update(username="admin")

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
