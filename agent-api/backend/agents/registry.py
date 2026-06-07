import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI

from backend.agents.control import AgentControlAdapter, BaseAgentControl
from backend.config import load_agent_section
from backend.editions import active_edition, load_edition
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


def discover_agent_manifests(edition_filter: tuple[str, ...] | set[str] | list[str] | None = None) -> list[AgentManifest]:
    if edition_filter is None:
        edition_filter = active_edition().enabled_agents
    return _discover_agent_manifests(edition_filter=edition_filter)


def discover_all_agent_manifests() -> list[AgentManifest]:
    return _discover_agent_manifests(edition_filter=None)


def discover_agent_manifests_for_edition(edition_name: str) -> list[AgentManifest]:
    return _discover_agent_manifests(edition_filter=load_edition(edition_name).enabled_agents)


def _discover_agent_manifests(edition_filter: tuple[str, ...] | set[str] | list[str] | None = None) -> list[AgentManifest]:
    allowed = set(edition_filter) if edition_filter is not None else None
    manifests = []
    for path in sorted(AGENTS_DIR.glob("*/manifest.yaml")):
        manifest = _load_manifest(path)
        if manifest and (allowed is None or manifest.id in allowed):
            manifests.append(manifest)
    return manifests


def include_agent_routers(app: FastAPI) -> None:
    for manifest in discover_agent_manifests():
        if not manifest.route_module:
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


def get_agent_control(agent_id: str) -> BaseAgentControl | None:
    manifest = next((item for item in discover_agent_manifests() if item.id == agent_id), None)
    if not manifest or not manifest.route_module or not manifest.service_object:
        return None
    module = importlib.import_module(manifest.route_module)
    service = getattr(module, manifest.service_object, None)
    if service is None:
        return None
    return AgentControlAdapter(agent_id=manifest.id, service=service)


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
        enabled=_agent_enabled(agent_id),
        status=str(data.get("status") or "active"),
        dashboard_route=ui.get("dashboard_route"),
        api_prefix=str(api.get("prefix") or ""),
        route_module=api.get("route_module"),
        service_object=runtime.get("service_object"),
        settings=data.get("settings") or {},
        source_path=path,
    )


def _agent_enabled(agent_id: str) -> bool:
    config = load_agent_section(agent_id)
    return bool(config.get("enabled", True))
