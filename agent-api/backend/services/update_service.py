from __future__ import annotations

import json
import os
import platform
import hashlib
import shutil
import subprocess
import tarfile
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

import yaml

from backend.editions import active_edition
from backend.paths import API_CONFIG_PATH, API_DIR, ENV_PATH, PROJECT_DIR

VERSION_FILE = API_DIR / "version.json"
UPDATE_MANIFEST_FILE = API_DIR / "update-manifest.json"
UPDATE_STATE_FILE = API_DIR / "data" / "system" / "update_state.json"
UPDATE_AUDIT_LOG = API_DIR / "logs" / "update_audit.jsonl"
DEFAULT_BACKUP_DIR = Path("/opt/roboterSteve/backups")
DEFAULT_VERSION = "0.1.0"
DEFAULT_CHANNEL = "stable"
UPDATE_LAYERS = ("application", "ai_runtime", "homeassistant", "system")
VALID_CHANNELS = {"stable", "beta", "dev"}
STEP_PENDING = "pending"
STEP_RUNNING = "running"
STEP_SUCCESS = "success"
STEP_FAILED = "failed"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class UpdatePaths:
    api_dir: Path = API_DIR
    project_dir: Path = PROJECT_DIR
    config_path: Path = API_CONFIG_PATH
    env_path: Path = ENV_PATH
    version_file: Path = VERSION_FILE
    manifest_file: Path = UPDATE_MANIFEST_FILE
    state_file: Path = UPDATE_STATE_FILE
    audit_log: Path = UPDATE_AUDIT_LOG
    backup_dir: Path | None = None


class UpdateConfigMixin:
    def __init__(self, paths: UpdatePaths | None = None) -> None:
        self.paths = paths or UpdatePaths()

    def _load_config(self) -> dict[str, Any]:
        if not self.paths.config_path.exists():
            return {}
        try:
            data = yaml.safe_load(self.paths.config_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            return {}
        return data if isinstance(data, dict) else {}

    def _update_config(self) -> dict[str, Any]:
        config = self._load_config()
        value = config.get("updates") if isinstance(config.get("updates"), dict) else {}
        return value if isinstance(value, dict) else {}

    def _load_env_values(self) -> dict[str, str]:
        values: dict[str, str] = {}
        if not self.paths.env_path.exists():
            return values
        for raw_line in self.paths.env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, raw_value = line.split("=", 1)
            values[key.strip()] = raw_value.strip().strip("\"'")
        return values

    def _env(self, name: str, env_values: dict[str, str] | None = None) -> str | None:
        env_values = env_values if env_values is not None else self._load_env_values()
        return os.getenv(name) or os.getenv(name.upper()) or env_values.get(name) or env_values.get(name.upper())

    def channel(self) -> str:
        update_config = self._update_config()
        value = str(self._env("UPDATE_CHANNEL") or update_config.get("channel") or DEFAULT_CHANNEL).strip().lower()
        return value if value in VALID_CHANNELS else DEFAULT_CHANNEL

    def execution_mode(self) -> str:
        update_config = self._update_config()
        mode = str(self._env("UPDATE_EXECUTION_MODE") or update_config.get("execution_mode") or "dry_run").strip().lower()
        return mode if mode in {"docker", "local"} else "dry_run"

    def update_server_url(self) -> str:
        update_config = self._update_config()
        return str(self._env("UPDATE_SERVER_URL") or update_config.get("server_url") or "").strip()

    def update_manifest_url(self) -> str:
        update_config = self._update_config()
        return str(self._env("UPDATE_MANIFEST_URL") or update_config.get("manifest_url") or "").strip()

    def update_manifest_path(self) -> Path:
        update_config = self._update_config()
        raw = self._env("UPDATE_MANIFEST_PATH") or update_config.get("manifest_path")
        if raw:
            path = Path(str(raw)).expanduser()
            return path if path.is_absolute() else self.paths.api_dir / path
        return self.paths.manifest_file

    def service_names(self) -> dict[str, str]:
        update_config = self._update_config()
        services = update_config.get("services") if isinstance(update_config.get("services"), dict) else {}
        return {
            "api": str(services.get("api") or "robotersteve-api"),
            "ollama": str(services.get("ollama") or "ollama"),
            "homeassistant": str(services.get("homeassistant") or "homeassistant"),
        }

    def backup_dir(self) -> Path:
        update_config = self._update_config()
        raw = self._env("ROBOTERSTEVE_BACKUP_DIR") or update_config.get("backup_dir")
        if raw:
            return Path(str(raw)).expanduser()
        if self.paths.backup_dir is not None:
            return self.paths.backup_dir
        return DEFAULT_BACKUP_DIR

    def ollama_models(self) -> list[str]:
        update_config = self._update_config()
        models = update_config.get("ollama_models") if isinstance(update_config.get("ollama_models"), list) else []
        env_models = self._env("OLLAMA_UPDATE_MODELS")
        if env_models:
            models = [item.strip() for item in env_models.split(",")]
        return [str(item).strip() for item in models if str(item).strip()]

    def _read_json(self, path: Path, default: dict[str, Any]) -> dict[str, Any]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return dict(default)
        return data if isinstance(data, dict) else dict(default)

    def _write_json(self, path: Path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


class VersionService(UpdateConfigMixin):
    def version(self) -> dict[str, Any]:
        metadata = self._read_json(self.paths.version_file, {})
        config = self._load_config()
        version_config = config.get("version") if isinstance(config.get("version"), dict) else {}
        app_version = str(self._env("ROBOTERSTEVE_VERSION") or metadata.get("version") or version_config.get("version") or DEFAULT_VERSION)
        build = str(self._env("ROBOTERSTEVE_BUILD") or metadata.get("build") or version_config.get("build") or datetime.now().strftime("%Y.%m.%d"))
        commit = str(self._env("ROBOTERSTEVE_COMMIT") or metadata.get("commit") or version_config.get("commit") or "unknown")
        return {
            "edition": active_edition().name,
            "app_version": app_version,
            "version": app_version,
            "build": build,
            "commit": commit,
            "docker_version": self._command_version(["docker", "--version"]),
            "docker_compose_version": self._docker_compose_version(),
            "ollama_version": self._ollama_version(),
            "homeassistant_version": self._homeassistant_version(),
            "os_version": self._os_version(),
            "channel": self.channel(),
        }

    def _command_version(self, command: list[str]) -> str:
        try:
            completed = subprocess.run(command, text=True, capture_output=True, timeout=8, check=False)
        except (OSError, subprocess.SubprocessError):
            return "unavailable"
        text = (completed.stdout or completed.stderr).strip()
        return text if completed.returncode == 0 and text else "unavailable"

    def _docker_compose_version(self) -> str:
        compose = ComposeCommandResolver(self.paths).resolve()
        return self._command_version(compose + ["version"])

    def _ollama_version(self) -> str:
        services = self.service_names()
        docker_version = self._command_version(["docker", "exec", services["ollama"], "ollama", "--version"])
        if docker_version != "unavailable":
            return docker_version
        return self._command_version(["ollama", "--version"])

    def _homeassistant_version(self) -> str:
        services = self.service_names()
        for command in (["docker", "exec", services["homeassistant"], "ha", "core", "info"], ["docker", "inspect", "--format", "{{.Config.Image}}", services["homeassistant"]]):
            value = self._command_version(command)
            if value != "unavailable":
                return value
        return "unavailable"

    def _os_version(self) -> str:
        os_release = Path("/etc/os-release")
        if os_release.exists():
            values: dict[str, str] = {}
            for line in os_release.read_text(encoding="utf-8", errors="ignore").splitlines():
                if "=" in line:
                    key, value = line.split("=", 1)
                    values[key] = value.strip().strip('"')
            return values.get("PRETTY_NAME") or values.get("NAME") or platform.platform()
        return platform.platform()


class UpdateCheckService(UpdateConfigMixin):
    def check(self, channel: str | None = None) -> dict[str, Any]:
        selected_channel = self._normalize_channel(channel or self.channel())
        current = VersionService(self.paths).version()
        try:
            latest = self._fetch_latest(selected_channel, current)
            latest_version = str(latest.get("latest_version") or current["app_version"])
            available = compare_versions(latest_version, str(current["app_version"])) > 0
            return {
                "ok": True,
                "offline": False,
                "available": available,
                "update_available": available,
                "current": current,
                "current_version": current["app_version"],
                "channel": selected_channel,
                "latest": latest,
                "latest_version": latest_version,
                "release_notes": latest.get("release_notes", []),
                "checked_at": utc_now(),
                "message": "Update verfuegbar." if available else "System ist aktuell.",
            }
        except Exception as exc:
            return {
                "ok": False,
                "offline": True,
                "available": False,
                "update_available": False,
                "current": current,
                "current_version": current["app_version"],
                "channel": selected_channel,
                "latest": None,
                "latest_version": current["app_version"],
                "release_notes": [],
                "checked_at": utc_now(),
                "message": "Updatepruefung derzeit nicht moeglich. System bleibt funktionsfaehig.",
                "error": str(exc),
            }

    def _fetch_latest(self, channel: str, current: dict[str, Any]) -> dict[str, Any]:
        manifest_url = self.update_manifest_url()
        if manifest_url:
            latest = self._fetch_static_manifest(manifest_url, channel, current)
            latest["source"] = "manifest_url"
            latest["manifest_url"] = manifest_url
            return latest
        server_url = self.update_server_url()
        if not server_url:
            manifest_latest = self._local_manifest_latest(channel, current)
            return manifest_latest if manifest_latest is not None else self._mock_latest(channel, current)
        if server_url.endswith(".json"):
            latest = self._fetch_static_manifest(server_url, channel, current)
            latest["source"] = "manifest_url"
            latest["manifest_url"] = server_url
            return latest
        query = urllib.parse.urlencode({"edition": active_edition().name, "channel": channel, "version": current["app_version"]})
        url = f"{server_url.rstrip('/')}/latest?{query}"
        request = urllib.request.Request(url, headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Update-Server nicht erreichbar: {exc}") from exc
        latest = self._normalize_latest(data, channel, current)
        latest["source"] = "server"
        return latest

    def _fetch_static_manifest(self, url: str, channel: str, current: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(url, headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Update-Manifest nicht erreichbar: {exc}") from exc
        selected = self._select_manifest_entry(data if isinstance(data, dict) else {}, channel)
        if selected is None:
            raise RuntimeError("Update-Manifest enthaelt keine passende Version.")
        return self._normalize_latest(selected, channel, current)

    def _local_manifest_latest(self, channel: str, current: dict[str, Any]) -> dict[str, Any] | None:
        path = self.update_manifest_path()
        if not path.exists():
            return None
        manifest = self._read_json(path, {})
        selected = self._select_manifest_entry(manifest, channel)
        if selected is None:
            return None
        latest = self._normalize_latest(selected, channel, current)
        latest["source"] = "manifest"
        latest["manifest_path"] = str(path)
        latest["schema_version"] = manifest.get("schema_version")
        return latest

    def _select_manifest_entry(self, manifest: dict[str, Any], channel: str) -> dict[str, Any] | None:
        edition_name = active_edition().name
        editions = manifest.get("editions")
        if isinstance(editions, dict):
            edition_block = editions.get(edition_name)
            if isinstance(edition_block, dict):
                entry = self._select_channel_entry(edition_block, channel)
                if entry is not None:
                    return entry
        entry = self._select_channel_entry(manifest, channel)
        if entry is not None:
            return entry
        return manifest if manifest.get("latest_version") or manifest.get("version") else None

    def _select_channel_entry(self, block: dict[str, Any], channel: str) -> dict[str, Any] | None:
        channels = block.get("channels")
        if isinstance(channels, dict):
            value = channels.get(channel) or channels.get(DEFAULT_CHANNEL)
            if isinstance(value, dict):
                return value
        return block if block.get("latest_version") or block.get("version") else None

    def _mock_latest(self, channel: str, current: dict[str, Any]) -> dict[str, Any]:
        update_config = self._update_config()
        mock = update_config.get("mock_latest") if isinstance(update_config.get("mock_latest"), dict) else {}
        latest_version = str(self._env("UPDATE_MOCK_LATEST_VERSION") or mock.get("latest_version") or current["app_version"])
        notes = mock.get("release_notes") or ["Lokaler Mock-Update-Server.", "Keine externen Downloads konfiguriert."]
        latest = self._normalize_latest({
            "latest_version": latest_version,
            "download_url": mock.get("download_url") or "mock://local-update",
            "mandatory": bool(mock.get("mandatory", False)),
            "release_notes": notes,
            "layers": mock.get("layers") or list(UPDATE_LAYERS),
        }, channel, current)
        latest["source"] = "mock"
        return latest

    def _normalize_latest(self, data: dict[str, Any], channel: str, current: dict[str, Any]) -> dict[str, Any]:
        notes = data.get("release_notes") or []
        if isinstance(notes, str):
            notes = [line.strip() for line in notes.splitlines() if line.strip()] or [notes]
        if not isinstance(notes, list):
            notes = []
        components = data.get("components") if isinstance(data.get("components"), dict) else {}
        layers = data.get("layers") if isinstance(data.get("layers"), list) else list(UPDATE_LAYERS)
        if components:
            layers = self._layers_from_components(components)
        return {
            "latest_version": str(data.get("latest_version") or data.get("version") or current["app_version"]),
            "download_url": str(data.get("download_url") or ""),
            "mandatory": bool(data.get("mandatory", False)),
            "release_notes": [str(item) for item in notes],
            "channel": channel,
            "layers": [str(item) for item in layers if str(item) in UPDATE_LAYERS],
            "components": components,
            "artifacts": data.get("artifacts") if isinstance(data.get("artifacts"), dict) else {},
            "minimum_version": str(data.get("minimum_version") or ""),
            "sha256": str(data.get("sha256") or ""),
            "size_bytes": int(data.get("size_bytes") or 0),
            "product": str(data.get("product") or data.get("edition") or ""),
        }

    def _layers_from_components(self, components: dict[str, Any]) -> list[str]:
        mapping = {
            "application": "application",
            "homeassistant": "homeassistant",
            "home_assistant": "homeassistant",
            "ollama": "ai_runtime",
            "ai_runtime": "ai_runtime",
            "system": "system",
        }
        layers: list[str] = []
        for component, raw_config in components.items():
            if not isinstance(raw_config, dict) or not bool(raw_config.get("update", False)):
                continue
            layer = mapping.get(str(component))
            if layer and layer not in layers:
                layers.append(layer)
        return layers

    def _normalize_channel(self, channel: str) -> str:
        value = str(channel or DEFAULT_CHANNEL).strip().lower()
        return value if value in VALID_CHANNELS else DEFAULT_CHANNEL


class BackupEngine(UpdateConfigMixin):
    def create_backup(self, version: dict[str, Any]) -> dict[str, Any]:
        backup_dir = self.backup_dir()
        try:
            backup_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            fallback = self.paths.api_dir / "data" / "backups" / "updates"
            fallback.mkdir(parents=True, exist_ok=True)
            backup_dir = fallback
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        target = backup_dir / f"backup-{stamp}.tar.gz"
        metadata = {"version": version.get("app_version") or version.get("version"), "created": utc_now(), "edition": active_edition().name}
        include_paths = self._backup_sources()
        with tarfile.open(target, "w:gz") as archive:
            metadata_bytes = json.dumps(metadata, ensure_ascii=False, indent=2).encode("utf-8")
            info = tarfile.TarInfo("backup_metadata.json")
            info.size = len(metadata_bytes)
            archive.addfile(info, fileobj=BytesIO(metadata_bytes))
            for path in include_paths:
                self._add_path(archive, path)
        size = target.stat().st_size
        metadata.update({"path": str(target), "size": size, "size_human": _human_size(size)})
        try:
            target.chmod(0o600)
        except OSError:
            pass
        return metadata

    def latest_backup(self) -> Path | None:
        backup_dir = self.backup_dir()
        if not backup_dir.exists():
            return None
        backups = sorted(backup_dir.glob("backup-*.tar.gz"), key=lambda item: item.stat().st_mtime, reverse=True)
        return backups[0] if backups else None

    def restore_latest_backup(self) -> dict[str, Any]:
        backup = self.latest_backup()
        if backup is None:
            raise RuntimeError("Kein Backup fuer Rollback vorhanden.")
        if self.execution_mode() != "docker":
            return {"status": "skipped", "reason": "dry_run", "backup": str(backup)}
        with tarfile.open(backup, "r:gz") as archive:
            self._safe_extract(archive, self.paths.api_dir)
        return {"status": "restored", "backup": str(backup)}

    def _safe_extract(self, archive: tarfile.TarFile, target: Path) -> None:
        target_root = target.resolve()
        for member in archive.getmembers():
            destination = (target_root / member.name).resolve()
            if target_root != destination and target_root not in destination.parents:
                raise RuntimeError(f"Unsicherer Backup-Pfad erkannt: {member.name}")
        archive.extractall(target_root)

    def _backup_sources(self) -> list[Path]:
        return [
            self.paths.api_dir / "config",
            self.paths.config_path,
            self.paths.env_path,
            self.paths.api_dir / "data",
            self.paths.api_dir / "editions",
            self.paths.api_dir / "settings",
            self.paths.api_dir / "backend" / "agents",
        ]

    def _add_path(self, archive: tarfile.TarFile, path: Path) -> None:
        if not path.exists():
            return
        if path.is_file():
            archive.add(path, arcname=self._arcname(path))
            return
        for child in path.rglob("*"):
            if child.is_file() and not self._skip(child):
                archive.add(child, arcname=self._arcname(child))

    def _arcname(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.paths.api_dir))
        except ValueError:
            return path.name

    def _skip(self, path: Path) -> bool:
        parts = set(path.parts)
        if "__pycache__" in parts or "node_modules" in parts or "logs" in parts:
            return True
        if path.suffix in {".pyc", ".pyo"}:
            return True
        try:
            return self.backup_dir() in path.parents
        except RuntimeError:
            return False


class ApplicationZipInstaller(UpdateConfigMixin):
    NEVER_OVERWRITE_NAMES = {
        ".env",
        "__pycache__",
        ".venv",
        "venv",
        "node_modules",
        "logs",
        "data",
    }
    NEVER_OVERWRITE_SUFFIXES = {".db", ".sqlite", ".sqlite3", ".pyc", ".pyo"}

    def install(self, latest: dict[str, Any]) -> dict[str, Any]:
        download_url = str(latest.get("download_url") or "").strip()
        if not download_url:
            raise RuntimeError("Application Update hat keine download_url.")
        expected_sha256 = str(latest.get("sha256") or "").strip().lower()
        if not expected_sha256:
            raise RuntimeError("Application ZIP ohne sha256 wird aus Sicherheitsgruenden nicht installiert.")
        if self.execution_mode() == "dry_run":
            return {"status": "skipped", "reason": "dry_run", "download_url": download_url}

        work_dir = Path(tempfile.mkdtemp(prefix="robotersteve-update-"))
        zip_path = work_dir / "application.zip"
        extract_dir = work_dir / "extract"
        try:
            self._download(download_url, zip_path)
            actual_sha256 = self._sha256(zip_path)
            if actual_sha256 != expected_sha256:
                raise RuntimeError("Application ZIP Pruefsumme ist ungueltig.")
            extract_dir.mkdir(parents=True, exist_ok=True)
            self._safe_extract_zip(zip_path, extract_dir)
            source_root = self._payload_root(extract_dir)
            copied = self._copy_payload(source_root, self.paths.api_dir)
            return {
                "status": "installed",
                "download_url": download_url,
                "sha256": actual_sha256,
                "files_copied": copied,
            }
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    def _download(self, url: str, target: Path) -> None:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme in {"", "file"}:
            source = Path(urllib.request.url2pathname(parsed.path if parsed.scheme == "file" else url)).expanduser()
            if not source.exists():
                raise RuntimeError(f"Application ZIP nicht gefunden: {source}")
            shutil.copy2(source, target)
            return
        if parsed.scheme != "https":
            raise RuntimeError("Application ZIP muss ueber HTTPS bereitgestellt werden.")
        request = urllib.request.Request(url, headers={"Accept": "application/zip, application/octet-stream"})
        try:
            with urllib.request.urlopen(request, timeout=60) as response, target.open("wb") as handle:
                shutil.copyfileobj(response, handle)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise RuntimeError(f"Application ZIP konnte nicht geladen werden: {exc}") from exc

    def _sha256(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _safe_extract_zip(self, zip_path: Path, target: Path) -> None:
        target_root = target.resolve()
        with zipfile.ZipFile(zip_path) as archive:
            for member in archive.infolist():
                destination = (target_root / member.filename).resolve()
                if target_root != destination and target_root not in destination.parents:
                    raise RuntimeError(f"Unsicherer ZIP-Pfad erkannt: {member.filename}")
            archive.extractall(target_root)

    def _payload_root(self, extract_dir: Path) -> Path:
        children = [child for child in extract_dir.iterdir() if child.name != "__MACOSX"]
        if len(children) == 1 and children[0].is_dir():
            return children[0]
        return extract_dir

    def _copy_payload(self, source: Path, target: Path) -> int:
        copied = 0
        for item in source.rglob("*"):
            if not item.is_file() or self._skip(item):
                continue
            relative = item.relative_to(source)
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, destination)
            copied += 1
        return copied

    def _skip(self, path: Path) -> bool:
        if any(part in self.NEVER_OVERWRITE_NAMES for part in path.parts):
            return True
        return path.suffix in self.NEVER_OVERWRITE_SUFFIXES


class ComposeCommandResolver:
    def __init__(self, paths: UpdatePaths) -> None:
        self.paths = paths

    def resolve(self) -> list[str]:
        if shutil.which("docker"):
            try:
                completed = subprocess.run(["docker", "compose", "version"], cwd=self.paths.api_dir, text=True, capture_output=True, timeout=10, check=False)
                if completed.returncode == 0:
                    return ["docker", "compose"]
            except (OSError, subprocess.SubprocessError):
                pass
        if shutil.which("docker-compose"):
            return ["docker-compose"]
        return ["docker", "compose"]


class UpdateExecutionService(UpdateConfigMixin):
    def commands_for_layer(self, layer: str) -> list[list[str]]:
        compose = ComposeCommandResolver(self.paths).resolve()
        services = self.service_names()
        if layer == "application":
            return [compose + ["pull"], compose + ["down"], compose + ["up", "-d"]]
        if layer == "ai_runtime":
            commands = [compose + ["pull", services["ollama"]], compose + ["up", "-d", services["ollama"]]]
            commands.extend([["docker", "exec", services["ollama"], "ollama", "pull", model] for model in self.ollama_models()])
            return commands
        if layer == "homeassistant":
            return [compose + ["pull", services["homeassistant"]], compose + ["up", "-d", services["homeassistant"]]]
        if layer == "system":
            return [["apt", "update"], ["apt", "upgrade", "-y"], ["apt", "autoremove", "-y"]]
        raise ValueError(f"Unbekannte Update-Ebene: {layer}")

    def run_layer(self, layer: str) -> list[dict[str, Any]]:
        return self._run_commands(self.commands_for_layer(layer))

    def rollback_commands(self) -> list[list[str]]:
        compose = ComposeCommandResolver(self.paths).resolve()
        return [compose + ["down"], compose + ["up", "-d"]]

    def _run_commands(self, commands: list[list[str]]) -> list[dict[str, Any]]:
        if self.execution_mode() == "docker":
            text = " && ".join(" ".join(_shell_quote(part) for part in command) for command in commands)
            process = subprocess.Popen(["sh", "-c", f"sleep 2; {text}"], cwd=self.paths.api_dir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            return [{"command": command, "status": "started_background", "pid": process.pid} for command in commands]
        return [{"command": command, "status": "skipped", "reason": "dry_run"} for command in commands]


class RollbackService(UpdateConfigMixin):
    def rollback(self) -> dict[str, Any]:
        executor = UpdateExecutionService(self.paths)
        backup = BackupEngine(self.paths)
        commands = executor.rollback_commands()
        stop_result = executor._run_commands([commands[0]])
        restore_result = backup.restore_latest_backup()
        start_result = executor._run_commands([commands[1]])
        return {"stop": stop_result, "restore": restore_result, "start": start_result}


class UpdateService(UpdateConfigMixin):
    def __init__(self, paths: UpdatePaths | None = None) -> None:
        super().__init__(paths)
        self._lock = threading.Lock()

    def current_version(self) -> dict[str, Any]:
        state = self._read_state()
        version = VersionService(self.paths).version()
        version["previous_version"] = state.get("previous_version")
        version["updated_at"] = state.get("updated_at") or self._read_json(self.paths.version_file, {}).get("updated_at")
        return version

    def status(self) -> dict[str, Any]:
        return self.public_status()

    def public_status(self) -> dict[str, Any]:
        technical = self.admin_status()
        version = technical["version"]
        latest = technical.get("latest") if isinstance(technical.get("latest"), dict) else None
        install = technical.get("install") if isinstance(technical.get("install"), dict) else {}
        status = str(install.get("status") or technical.get("state") or "idle")
        return {
            "product": self.product_name(),
            "current_version": version.get("app_version") or version.get("version") or DEFAULT_VERSION,
            "latest_version": latest.get("latest_version") if latest else None,
            "update_available": bool(technical.get("update_available", False)),
            "last_checked": technical.get("last_check"),
            "status": status,
            "state": status,
            "progress": int(technical.get("progress", 0) or 0),
            "current_step": int(technical.get("current_step", 0) or 0),
            "message": self._public_message(status, bool(technical.get("update_available", False))),
            "release_notes": latest.get("release_notes", []) if latest else [],
            "steps": self._public_steps(install.get("steps") if isinstance(install.get("steps"), list) else None),
            "dev_mode": self.dev_mode_enabled(),
        }

    def admin_status(self) -> dict[str, Any]:
        state = self._read_state()
        install = state.get("install") if isinstance(state.get("install"), dict) else {"status": "idle", "steps": self._initial_steps("-")}
        latest = state.get("latest") if isinstance(state.get("latest"), dict) else None
        status = {
            "state": install.get("status", "idle"),
            "current_step": int(install.get("current_step", 0) or 0),
            "progress": int(install.get("progress", 0) or 0),
            "message": str(install.get("message") or "Bereit."),
            "version": self.current_version(),
            "channel": self.channel(),
            "layers": list(UPDATE_LAYERS),
            "execution_mode": self.execution_mode(),
            "update_server_url": self.update_server_url() or "mock",
            "last_check": state.get("last_check"),
            "latest": latest,
            "update_available": bool(state.get("update_available", False)),
            "install": install,
            "rollback": state.get("rollback") or {"available": bool(BackupEngine(self.paths).latest_backup()), "previous_version": state.get("previous_version")},
            "last_error": state.get("last_error"),
            "backup": state.get("backup"),
        }
        return status

    def check_for_updates(self, channel: str | None = None, notify: bool = False) -> dict[str, Any]:
        result = UpdateCheckService(self.paths).check(channel or DEFAULT_CHANNEL)
        state = self._read_state()
        state.update({
            "last_check": result["checked_at"],
            "latest": result.get("latest"),
            "update_available": bool(result.get("available")),
            "last_error": result.get("error"),
        })
        self._write_state(state)
        if notify and result.get("available"):
            self._notify_update_available(result.get("latest") or {})
        return {
            "ok": bool(result.get("ok", False)),
            "offline": bool(result.get("offline", False)),
            "product": self.product_name(),
            "current_version": result.get("current_version"),
            "latest_version": result.get("latest_version"),
            "update_available": bool(result.get("available")),
            "last_checked": result.get("checked_at"),
            "status": "idle",
            "message": self._public_message("idle", bool(result.get("available"))),
            "release_notes": result.get("release_notes", []),
        }

    def install_update(self, username: str = "admin", layer: str = "auto") -> dict[str, Any]:
        if layer in {"", "auto", None}:
            layers: list[str] = []
        elif layer == "all":
            layers = ["application", "ai_runtime", "homeassistant", "system"]
        elif layer in UPDATE_LAYERS:
            layers = [layer]
        else:
            raise ValueError(f"Unbekannte Update-Ebene: {layer}")
        with self._lock:
            state = self._read_state()
            latest = state.get("latest") if isinstance(state.get("latest"), dict) else None
            if latest is None:
                raw_check = UpdateCheckService(self.paths).check(DEFAULT_CHANNEL)
                latest = raw_check.get("latest") if isinstance(raw_check.get("latest"), dict) else None
                state.update({
                    "last_check": raw_check.get("checked_at"),
                    "latest": latest,
                    "update_available": bool(raw_check.get("available")),
                    "last_error": raw_check.get("error"),
                })
                self._write_state(state)
            if latest is None:
                raise RuntimeError("Kein Update-Metadatum verfuegbar.")
            if not layers:
                layers = self._layers_for_latest(latest)
            if not layers:
                raise RuntimeError("Keine Update-Komponenten fuer diese Version aktiviert.")
            current = self.current_version()
            target_version = str(latest.get("latest_version") or current["app_version"])
            self._validate_latest_for_install(latest, str(current["app_version"]))
            steps = self._initial_steps(target_version)
            self._set_install_state(state, "running", steps, 0, 0, "Update wird vorbereitet.", target_version, layers)
            try:
                self._set_step(state, steps, 0, STEP_SUCCESS, "Vorbereitung abgeschlossen.", 10, "Update wird vorbereitet.")
                self._set_step(state, steps, 1, STEP_RUNNING, "Sicherung wird erstellt.", 20, "Sicherung wird erstellt.")
                backup = BackupEngine(self.paths).create_backup(current)
                self._set_step(state, steps, 1, STEP_SUCCESS, "Sicherung erstellt.", 35, "Sicherung erstellt.")

                command_results: list[dict[str, Any]] = []
                executor = UpdateExecutionService(self.paths)
                self._set_step(state, steps, 2, STEP_RUNNING, "Installation laeuft.", 45, "Update wird installiert.")
                for item in layers:
                    if item == "application" and self._uses_application_zip(latest):
                        command_results.append({"layer": item, **ApplicationZipInstaller(self.paths).install(latest)})
                    else:
                        command_results.extend(executor.run_layer(item))
                self._set_step(state, steps, 2, STEP_SUCCESS, "Installation abgeschlossen.", 70, "Update installiert.")

                self._set_step(state, steps, 3, STEP_RUNNING, "Neustart wird vorbereitet.", 85, "Neustart laeuft.")
                self._set_step(state, steps, 3, STEP_SUCCESS, "Neustart abgeschlossen.", 92, "Neustart abgeschlossen.")
                self._set_step(state, steps, 4, STEP_SUCCESS, f"{self.product_name()} wurde aktualisiert.", 100, "Update erfolgreich.")

                previous_version = str(current["app_version"])
                self._write_version({**current, "version": target_version, "app_version": target_version, "previous_version": previous_version, "updated_at": utc_now()})
                state.update({"previous_version": previous_version, "installed_version": target_version, "updated_at": utc_now(), "update_available": False, "backup": backup})
                state["install"] = {**state["install"], "status": "success", "state": "success", "finished_at": utc_now(), "command_results": command_results}
                self._write_state(state)
                self._audit("install", username, previous_version, target_version, "success", {"layers": layers, "backup": backup, "execution_mode": self.execution_mode()})
                if "system" in layers:
                    self._notify_reboot_hint()
                return self.public_status()
            except Exception as exc:
                self._mark_failed(state, steps, str(exc))
                self._audit("install", username, str(current.get("app_version")), target_version, "failed", {"error": str(exc), "layers": layers})
                raise

    def rollback(self, username: str = "admin") -> dict[str, Any]:
        with self._lock:
            state = self._read_state()
            current = self.current_version()
            previous_version = str(state.get("previous_version") or "").strip()
            if not previous_version and BackupEngine(self.paths).latest_backup() is None:
                raise RuntimeError("Kein Rollback-Ziel vorhanden.")
            steps = [
                {"key": "stop", "label": "Container stoppen", "status": STEP_PENDING},
                {"key": "restore", "label": "Backup wiederherstellen", "status": STEP_PENDING},
                {"key": "start", "label": "Container starten", "status": STEP_PENDING},
                {"key": "done", "label": "Rollback erfolgreich", "status": STEP_PENDING},
            ]
            state["rollback"] = {"status": "running", "state": "running", "target_version": previous_version, "steps": steps, "started_at": utc_now()}
            self._write_state(state)
            try:
                result = RollbackService(self.paths).rollback()
                for step in steps:
                    step["status"] = STEP_SUCCESS
                self._write_version({**current, "version": previous_version or current["app_version"], "app_version": previous_version or current["app_version"], "previous_version": current["app_version"], "updated_at": utc_now()})
                state["previous_version"] = current["app_version"]
                state["rollback"] = {"status": "success", "state": "success", "target_version": previous_version, "steps": steps, "finished_at": utc_now(), "result": result}
                self._write_state(state)
                self._audit("rollback", username, current["app_version"], previous_version, "success", {"result": result})
                return self.admin_status()
            except Exception as exc:
                for step in steps:
                    if step["status"] == STEP_PENDING:
                        step["status"] = STEP_FAILED
                        step["detail"] = str(exc)
                        break
                state["rollback"] = {"status": "failed", "state": "failed", "steps": steps, "finished_at": utc_now()}
                state["last_error"] = str(exc)
                self._write_state(state)
                self._audit("rollback", username, current["app_version"], previous_version, "failed", {"error": str(exc)})
                raise

    def create_backup(self, version: dict[str, Any]) -> Path:
        return Path(BackupEngine(self.paths).create_backup(version)["path"])

    def _initial_steps(self, target_version: str) -> list[dict[str, Any]]:
        return [
            {"key": "prepare", "label": "Vorbereitung", "status": STEP_PENDING, "detail": f"Version {target_version}"},
            {"key": "backup", "label": "Sicherung", "status": STEP_PENDING},
            {"key": "install", "label": "Installation", "status": STEP_PENDING},
            {"key": "restart", "label": "Neustart", "status": STEP_PENDING},
            {"key": "done", "label": "Fertig", "status": STEP_PENDING},
        ]

    def _public_steps(self, steps: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        source = steps or self._initial_steps("-")
        labels = ["Vorbereitung", "Sicherung", "Installation", "Neustart", "Fertig"]
        result: list[dict[str, Any]] = []
        for index, label in enumerate(labels):
            raw = source[index] if index < len(source) and isinstance(source[index], dict) else {}
            result.append({
                "key": ["prepare", "backup", "install", "restart", "done"][index],
                "label": label,
                "status": raw.get("status") or STEP_PENDING,
            })
        return result

    def _layers_for_latest(self, latest: dict[str, Any]) -> list[str]:
        components = latest.get("components") if isinstance(latest.get("components"), dict) else {}
        if components:
            return UpdateCheckService(self.paths)._layers_from_components(components)
        else:
            layers = [str(item) for item in latest.get("layers", []) if str(item) in UPDATE_LAYERS]
        return layers or ["application"]

    def _uses_application_zip(self, latest: dict[str, Any]) -> bool:
        download_url = str(latest.get("download_url") or "").strip()
        if not download_url or download_url.startswith(("manifest://", "mock://")):
            return False
        scheme = urllib.parse.urlparse(download_url).scheme
        return scheme in {"", "file", "https"}

    def _validate_latest_for_install(self, latest: dict[str, Any], current_version: str) -> None:
        product = str(latest.get("product") or "").strip().lower()
        if product and product not in {active_edition().name.lower(), self.product_name().lower()}:
            raise RuntimeError("Update-Manifest passt nicht zu dieser Installation.")
        minimum_version = str(latest.get("minimum_version") or "").strip()
        if minimum_version and compare_versions(current_version, minimum_version) < 0:
            raise RuntimeError("Diese Installation ist fuer ein Direktupdate zu alt. Bitte kontaktieren Sie den Support.")

    def product_name(self) -> str:
        edition_name = active_edition().name
        if edition_name == "seniorcare":
            return "SeniorCare"
        if edition_name == "personal":
            return "RoboterSteve"
        return active_edition().description or edition_name.title()

    def dev_mode_enabled(self) -> bool:
        return str(self._env("ROBOTERSTEVE_DEV_MODE") or "").strip().lower() in {"1", "true", "yes", "on"}

    def _public_message(self, status: str, update_available: bool) -> str:
        if status in {"running"}:
            return "Update wird installiert."
        if status in {"success", "completed"}:
            return f"{self.product_name()} wurde erfolgreich aktualisiert."
        if status in {"failed", "error"}:
            return "Das Update konnte nicht vollstaendig installiert werden. Bitte versuchen Sie es erneut oder kontaktieren Sie den Support."
        if update_available:
            return f"Eine neue Version von {self.product_name()} ist verfuegbar."
        return "Ihre Installation ist auf dem neuesten Stand."

    def _set_install_state(self, state: dict[str, Any], status: str, steps: list[dict[str, Any]], current_step: int, progress: int, message: str, target_version: str, layers: list[str]) -> None:
        state["install"] = {"status": status, "state": status, "target_version": target_version, "layers": layers, "steps": steps, "current_step": current_step, "progress": progress, "message": message, "started_at": state.get("install", {}).get("started_at") or utc_now()}
        self._write_state(state)

    def _set_step(self, state: dict[str, Any], steps: list[dict[str, Any]], index: int, status: str, detail: str, progress: int, message: str) -> None:
        steps[index]["status"] = status
        steps[index]["detail"] = detail
        state["install"] = {**state.get("install", {}), "status": "running" if progress < 100 else "success", "state": "running" if progress < 100 else "success", "steps": steps, "current_step": index + 1, "progress": progress, "message": message}
        self._write_state(state)

    def _mark_failed(self, state: dict[str, Any], steps: list[dict[str, Any]], error: str) -> None:
        for step in steps:
            if step["status"] in {STEP_PENDING, STEP_RUNNING}:
                step["status"] = STEP_FAILED
                step["detail"] = error
                break
        state["install"] = {**state.get("install", {}), "status": "failed", "state": "failed", "steps": steps, "message": error, "finished_at": utc_now()}
        state["last_error"] = error
        self._write_state(state)

    def _commands_detail(self) -> str:
        return "Kommandos im Hintergrund gestartet." if self.execution_mode() == "docker" else "Dry-Run: Kommandos nicht ausgefuehrt."

    def _read_state(self) -> dict[str, Any]:
        return self._read_json(self.paths.state_file, {"install": {"status": "idle", "state": "idle", "steps": self._initial_steps("-"), "progress": 0, "current_step": 0}})

    def _write_state(self, state: dict[str, Any]) -> None:
        self._write_json(self.paths.state_file, state)

    def _write_version(self, data: dict[str, Any]) -> None:
        self.paths.version_file.parent.mkdir(parents=True, exist_ok=True)
        self.paths.version_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _notify_update_available(self, latest: dict[str, Any]) -> None:
        from backend.services.messaging import MessagingService

        MessagingService().create_message(
            source="system",
            category="updates",
            severity="warning" if latest.get("mandatory") else "info",
            title="Update verfuegbar",
            message=f"Version {latest.get('latest_version')} ist verfuegbar.",
            payload={"source": "update_service", "latest": latest},
        )

    def _notify_reboot_hint(self) -> None:
        from backend.services.messaging import MessagingService

        MessagingService().create_message(
            source="system",
            category="updates",
            severity="warning",
            title="Neustart pruefen",
            message="System-Updates wurden angestossen. Bitte pruefen, ob ein Debian-Neustart notwendig ist.",
            payload={"source": "update_service", "reboot_required": True},
        )

    def _audit(self, action: str, username: str, from_version: str, to_version: str, result: str, payload: dict[str, Any]) -> None:
        self.paths.audit_log.parent.mkdir(parents=True, exist_ok=True)
        entry = {"timestamp": utc_now(), "user": username, "edition": active_edition().name, "action": action, "from_version": from_version, "to_version": to_version, "result": result, "payload": payload}
        with self.paths.audit_log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        try:
            self.paths.audit_log.chmod(0o600)
        except OSError:
            pass


def compare_versions(left: str, right: str) -> int:
    def parts(value: str) -> list[int]:
        cleaned = value.split("-", 1)[0]
        result = []
        for part in cleaned.split("."):
            try:
                result.append(int(part))
            except ValueError:
                result.append(0)
        return result

    left_parts = parts(left)
    right_parts = parts(right)
    max_len = max(len(left_parts), len(right_parts))
    left_parts.extend([0] * (max_len - len(left_parts)))
    right_parts.extend([0] * (max_len - len(right_parts)))
    return (left_parts > right_parts) - (left_parts < right_parts)


def _shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def _human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"
