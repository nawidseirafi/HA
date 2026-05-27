import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI

from backend.paths import BACKEND_DIR


AGENTS_DIR = BACKEND_DIR / "agents"


@dataclass(frozen=True)
class AgentManifest:
    id: str
    name: str
    description: str
    icon: str
    enabled: bool
    status: str
    dashboard_route: str | None
    api_prefix: str
    route_module: str | None
    service_object: str | None
    settings: dict[str, Any]
    source_path: Path

    def public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "icon": self.icon,
            "enabled": self.enabled,
            "status": self.status,
            "dashboard_route": self.dashboard_route,
            "api_prefix": self.api_prefix,
            "settings": self.settings,
        }


def discover_agent_manifests() -> list[AgentManifest]:
    manifests = []
    for path in sorted(AGENTS_DIR.glob("*/manifest.yaml")):
        manifest = _load_manifest(path)
        if manifest:
            manifests.append(manifest)
    return manifests


def include_agent_routers(app: FastAPI) -> None:
    for manifest in discover_agent_manifests():
        if not manifest.enabled or not manifest.route_module:
            continue
        module = importlib.import_module(manifest.route_module)
        router = getattr(module, "router", None)
        if router is not None:
            app.include_router(router)


def agent_runtime_services() -> list[Any]:
    services = []
    for manifest in discover_agent_manifests():
        if not manifest.enabled or not manifest.route_module or not manifest.service_object:
            continue
        module = importlib.import_module(manifest.route_module)
        service = getattr(module, manifest.service_object, None)
        if service is not None:
            services.append(service)
    return services


def _load_manifest(path: Path) -> AgentManifest | None:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return None
    agent_id = str(data.get("id") or path.parent.name).strip()
    if not agent_id:
        return None
    ui = data.get("ui") or {}
    api = data.get("api") or {}
    runtime = data.get("runtime") or {}
    return AgentManifest(
        id=agent_id,
        name=str(data.get("name") or agent_id),
        description=str(data.get("description") or ""),
        icon=str(ui.get("icon") or "Bot"),
        enabled=bool(data.get("enabled", True)),
        status=str(data.get("status") or "active"),
        dashboard_route=ui.get("dashboard_route"),
        api_prefix=str(api.get("prefix") or ""),
        route_module=api.get("route_module"),
        service_object=runtime.get("service_object"),
        settings=data.get("settings") or {},
        source_path=path,
    )
