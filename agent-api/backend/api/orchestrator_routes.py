from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from backend.agents.registry import discover_agent_manifests, get_agent_control
from backend.product import active_product, is_core_service_enabled
from backend.services.homeassistant_service import HomeAssistantService
from backend.services.orchestrator_control_service import OrchestratorControlService


router = APIRouter(prefix="/api/orchestrator", tags=["orchestrator"])
control_service = OrchestratorControlService()


class ControlPayload(BaseModel):
    action: str | None = None
    mode: str | None = None
    dry_run: bool | None = None

    class Config:
        extra = "allow"


@router.get("/map")
def orchestrator_map(live: bool = Query(default=False)) -> dict[str, Any]:
    agents = [_agent_node(manifest.public_dict(), live=live) for manifest in discover_agent_manifests()]
    agent_ids = {agent["id"] for agent in agents}
    services = _service_nodes(live=live)
    scheduler = next((agent for agent in agents if agent["id"] == "scheduler"), None)
    nodes = [
        {
            "id": "orchestrator",
            "label": "RoboterSteve",
            "subtitle": "Orchestrator",
            "kind": "orchestrator",
            "status": "running" if any(agent["status"] == "running" for agent in agents) else "active",
            "icon": "Bot",
            "control": _read_only_control(),
        },
        *agents,
        *services,
    ]
    primary_edges = _primary_edges(agents, services, scheduler)
    edges = [
        *primary_edges,
        *[
            {
                "id": f"{agent_id}-database",
                "from": agent_id,
                "to": "database",
                "kind": "secondary",
                "active": _is_active(agent["status"]),
                "status": agent["status"],
            }
            for agent in agents
            for agent_id in [agent["id"]]
            if agent_id in {"invoices", "mywellness", "market", "vacation", "garden", "telegram"}
        ],
        *[
            {
                "id": f"{agent_id}-openai",
                "from": agent_id,
                "to": "openai",
                "kind": "secondary",
                "active": _is_active(agent["status"]),
                "status": agent["status"],
            }
            for agent in agents
            for agent_id in [agent["id"]]
            if agent_id in {"invoices", "mywellness", "market", "garden", "telegram"}
        ],
    ]
    if "telegram" in agent_ids:
        telegram = next(agent for agent in agents if agent["id"] == "telegram")
        if "homeassistant" in {service["id"] for service in services}:
            edges.append({
                "id": "telegram-homeassistant",
                "from": "telegram",
                "to": "homeassistant",
                "kind": "secondary",
                "active": _is_active(telegram["status"]),
                "status": telegram["status"],
            })
        if "messaging" in {service["id"] for service in services}:
            edges.append({
                "id": "telegram-messaging",
                "from": "telegram",
                "to": "messaging",
                "kind": "secondary",
                "active": _is_active(telegram["status"]),
                "status": telegram["status"],
            })
    if "vacation" in agent_ids:
        vacation = next(agent for agent in agents if agent["id"] == "vacation")
        edges.extend([
            {
                "id": "vacation-homeassistant",
                "from": "vacation",
                "to": "homeassistant",
                "kind": "secondary",
                "active": _is_active(vacation["status"]),
                "status": vacation["status"],
            },
            {
                "id": "vacation-openai",
                "from": "vacation",
                "to": "openai",
                "kind": "secondary",
                "active": _is_active(vacation["status"]),
                "status": vacation["status"],
            },
        ])
    if "mywellness" in agent_ids:
        mywellness = next(agent for agent in agents if agent["id"] == "mywellness")
        edges.append({
            "id": "mywellness-homeassistant",
            "from": "mywellness",
            "to": "homeassistant",
            "kind": "secondary",
            "active": _is_active(mywellness["status"]),
            "status": mywellness["status"],
        })
    if "garden" in agent_ids:
        garden = next(agent for agent in agents if agent["id"] == "garden")
        edges.append({
            "id": "garden-homeassistant",
            "from": "garden",
            "to": "homeassistant",
            "kind": "secondary",
            "active": _is_active(garden["status"]),
            "status": garden["status"],
        })
    return {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "product": active_product().public_dict(),
        "summary": _summary(agents),
        "nodes": nodes,
        "edges": edges,
    }


@router.get("/agents/{agent_id}/control")
def agent_control(agent_id: str) -> dict[str, Any]:
    return control_service.get_control_capabilities(agent_id)


@router.post("/agents/{agent_id}/control/{action}")
def execute_agent_control(agent_id: str, action: str, payload: ControlPayload | None = None) -> dict[str, Any]:
    data = payload.model_dump(exclude_none=True) if payload and hasattr(payload, "model_dump") else payload.dict(exclude_none=True) if payload else {}
    return control_service.execute(agent_id, action, data)


def _agent_node(manifest: dict[str, Any], live: bool = False) -> dict[str, Any]:
    agent_id = str(manifest.get("id") or "")
    status_data = _agent_status(agent_id) if live else _fast_agent_status(agent_id, manifest)
    status = _status_tone(agent_id, manifest, status_data)
    return {
        "id": agent_id,
        "label": _agent_label(agent_id, manifest),
        "subtitle": _agent_subtitle(agent_id, manifest),
        "kind": "platform" if agent_id == "scheduler" else "agent",
        "status": status,
        "icon": _agent_icon(agent_id, manifest),
        "enabled": bool(manifest.get("enabled", True)),
        "control": _control_info(agent_id),
        "dashboard_route": manifest.get("dashboard_route"),
        "api_prefix": manifest.get("api_prefix"),
        "last_run": _first_string(status_data, "last_successful_run", "last_finished_at", "last_started_at"),
        "next_action": _first_string(status_data, "next_scheduled_run") or _next_action(agent_id),
    }


def _agent_status(agent_id: str) -> dict[str, Any]:
    try:
        control = get_agent_control(agent_id)
        if control and "status" in control.capabilities():
            result = control.execute("status")
            data = result.get("data") if isinstance(result.get("data"), dict) else {}
            if isinstance(data, dict):
                data.setdefault("status", result.get("status"))
                return data
    except Exception as exc:
        return {"status": "error", "error": str(exc)}
    return {}


def _fast_agent_status(agent_id: str, manifest: dict[str, Any]) -> dict[str, Any]:
    enabled = bool(manifest.get("enabled", True))
    status = "active" if enabled else "disabled"
    defaults = {
        "invoices": {"next_scheduled_run": "22:00 Uhr"},
        "mywellness": {"next_scheduled_run": "17:00 Uhr"},
        "market": {"next_scheduled_run": "Bereit"},
        "vacation": {"next_scheduled_run": "Home Assistant synchronisieren"},
        "garden": {"next_scheduled_run": "07:00 Uhr"},
    }
    return {"status": status, "enabled": enabled, **defaults.get(agent_id, {})}


def _service_nodes(live: bool = False) -> list[dict[str, Any]]:
    ha_status = "active"
    if live:
        try:
            HomeAssistantService().get_states()
        except Exception:
            ha_status = "error"
    candidates = [
        ("messaging", {"id": "messaging", "label": "Message Center", "subtitle": "Nachrichten & Hinweise", "kind": "platform", "status": "active", "icon": "Bell", "control": _read_only_control()}),
        ("household", {"id": "household", "label": "Household", "subtitle": "Haushaltsstatus & Checks", "kind": "platform", "status": "active", "icon": "Home", "control": _read_only_control()}),
        ("llm", {"id": "openai", "label": "OpenAI", "subtitle": "Modelle & Verarbeitung", "kind": "service", "status": "active", "icon": "Sparkles", "control": _read_only_control()}),
        ("database", {"id": "database", "label": "Database", "subtitle": "Daten & Historie", "kind": "service", "status": "active", "icon": "Database", "control": _read_only_control()}),
        ("homeassistant", {"id": "homeassistant", "label": "Home Assistant", "subtitle": "Smart Home Bridge", "kind": "service", "status": ha_status, "icon": "HousePlug", "control": _read_only_control()}),
    ]
    return [node for service_id, node in candidates if service_id == "database" or is_core_service_enabled(service_id)]


def _primary_edges(agents: list[dict[str, Any]], services: list[dict[str, Any]], scheduler: dict[str, Any] | None) -> list[dict[str, Any]]:
    service_by_id = {service["id"]: service for service in services}
    if not scheduler:
        return [
            {
                "id": f"orchestrator-{agent['id']}",
                "from": "orchestrator",
                "to": agent["id"],
                "kind": "primary",
                "active": _is_active(agent["status"]),
                "status": agent["status"],
            }
            for agent in agents
        ]

    edges = [
        {
            "id": "orchestrator-scheduler",
            "from": "orchestrator",
            "to": "scheduler",
            "kind": "primary",
            "active": _is_active(scheduler["status"]),
            "status": scheduler["status"],
        }
    ]
    if "messaging" in service_by_id:
        messaging = service_by_id["messaging"]
        edges.append({
            "id": "orchestrator-messaging",
            "from": "orchestrator",
            "to": "messaging",
            "kind": "primary",
            "active": True,
            "status": messaging["status"],
        })
    scheduled_targets = {"market", "invoices", "vacation", "mywellness", "garden"}
    for agent in agents:
        if agent["id"] in scheduled_targets:
            edges.append({
                "id": f"scheduler-{agent['id']}",
                "from": "scheduler",
                "to": agent["id"],
                "kind": "primary",
                "active": _is_active(agent["status"]),
                "status": agent["status"],
            })
        elif agent["id"] == "telegram":
            edges.append({
                "id": "orchestrator-telegram",
                "from": "orchestrator",
                "to": "telegram",
                "kind": "primary",
                "active": _is_active(agent["status"]),
                "status": agent["status"],
            })
    if "household" in service_by_id:
        household = service_by_id["household"]
        edges.append({
            "id": "scheduler-household",
            "from": "scheduler",
            "to": "household",
            "kind": "primary",
            "active": True,
            "status": household["status"],
        })
    return edges


def _control_info(agent_id: str) -> dict[str, Any]:
    try:
        info = control_service.get_control_capabilities(agent_id)
    except Exception:
        return _read_only_control()
    return {
        "supported": bool(info.get("supported")),
        "actions": info.get("actions") or [],
    }


def _read_only_control() -> dict[str, Any]:
    return {"supported": False, "actions": []}


def _status_tone(agent_id: str, manifest: dict[str, Any], status_data: dict[str, Any]) -> str:
    raw = str(status_data.get("status") or status_data.get("current_status") or status_data.get("last_status") or manifest.get("status") or "").lower()
    if status_data.get("error") or status_data.get("last_error") or "error" in raw:
        return "error"
    if status_data.get("is_running") is True or "running" in raw:
        return "running"
    if status_data.get("enabled") is False or manifest.get("enabled") is False:
        return "disabled"
    if "disabled" in raw or raw == "aus":
        return "disabled"
    if "pause" in raw:
        return "paused"
    if "idle" in raw or raw in {"ok", "active", "ready"}:
        return "active"
    return "active"


def _summary(agents: list[dict[str, Any]]) -> dict[str, Any]:
    active = sum(1 for agent in agents if agent["status"] in {"active", "running"})
    paused = sum(1 for agent in agents if agent["status"] == "paused")
    errors = sum(1 for agent in agents if agent["status"] == "error")
    last = next((agent for agent in agents if agent.get("last_run")), None)
    next_agent = next((agent for agent in agents if agent.get("next_action")), None)
    return {
        "active": active,
        "paused": paused,
        "errors": errors,
        "last_activity": _activity_label(last, "Noch keine Live-Daten"),
        "next_activity": _activity_label(next_agent, "Nicht geplant"),
    }


def _activity_label(agent: dict[str, Any] | None, fallback: str) -> str:
    if not agent:
        return fallback
    value = agent.get("last_run") or agent.get("next_action") or ""
    return f"{agent['label']} · {value}" if value else fallback


def _is_active(status: str) -> bool:
    return status in {"active", "running"}


def _first_string(data: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def _agent_label(agent_id: str, manifest: dict[str, Any]) -> str:
    return str(manifest.get("name") or agent_id)


def _agent_subtitle(agent_id: str, manifest: dict[str, Any]) -> str:
    return str(manifest.get("description") or "Automatisierte Aufgabe")


def _agent_icon(agent_id: str, manifest: dict[str, Any]) -> str:
    return str(manifest.get("icon") or "Zap")


def _next_action(agent_id: str) -> str:
    actions = {
        "invoices": "22:00 Uhr",
        "mywellness": "17:00 Uhr",
        "market": "Bereit",
        "vacation": "Home Assistant synchronisieren",
        "garden": "07:00 Uhr",
    }
    return actions.get(agent_id, "Bereit")
