#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


API_DIR = Path(__file__).resolve().parents[1]
BUILD_DIR = API_DIR / "build"
BACKEND_DIR = API_DIR / "backend"
FRONTEND_DIR = API_DIR / "frontend"
EDITIONS_DIR = API_DIR / "editions"

NEVER_COPY_NAMES = {
    ".DS_Store",
    ".env",
    "__pycache__",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "logs",
    "data",
}
NEVER_COPY_SUFFIXES = {".db", ".sqlite", ".sqlite3", ".pyc", ".pyo"}

CORE_API_ROUTES = {
    "auth": ["backend/api/auth_routes.py"],
    "system": ["backend/api/system_routes.py"],
    "settings": ["backend/api/settings_routes.py"],
    "orchestrator": ["backend/api/orchestrator_routes.py"],
    "homeassistant": ["backend/api/homeassistant_routes.py"],
    "household": ["backend/api/household_routes.py"],
    "infrastructure": ["backend/api/infrastructure_routes.py"],
    "waste": ["backend/api/waste_routes.py"],
}

CORE_SERVICE_FILES = {
    "auth": ["backend/services/auth_service.py"],
    "system": ["backend/services/update_service.py"],
    "settings": ["backend/services/settings_service.py"],
    "orchestrator": ["backend/services/orchestrator_control_service.py"],
    "homeassistant": ["backend/services/homeassistant_service.py", "backend/services/core"],
    "household": ["backend/services/household_service.py", "backend/services/waste_service.py"],
    "infrastructure": ["backend/services/infrastructure_service.py", "backend/services/infrastructure_store.py"],
    "waste": ["backend/services/waste_service.py"],
    "messaging": ["backend/services/messaging"],
    "llm": ["backend/services/llm"],
}

ALWAYS_BACKEND_FILES = [
    "backend/__init__.py",
    "backend/main.py",
    "backend/config.py",
    "backend/editions.py",
    "backend/paths.py",
    "backend/logging_config.py",
    "backend/api/__init__.py",
    "backend/agents/__init__.py",
    "backend/agents/control.py",
    "backend/agents/registry.py",
    "backend/agents/routes.py",
    "backend/services/__init__.py",
]


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python tools/build_edition.py <edition>", file=sys.stderr)
        return 2

    edition_name = sys.argv[1].strip()
    edition = load_edition(edition_name)
    target = BUILD_DIR / edition_name

    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)

    copy_backend(edition, target)
    copy_requirements(target)
    copy_version_file(target)
    copy_update_manifest(target)
    copy_edition_files(edition_name, target)
    build_or_copy_frontend(edition, target)
    write_config_example(edition, target)
    write_env_example(edition, target)
    write_docker_compose(edition, target)
    write_readme(edition, target)
    create_release_artifacts(edition, target)

    print(f"Built edition '{edition_name}' in {target}")
    return 0


def load_edition(name: str) -> dict[str, Any]:
    path = EDITIONS_DIR / f"{name}.yaml"
    if not path.exists():
        raise SystemExit(f"Edition not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise SystemExit(f"Invalid edition config: {path}")
    data.setdefault("name", name)
    data.setdefault("enabled_agents", [])
    data.setdefault("enabled_core_services", [])
    data.setdefault("include_frontend", True)
    data.setdefault("include_data", False)
    return data


def copy_backend(edition: dict[str, Any], target: Path) -> None:
    for rel in ALWAYS_BACKEND_FILES:
        copy_path(API_DIR / rel, target / rel)

    core_services = set(string_list(edition.get("enabled_core_services")))
    for service_id in sorted(core_services):
        for rel in CORE_API_ROUTES.get(service_id, []):
            copy_path(API_DIR / rel, target / rel)
        for rel in CORE_SERVICE_FILES.get(service_id, []):
            copy_path(API_DIR / rel, target / rel)

    for agent_id in string_list(edition.get("enabled_agents")):
        source = BACKEND_DIR / "agents" / agent_id
        if not source.exists():
            print(f"Warning: agent '{agent_id}' does not exist at {source}", file=sys.stderr)
            continue
        copy_path(source, target / "backend" / "agents" / agent_id)

    for rel in string_list(edition.get("include_files")):
        copy_path(API_DIR / rel, target / rel)


def copy_requirements(target: Path) -> None:
    copy_path(API_DIR / "requirements.txt", target / "requirements.txt")
    copy_path(API_DIR / "UPDATE_SYSTEM.md", target / "UPDATE_SYSTEM.md")


def copy_version_file(target: Path) -> None:
    copy_path(API_DIR / "version.json", target / "version.json")


def copy_update_manifest(target: Path) -> None:
    copy_path(API_DIR / "update-manifest.json", target / "update-manifest.json")


def copy_edition_files(edition_name: str, target: Path) -> None:
    copy_path(EDITIONS_DIR / f"{edition_name}.yaml", target / "editions" / f"{edition_name}.yaml")
    (target / "editions").mkdir(parents=True, exist_ok=True)
    (target / "editions" / "edition.lock").write_text(f"{edition_name}\n", encoding="utf-8")


def build_or_copy_frontend(edition: dict[str, Any], target: Path) -> None:
    if not bool(edition.get("include_frontend", True)):
        return
    dist_target = target / "frontend" / "dist"
    frontend_app = str(edition.get("frontend_app") or edition.get("name") or "personal")
    env = os.environ.copy()
    env["VITE_ROBOTERSTEVE_EDITION"] = frontend_app
    try:
        subprocess.run(["npm", "run", "build"], cwd=FRONTEND_DIR, env=env, check=True)
        copy_frontend_dist(FRONTEND_DIR / "dist", dist_target)
    except (OSError, subprocess.CalledProcessError) as exc:
        existing_dist = FRONTEND_DIR / "dist"
        if not existing_dist.exists():
            raise SystemExit(f"Frontend build failed and no existing dist is available: {exc}") from exc
        print(f"Warning: frontend build failed, copying existing dist: {exc}", file=sys.stderr)
        copy_frontend_dist(existing_dist, dist_target)


def write_config_example(edition: dict[str, Any], target: Path) -> None:
    name = str(edition.get("name") or "personal")
    if name == "seniorcare":
        config = seniorcare_config_example()
    else:
        config = personal_config_example()
    config["edition"] = {
        "name": name,
        "description": str(edition.get("description") or ""),
    }
    (target / "config.example.yaml").write_text(yaml.safe_dump(config, sort_keys=False, allow_unicode=True), encoding="utf-8")


def personal_config_example() -> dict[str, Any]:
    return {
        "server": {"host": "0.0.0.0", "port": 8080},
        "logging": {"file": "./logs/agent-api.log", "level": "INFO"},
        "auth": {
            "username_env": "AGENT_API_USERNAME",
            "password_env": "AGENT_API_PASSWORD",
            "jwt_secret_env": "AGENT_API_JWT_SECRET",
            "token_ttl_seconds": 604800,
        },
        "home_assistant": {"url": "HA_URL", "token": "HA_TOKEN"},
        "llm": {
            "provider": "openai",
            "openai": {"api_key": "OPENAI_API_KEY", "model": "gpt-4.1-mini"},
            "llama": {"base_url": "http://ollama:11434", "model": "qwen2.5:3b"},
        },
        "messaging": {"enabled": True},
        "updates": {
            "channel": "stable",
            "server_url": "UPDATE_SERVER_URL",
            "manifest_url": "UPDATE_MANIFEST_URL",
            "manifest_path": "update-manifest.json",
            "execution_mode": "dry_run",
            "backup_dir": "/opt/roboterSteve/backups",
            "services": {
                "api": "robotersteve-api",
                "ollama": "ollama",
                "homeassistant": "homeassistant",
            },
            "ollama_models": [],
            "mock_latest": {
                "latest_version": "0.1.0",
                "mandatory": False,
                "release_notes": ["Lokaler Mock-Update-Server."],
            },
        },
        "infrastructure": {"enabled": True, "database_path": "data/infrastructure/infrastructure.db"},
    }


def seniorcare_config_example() -> dict[str, Any]:
    return {
        "server": {"host": "0.0.0.0", "port": 8080},
        "logging": {"file": "./logs/agent-api.log", "level": "INFO"},
        "auth": {
            "username_env": "AGENT_API_USERNAME",
            "password_env": "AGENT_API_PASSWORD",
            "jwt_secret_env": "AGENT_API_JWT_SECRET",
            "token_ttl_seconds": 604800,
        },
        "home_assistant": {"url": "HA_URL", "token": "HA_TOKEN"},
        "llm": {
            "provider": "llama",
            "llama": {"base_url": "http://ollama:11434", "model": "qwen2.5:3b"},
        },
        "messaging": {"enabled": True},
        "updates": {
            "channel": "stable",
            "server_url": "UPDATE_SERVER_URL",
            "manifest_url": "UPDATE_MANIFEST_URL",
            "manifest_path": "update-manifest.json",
            "execution_mode": "dry_run",
            "backup_dir": "/opt/roboterSteve/backups",
            "services": {
                "api": "robotersteve-api",
                "ollama": "ollama",
                "homeassistant": "homeassistant",
            },
            "ollama_models": ["qwen2.5:3b"],
            "mock_latest": {
                "latest_version": "0.1.0",
                "mandatory": False,
                "release_notes": ["Lokaler Mock-Update-Server."],
            },
        },
        "scheduler": {"enabled": True},
        "senior": {"enabled": True, "mode": "placeholder"},
    }


def write_env_example(edition: dict[str, Any], target: Path) -> None:
    lines = [
        f"ROBOTERSTEVE_EDITION={edition.get('name')}",
        "ROBOTERSTEVE_VERSION=0.1.0",
        "ROBOTERSTEVE_BUILD=2026.06.08",
        "ROBOTERSTEVE_COMMIT=development",
        "AGENT_API_USERNAME=admin",
        "AGENT_API_PASSWORD=change-me",
        "AGENT_API_JWT_SECRET=change-me-long-random-secret",
        "HA_URL=http://homeassistant.local:8123",
        "HA_TOKEN=replace-with-token",
        "OPENAI_API_KEY=",
        "GEMINI_API_KEY=",
        "UPDATE_SERVER_URL=",
        "UPDATE_MANIFEST_URL=",
        "UPDATE_MANIFEST_PATH=update-manifest.json",
        "UPDATE_CHANNEL=stable",
        "UPDATE_EXECUTION_MODE=dry_run",
        "ROBOTERSTEVE_BACKUP_DIR=/opt/roboterSteve/backups",
        "OLLAMA_UPDATE_MODELS=",
    ]
    (target / ".env.example").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_docker_compose(edition: dict[str, Any], target: Path) -> None:
    name = str(edition.get("name") or "personal")
    if name == "personal":
        compose_path = target / "docker-compose.yml"
        if compose_path.exists():
            compose_path.unlink()
        return

    services: dict[str, Any] = {
        "robotersteve-api": {
            "image": "python:3.12-slim",
            "working_dir": "/app",
            "volumes": [".:/app", "/var/run/docker.sock:/var/run/docker.sock"],
            "env_file": [".env"],
            "environment": {"UPDATE_EXECUTION_MODE": "docker"},
            "command": "sh -c \"apt-get update && apt-get install -y docker.io docker-compose && pip install -r requirements.txt && uvicorn backend.main:app --host 0.0.0.0 --port 8080\"",
            "ports": ["8080:8080"],
        }
    }
    if name == "seniorcare":
        services["ollama"] = {
            "image": "ollama/ollama:latest",
            "ports": ["11434:11434"],
            "volumes": ["ollama:/root/.ollama"],
        }
    compose: dict[str, Any] = {"services": services}
    if name == "seniorcare":
        compose["volumes"] = {"ollama": None}
    (target / "docker-compose.yml").write_text(yaml.safe_dump(compose, sort_keys=False), encoding="utf-8")


def write_readme(edition: dict[str, Any], target: Path) -> None:
    name = str(edition.get("name") or "personal")
    agents = ", ".join(string_list(edition.get("enabled_agents"))) or "none"
    if name == "personal":
        install_section = """## Installation
1. `.env.example` nach `.env` kopieren und Werte setzen.
2. `config.example.yaml` nach `config.yaml` kopieren und anpassen.
3. Virtuelle Umgebung erstellen und aktivieren.
4. Abhaengigkeiten installieren:
   ```bash
   pip install -r requirements.txt
   ```
5. Backend starten:
   ```bash
   ROBOTERSTEVE_EDITION=personal uvicorn backend.main:app --host 0.0.0.0 --port 8080
   ```

## Pruefung
Nach dem Kopieren muessen `backend/`, `frontend/`, `editions/`, `config.yaml` und `.env` im Deployment-Root liegen.

```bash
python - <<'PY'
from backend.editions import active_edition
from backend.main import app
print(active_edition().public_dict())
print('/api/auth/login' in [getattr(route, 'path', '') for route in app.routes])
PY
```

Wenn `/docs` nur `/health` und `/api/agents` zeigt, fehlt sehr wahrscheinlich `editions/personal.yaml` im Deployment oder es laeuft nicht der neu gebaute Personal-Stand.

## Deployment-Hinweis
Diese Personal Edition ist fuer ein normales Python/systemd-Deployment vorgesehen. Es wird bewusst keine `docker-compose.yml` erzeugt.
"""
    else:
        install_section = """## Installation
1. `.env.example` nach `.env` kopieren und Werte setzen.
2. `config.example.yaml` nach `config.yaml` kopieren und anpassen.
3. `pip install -r requirements.txt`
4. `uvicorn backend.main:app --host 0.0.0.0 --port 8080`

## Docker Compose
```bash
docker compose up
```
"""

    text = f"""# RoboterSteve {name} Edition

## Inhalt
- Agenten: {agents}
- Frontend: {'enthalten' if edition.get('include_frontend', True) else 'nicht enthalten'}
- Private Daten, Logs und Datenbanken sind nicht enthalten.

{install_section}
"""
    (target / "README_INSTALL.md").write_text(text, encoding="utf-8")


def create_release_artifacts(edition: dict[str, Any], target: Path) -> None:
    name = str(edition.get("name") or target.name)
    version = read_version_metadata().get("version", "0.1.0")
    release_dir = BUILD_DIR / "releases" / name
    release_dir.mkdir(parents=True, exist_ok=True)
    zip_name = f"{name}-{version}.zip"
    zip_path = release_dir / zip_name
    embedded_manifest = deployment_manifest(edition, target, version, zip_name, include_artifact=False)
    (target / "deployment-manifest.json").write_text(json.dumps(embedded_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if zip_path.exists():
        zip_path.unlink()
    zip_directory(target, zip_path, root_name=f"{name}-{version}")
    sha256 = sha256_file(zip_path)
    size_bytes = zip_path.stat().st_size

    external_manifest = deployment_manifest(
        edition,
        target,
        version,
        zip_name,
        include_artifact=True,
        sha256=sha256,
        size_bytes=size_bytes,
        download_url=release_download_url(name, version, zip_name),
    )
    latest_manifest = update_latest_manifest(name, version, external_manifest)
    (release_dir / "deployment-manifest.json").write_text(json.dumps(external_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (release_dir / "latest.json").write_text(json.dumps(latest_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (target / "deployment-manifest.json").write_text(json.dumps(external_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Release ZIP: {zip_path}")
    print(f"Update manifest: {release_dir / 'latest.json'}")


def read_version_metadata() -> dict[str, Any]:
    path = API_DIR / "version.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": "0.1.0", "build": datetime.now(timezone.utc).strftime("%Y.%m.%d"), "commit": "development"}
    return data if isinstance(data, dict) else {"version": "0.1.0"}


def deployment_manifest(
    edition: dict[str, Any],
    target: Path,
    version: str,
    zip_name: str,
    include_artifact: bool,
    sha256: str = "",
    size_bytes: int = 0,
    download_url: str = "",
) -> dict[str, Any]:
    version_info = read_version_metadata()
    name = str(edition.get("name") or target.name)
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "manifest_type": "robotersteve-deployment",
        "product": name,
        "edition": name,
        "description": str(edition.get("description") or ""),
        "version": version,
        "build": str(version_info.get("build") or ""),
        "commit": str(version_info.get("commit") or ""),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "frontend_app": str(edition.get("frontend_app") or name),
        "enabled_agents": string_list(edition.get("enabled_agents")),
        "enabled_core_services": string_list(edition.get("enabled_core_services")),
        "include_frontend": bool(edition.get("include_frontend", True)),
        "include_data": False,
        "install": {
            "root": "/opt/roboterSteve",
            "python_entrypoint": "backend.main:app",
            "port": 8080,
            "service_name": "agent-api.service",
        },
        "excluded": sorted(NEVER_COPY_NAMES),
    }
    if include_artifact:
        manifest["artifact"] = {
            "file": zip_name,
            "download_url": download_url,
            "sha256": sha256,
            "size_bytes": size_bytes,
        }
    return manifest


def update_latest_manifest(edition_name: str, version: str, deployment: dict[str, Any]) -> dict[str, Any]:
    artifact = deployment["artifact"]
    return {
        "schema_version": 1,
        "product": edition_name,
        "latest_version": version,
        "download_url": artifact["download_url"],
        "sha256": artifact["sha256"],
        "size_bytes": artifact["size_bytes"],
        "mandatory": False,
        "minimum_version": "0.1.0",
        "release_notes": [
            f"{edition_name} {version} Release.",
            "Application-Paket fuer Update Engine V1.",
        ],
        "components": {
            "application": {"update": True},
            "homeassistant": {"update": False},
            "ollama": {"update": False},
            "system": {"update": False},
        },
        "deployment_manifest": "deployment-manifest.json",
    }


def release_download_url(edition_name: str, version: str, zip_name: str) -> str:
    base = os.environ.get("UPDATE_RELEASE_BASE_URL", "").strip()
    if base:
        return f"{base.rstrip('/')}/{zip_name}"
    return f"https://seirafi.de/robotersteve/{edition_name}/stable/releases/{zip_name}"


def zip_directory(source: Path, target: Path, root_name: str) -> None:
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source.rglob("*")):
            if not path.is_file() or should_skip(path):
                continue
            relative = path.relative_to(source)
            archive.write(path, f"{root_name}/{relative.as_posix()}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def copy_path(source: Path, target: Path) -> None:
    if not source.exists() or should_skip(source):
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, target, ignore=ignore_names, dirs_exist_ok=True)
    else:
        shutil.copy2(source, target)


def copy_frontend_dist(source: Path, target: Path) -> None:
    if not source.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target, ignore=ignore_names, dirs_exist_ok=True)


def ignore_names(_dir: str, names: list[str]) -> set[str]:
    ignored = set()
    for name in names:
        path = Path(name)
        if name in NEVER_COPY_NAMES or path.suffix in NEVER_COPY_SUFFIXES:
            ignored.add(name)
    return ignored


def should_skip(path: Path) -> bool:
    return path.name in NEVER_COPY_NAMES or path.suffix in NEVER_COPY_SUFFIXES


def string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


if __name__ == "__main__":
    raise SystemExit(main())
