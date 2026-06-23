#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import hashlib


ROOT = Path(__file__).resolve().parent
BUILD_DIR = ROOT / "build"
TARGET_DIR = BUILD_DIR / "robotersteve"
UPDATE_DIR = BUILD_DIR / "updates" / "robotersteve" / "stable"
RELEASE_DIR = UPDATE_DIR / "releases"
FRONTEND_DIR = ROOT / "frontend"

COPY_ITEMS = [
    "backend",
    "frontend/dist",
    "requirements.txt",
    "agent-api.service",
    "main.py",
    "version.json",
]

NEVER_COPY_NAMES = {
    ".DS_Store",
    ".env",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    "data",
    "logs",
    "build",
}

NEVER_COPY_SUFFIXES = {".pyc", ".pyo", ".db", ".db-shm", ".db-wal", ".sqlite", ".sqlite3"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Build RoboterSteve deployment artifacts")
    parser.add_argument("--version", default="", help="Override version.json version")
    parser.add_argument("--base-url", default=os.environ.get("ROBOTERSTEVE_UPDATE_BASE_URL", ""), help="Public base URL for generated update manifest")
    parser.add_argument("--no-zip", action="store_true", help="Only create build/robotersteve without update ZIP artifacts")
    parser.add_argument("--skip-frontend-build", action="store_true", help="Reuse frontend/dist instead of running npm run build")
    args = parser.parse_args()

    version = args.version.strip() or current_version()
    clean_build_dir()
    build_frontend(skip=args.skip_frontend_build)
    copy_deployment_tree(version)
    write_readme()
    write_config_example()
    write_env_example()
    write_readme_install()
    if not args.no_zip:
        create_update_artifacts(version=version, base_url=args.base_url.strip())
    else:
        write_update_manifest(version=version, base_url=args.base_url.strip())

    print(f"Built RoboterSteve deployment in {TARGET_DIR}")
    if not args.no_zip:
        print(f"Update artifacts in {UPDATE_DIR}")
    return 0

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def clean_build_dir() -> None:
    if TARGET_DIR.exists():
        shutil.rmtree(TARGET_DIR)
    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)


def build_frontend(skip: bool = False) -> None:
    dist = FRONTEND_DIR / "dist"
    if skip:
        if not dist.exists():
            raise SystemExit("frontend/dist does not exist. Run without --skip-frontend-build first.")
        return
    try:
        subprocess.run(["npm", "run", "build"], cwd=FRONTEND_DIR, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        if dist.exists():
            print(f"Warning: frontend build failed, reusing existing dist: {exc}", file=sys.stderr)
            return
        raise SystemExit(f"Frontend build failed and no existing frontend/dist is available: {exc}") from exc


def copy_deployment_tree(version: str) -> None:
    for item in COPY_ITEMS:
        source = ROOT / item
        if not source.exists():
            continue
        copy_path(source, TARGET_DIR / item)
    write_version_file(TARGET_DIR / "version.json", version)
    ensure_runtime_dirs(TARGET_DIR)


def copy_path(source: Path, target: Path) -> None:
    if should_skip(source):
        return
    if source.is_dir():
        shutil.copytree(source, target, ignore=copy_ignore)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def copy_ignore(directory: str, names: list[str]) -> set[str]:
    ignored: set[str] = set()
    for name in names:
        path = Path(directory) / name
        if name in NEVER_COPY_NAMES or path.suffix in NEVER_COPY_SUFFIXES:
            ignored.add(name)
    return ignored


def should_skip(path: Path) -> bool:
    return path.name in NEVER_COPY_NAMES or path.suffix in NEVER_COPY_SUFFIXES


def ensure_runtime_dirs(target: Path) -> None:
    for directory in ("data", "logs", "backups"):
        path = target / directory
        path.mkdir(parents=True, exist_ok=True)
        (path / ".gitkeep").write_text("", encoding="utf-8")


def write_config_example() -> None:
    config = {
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
            "llama": {"base_url": "http://localhost:11434", "model": "qwen2.5:3b"},
        },
        "messaging": {"enabled": True},
        "updates": {
            "channel": "stable",
            "manifest_url": "UPDATE_MANIFEST_URL",
            "manifest_path": "update-manifest.json",
            "execution_mode": "local_systemd",
            "systemd_service": "agent-api",
            "backup_dir": "./backups",
        },
    }
    try:
        import yaml

        content = yaml.safe_dump(config, sort_keys=False, allow_unicode=True)
    except Exception:
        content = json.dumps(config, ensure_ascii=False, indent=2)
    (TARGET_DIR / "config.example.yaml").write_text(content, encoding="utf-8")


def write_env_example() -> None:
    (TARGET_DIR / ".env.example").write_text(
        "\n".join(
            [
                "AGENT_API_USERNAME=admin",
                "AGENT_API_PASSWORD=change-me",
                "AGENT_API_JWT_SECRET=change-me-long-random-secret",
                "HA_URL=",
                "HA_TOKEN=",
                "OPENAI_API_KEY=",
                "UPDATE_MANIFEST_URL=",
                "UPDATE_EXECUTION_MODE=local_systemd",
                "UPDATE_SYSTEMD_SERVICE=agent-api",
                "ROBOTERSTEVE_BACKUP_DIR=./backups",
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_readme() -> None:
    (TARGET_DIR / "README.md").write_text(
        """# RoboterSteve

Standalone deployment package for RoboterSteve.

This package is built as a single RoboterSteve product.

## Contents

- `backend/`: FastAPI backend
- `frontend/dist/`: built frontend
- `requirements.txt`: Python dependencies
- `config.example.yaml`: configuration template
- `.env.example`: environment template
- `README_INSTALL.md`: installation notes
""",
        encoding="utf-8",
    )


def write_readme_install() -> None:
    (TARGET_DIR / "README_INSTALL.md").write_text(
        """# RoboterSteve Installation

1. Copy `.env.example` to `.env` and adjust credentials.
2. Copy `config.example.yaml` to `config.yaml` and adjust integrations.
3. Install dependencies:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

4. Start:

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8080
```

Runtime data stays in `data/`, `logs/` and `backups/`; those folders are not part of update ZIP payloads.
""",
        encoding="utf-8",
    )


def write_version_file(path: Path, version: str) -> None:
    data = read_json(ROOT / "version.json", {})
    data["version"] = version
    data["app_version"] = version
    data["build"] = data.get("build") or datetime.now(timezone.utc).strftime("%Y.%m.%d")
    data["commit"] = data.get("commit") or git_commit()
    data["updated_at"] = utc_now()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def create_update_artifacts(version: str, base_url: str) -> None:
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = RELEASE_DIR / f"robotersteve-{version}.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(TARGET_DIR.rglob("*")):
            if should_skip(path):
                continue
            rel = path.relative_to(TARGET_DIR)
            if any(part in NEVER_COPY_NAMES for part in rel.parts):
                continue
            if path.is_file():
                archive.write(path, Path(f"robotersteve-{version}") / rel)

    latest = latest_manifest(version=version, zip_path=zip_path, base_url=base_url)
    (UPDATE_DIR / "latest.json").write_text(json.dumps(latest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (UPDATE_DIR / "deployment-manifest.json").write_text(
        json.dumps(
            {
                "product": "robotersteve",
                "version": version,
                "created_at": utc_now(),
                "artifact": str(zip_path.relative_to(BUILD_DIR)),
                "target": str(TARGET_DIR.relative_to(BUILD_DIR)),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def write_update_manifest(version: str, base_url: str) -> None:
    (TARGET_DIR / "update-manifest.json").write_text(
        json.dumps(latest_manifest(version=version, zip_path=RELEASE_DIR / f"robotersteve-{version}.zip", base_url=base_url), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def latest_manifest(version: str, zip_path: Path, base_url: str) -> dict[str, Any]:
    filename = zip_path.name
    download_url = f"{base_url.rstrip('/')}/stable/releases/{filename}" if base_url else str(zip_path)
    sha256 = sha256_file(zip_path) if zip_path.exists() else ""

    return {
        "latest_version": version,
        "download_url": download_url,
        "mandatory": False,
        "minimum_version": "0.1.0",
        "sha256": sha256,
        "release_notes": [f"RoboterSteve {version} deployment build."],
        "components": {
            "application": {"update": True},
            "homeassistant": {"update": False},
            "ollama": {"update": False},
            "system": {"update": False},
        },
        "channels": {
            "stable": {
                "latest_version": version,
                "download_url": download_url,
                "mandatory": False,
                "sha256": sha256,
                "release_notes": [f"RoboterSteve {version} deployment build."],
                "layers": ["application"],
            }
        },
    }


def current_version() -> str:
    return str(read_json(ROOT / "version.json", {}).get("version") or "0.1.0")


def read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(default)
    return data if isinstance(data, dict) else dict(default)


def git_commit() -> str:
    try:
        result = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, check=True, text=True, capture_output=True)
        return result.stdout.strip() or "unknown"
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


if __name__ == "__main__":
    raise SystemExit(main())
