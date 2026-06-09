import json
import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

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

    def test_install_update_dry_run_writes_state_and_simulated_backup(self):
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
            self.assertEqual(admin_status["backup"]["status"], "skipped")
            self.assertEqual(admin_status["backup"]["reason"], "dry_run")
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
                "updates:\n  execution_mode: local_no_restart\n  manifest_path: update-manifest.json\n",
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

    def test_legacy_local_update_schedules_systemd_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._paths(tmp)
            paths.version_file.write_text(json.dumps({"version": "1.2.0", "build": "test", "commit": "abc"}), encoding="utf-8")
            source_zip = paths.api_dir / "release.zip"
            with zipfile.ZipFile(source_zip, "w") as archive:
                archive.writestr("release/backend/new_feature.txt", "installed")
            sha256 = hashlib.sha256(source_zip.read_bytes()).hexdigest()
            paths.config_path.write_text(
                "updates:\n"
                "  execution_mode: local\n"
                "  manifest_path: update-manifest.json\n"
                "  systemd_restart_command: /bin/echo restart-agent-api\n",
                encoding="utf-8",
            )
            paths.manifest_file.write_text(
                json.dumps({
                    "product": "personal",
                    "latest_version": "1.4.0",
                    "download_url": source_zip.as_uri(),
                    "sha256": sha256,
                    "components": {"application": {"update": True}},
                }),
                encoding="utf-8",
            )
            service = UpdateService(paths)
            service.check_for_updates()
            service.install_update(username="admin")
            restart = service.admin_status()["install"]["restart"]
            self.assertEqual(restart["status"], "scheduled")
            self.assertEqual(restart["command"], ["/bin/echo", "restart-agent-api"])

    def test_local_systemd_update_installs_zip_and_schedules_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._paths(tmp)
            (paths.api_dir / ".env").write_text("SECRET=keep", encoding="utf-8")
            (paths.api_dir / "data").mkdir(parents=True)
            (paths.api_dir / "data" / "private.db").write_text("db", encoding="utf-8")
            paths.version_file.write_text(json.dumps({"version": "1.2.0", "build": "test", "commit": "abc"}), encoding="utf-8")
            source_zip = paths.api_dir / "release.zip"
            with zipfile.ZipFile(source_zip, "w") as archive:
                archive.writestr("release/backend/new_feature.txt", "installed")
                archive.writestr("release/.env", "SECRET=replace")
                archive.writestr("release/data/private.db", "replace")
            sha256 = hashlib.sha256(source_zip.read_bytes()).hexdigest()
            paths.config_path.write_text(
                "updates:\n"
                "  execution_mode: local_systemd\n"
                "  manifest_path: update-manifest.json\n"
                "  systemd_service: agent-api\n"
                "  systemd_restart_command: /bin/echo restart-agent-api\n",
                encoding="utf-8",
            )
            paths.manifest_file.write_text(
                json.dumps({
                    "product": "personal",
                    "latest_version": "1.4.0",
                    "download_url": source_zip.as_uri(),
                    "sha256": sha256,
                    "components": {"application": {"update": True}},
                }),
                encoding="utf-8",
            )
            service = UpdateService(paths)
            service.check_for_updates()
            status = service.install_update(username="admin")

            self.assertEqual(status["current_version"], "1.4.0")
            self.assertEqual((paths.api_dir / "backend" / "new_feature.txt").read_text(encoding="utf-8"), "installed")
            self.assertEqual((paths.api_dir / ".env").read_text(encoding="utf-8"), "SECRET=keep")
            self.assertEqual((paths.api_dir / "data" / "private.db").read_text(encoding="utf-8"), "db")
            restart = service.admin_status()["install"]["restart"]
            self.assertEqual(restart["status"], "scheduled")
            self.assertEqual(restart["command"], ["/bin/echo", "restart-agent-api"])

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

    def test_rollback_is_rejected_for_local_deployments(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._paths(tmp)
            paths.version_file.write_text(json.dumps({"version": "1.2.0", "build": "test", "commit": "abc"}), encoding="utf-8")
            paths.config_path.write_text("updates:\n  execution_mode: local\n", encoding="utf-8")
            service = UpdateService(paths)
            with self.assertRaisesRegex(RuntimeError, "Docker"):
                service.rollback(username="admin")

    def test_zip_docker_manifest_does_not_use_local_zip_installer(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._paths(tmp)
            paths.version_file.write_text(json.dumps({"version": "1.2.0", "build": "test", "commit": "abc"}), encoding="utf-8")
            paths.config_path.write_text("updates:\n  execution_mode: zip_docker\n  manifest_path: update-manifest.json\n", encoding="utf-8")
            paths.manifest_file.write_text(
                json.dumps({
                    "product": "personal",
                    "latest_version": "1.4.0",
                    "download_url": "file:///tmp/app.zip",
                    "sha256": "0" * 64,
                    "components": {"application": {"update": True}},
                }),
                encoding="utf-8",
            )
            service = UpdateService(paths)
            service.check_for_updates()
            self.assertFalse(service._uses_application_zip(service.admin_status()["latest"]))

    def test_zip_docker_update_copies_package_without_overwriting_local_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._paths(tmp)
            root = Path(tmp)
            deploy = root / "deploy"
            deploy.mkdir()
            (deploy / ".env").write_text("SECRET=keep", encoding="utf-8")
            (deploy / "config.yaml").write_text("secret: keep", encoding="utf-8")
            (deploy / "data").mkdir()
            (deploy / "data" / "local.db").write_text("db", encoding="utf-8")
            (deploy / "docker-compose.yml").write_text("old-compose", encoding="utf-8")
            (deploy / "version.json").write_text(json.dumps({"version": "1.2.0"}), encoding="utf-8")
            source_zip = paths.api_dir / "seniorcare.zip"
            with zipfile.ZipFile(source_zip, "w") as archive:
                archive.writestr("seniorcare-1.4.0/backend/main.py", "new")
                archive.writestr("seniorcare-1.4.0/frontend/dist/index.html", "<html></html>")
                archive.writestr("seniorcare-1.4.0/requirements.txt", "fastapi")
                archive.writestr("seniorcare-1.4.0/Dockerfile", "FROM python:3.12-slim")
                archive.writestr("seniorcare-1.4.0/docker-compose.yml", "services: {}")
                archive.writestr("seniorcare-1.4.0/version.json", json.dumps({"version": "1.4.0"}))
                archive.writestr("seniorcare-1.4.0/update-manifest.json", "{}")
                archive.writestr("seniorcare-1.4.0/README.md", "readme")
                archive.writestr("seniorcare-1.4.0/.env", "SECRET=replace")
                archive.writestr("seniorcare-1.4.0/config.yaml", "secret: replace")
                archive.writestr("seniorcare-1.4.0/data/local.db", "replace")
            paths.version_file.write_text(json.dumps({"version": "1.2.0", "build": "test", "commit": "abc"}), encoding="utf-8")
            paths.config_path.write_text(
                f"updates:\n  execution_mode: zip_docker\n  manifest_path: update-manifest.json\n  deployment_dir: {deploy}\n  compose_project_dir: {deploy}\n  healthcheck_url: http://127.0.0.1:8080/health\n",
                encoding="utf-8",
            )
            paths.manifest_file.write_text(
                json.dumps({
                    "product": "personal",
                    "latest_version": "1.4.0",
                    "download_url": source_zip.as_uri(),
                    "sha256": "",
                    "components": {"application": {"update": True}},
                }),
                encoding="utf-8",
            )
            service = UpdateService(paths)
            service.check_for_updates()

            class Response:
                status = 200
                def __enter__(self):
                    return self
                def __exit__(self, *_args):
                    return False

            commands: list[list[str]] = []

            def fake_run(*args, **kwargs):
                command = args[0] if args else kwargs.get("args")
                if isinstance(command, list):
                    commands.append(command)
                return type("Completed", (), {"returncode": 0, "stdout": "", "stderr": ""})()

            with patch("backend.services.update_service.shutil.which", return_value="/usr/bin/docker"), \
                 patch("backend.services.update_service.subprocess.run", side_effect=fake_run), \
                 patch("backend.services.update_service.urllib.request.urlopen", return_value=Response()):
                status = service.install_update(username="admin")

            self.assertEqual(status["current_version"], "1.4.0")
            self.assertEqual((deploy / ".env").read_text(encoding="utf-8"), "SECRET=keep")
            self.assertEqual((deploy / "config.yaml").read_text(encoding="utf-8"), "secret: keep")
            self.assertEqual((deploy / "data" / "local.db").read_text(encoding="utf-8"), "db")
            self.assertEqual((deploy / "backend" / "main.py").read_text(encoding="utf-8"), "new")
            self.assertEqual((deploy / "docker-compose.yml").read_text(encoding="utf-8"), "services: {}")
            self.assertTrue((deploy / "backups").exists())
            self.assertIn(["docker", "compose", "up", "-d", "--build"], commands)
            self.assertNotIn(["docker", "restart", "robotersteve-api"], commands)
            self.assertFalse(any(command[-1:] == ["restart"] or "restart" in command for command in commands))

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
