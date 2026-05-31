from datetime import datetime
from typing import Any

from fastapi import APIRouter

from backend.agents.registry import discover_agent_manifests
from backend.agents.invoices.routes import invoice_service
from backend.agents.market.report_service import MarketReportService
from backend.agents.mywellness.routes import mywellness_service
from backend.agents.vacation.routes import vacation_service
from backend.services.homeassistant_service import HomeAssistantService


router = APIRouter(prefix="/api/orchestrator", tags=["orchestrator"])


@router.get("/map")
def orchestrator_map() -> dict[str, Any]:
    agents = [_agent_node(manifest.public_dict()) for manifest in discover_agent_manifests()]
    agent_ids = {agent["id"] for agent in agents}
    services = _service_nodes()
    nodes = [
        {
            "id": "orchestrator",
            "label": "RoboterSteve",
            "subtitle": "Orchestrator",
            "kind": "orchestrator",
            "status": "running" if any(agent["status"] == "running" for agent in agents) else "active",
            "icon": "Bot",
        },
        *agents,
        *services,
    ]
    edges = [
        *[
            {
                "id": f"orchestrator-{agent_id}",
                "from": "orchestrator",
                "to": agent_id,
                "kind": "primary",
                "active": _is_active(agent["status"]),
                "status": agent["status"],
            }
            for agent in agents
            for agent_id in [agent["id"]]
        ],
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
            if agent_id in {"invoices", "mywellness", "market", "vacation"}
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
            if agent_id in {"invoices", "mywellness", "market"}
        ],
    ]
    if "vacation" in agent_ids:
        vacation = next(agent for agent in agents if agent["id"] == "vacation")
        edges.append({
            "id": "vacation-homeassistant",
            "from": "vacation",
            "to": "homeassistant",
            "kind": "secondary",
            "active": _is_active(vacation["status"]),
            "status": vacation["status"],
        })
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
    return {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "summary": _summary(agents),
        "nodes": nodes,
        "edges": edges,
    }


def _agent_node(manifest: dict[str, Any]) -> dict[str, Any]:
    agent_id = str(manifest.get("id") or "")
    status_data = _agent_status(agent_id)
    status = _status_tone(agent_id, manifest, status_data)
    return {
        "id": agent_id,
        "label": _agent_label(agent_id, manifest),
        "subtitle": _agent_subtitle(agent_id, manifest),
        "kind": "agent",
        "status": status,
        "icon": _agent_icon(agent_id, manifest),
        "enabled": bool(manifest.get("enabled", True)),
        "dashboard_route": manifest.get("dashboard_route"),
        "api_prefix": manifest.get("api_prefix"),
        "last_run": _first_string(status_data, "last_successful_run", "last_finished_at", "last_started_at"),
        "next_action": _first_string(status_data, "next_scheduled_run") or _next_action(agent_id),
    }


def _agent_status(agent_id: str) -> dict[str, Any]:
    try:
        if agent_id == "invoices":
            return invoice_service.status()
        if agent_id == "mywellness":
            return mywellness_service.status()
        if agent_id == "market":
            return {"status": "paused", **MarketReportService().summary()}
        if agent_id == "vacation":
            return vacation_service.status()
    except Exception as exc:
        return {"status": "error", "error": str(exc)}
    return {}


def _service_nodes() -> list[dict[str, Any]]:
    ha_status = "active"
    try:
        HomeAssistantService().get_states()
    except Exception:
        ha_status = "error"
    return [
        {"id": "openai", "label": "OpenAI", "subtitle": "Modelle & Verarbeitung", "kind": "service", "status": "active", "icon": "Sparkles"},
        {"id": "database", "label": "Database", "subtitle": "Daten & Historie", "kind": "service", "status": "active", "icon": "Database"},
        {"id": "homeassistant", "label": "Home Assistant", "subtitle": "Smart Home Bridge", "kind": "service", "status": ha_status, "icon": "HousePlug"},
    ]


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
    if agent_id == "market":
        return "paused"
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
    actions = {"invoices": "22:00 Uhr", "mywellness": "17:00 Uhr", "market": "Bereit", "vacation": "Home Assistant synchronisieren"}
    return actions.get(agent_id, "Bereit")
