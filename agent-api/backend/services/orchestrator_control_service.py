from typing import Any

from fastapi import HTTPException

from backend.agents.control import AgentControlCapability, CONTROL_ACTIONS
from backend.agents.registry import discover_agent_manifests, get_agent_control


class OrchestratorControlService:
    def list_controls(self) -> list[dict[str, Any]]:
        controls = []
        for manifest in discover_agent_manifests():
            control = get_agent_control(manifest.id)
            actions = control.capabilities() if control else []
            controls.append({
                "agent_id": manifest.id,
                "enabled": manifest.enabled,
                "supported": bool(actions),
                "actions": actions,
            })
        return controls

    def get_control_capabilities(self, agent_id: str) -> dict[str, Any]:
        manifest = self._manifest(agent_id)
        control = get_agent_control(manifest.id)
        actions = control.capabilities() if control else []
        return {
            "agent_id": manifest.id,
            "enabled": manifest.enabled,
            "supported": bool(actions),
            "actions": actions,
        }

    def execute(self, agent_id: str, action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        clean_action = self._action(action)
        manifest = self._manifest(agent_id)
        control = get_agent_control(manifest.id)
        if control is None:
            raise HTTPException(status_code=405, detail=f"Agent {manifest.id} bietet keinen Control-Vertrag an.")

        actions = control.capabilities()
        if clean_action not in actions:
            raise HTTPException(status_code=405, detail=f"Aktion {clean_action} wird fuer Agent {manifest.id} nicht unterstuetzt.")
        if not manifest.enabled and clean_action not in {"status", "enable"} and "enable" not in actions:
            raise HTTPException(status_code=409, detail=f"Agent {manifest.id} ist im Manifest deaktiviert.")

        try:
            result = control.execute(clean_action, payload or {})
        except HTTPException:
            raise
        except Exception as exc:
            return {
                "agent_id": manifest.id,
                "action": clean_action,
                "ok": False,
                "status": "error",
                "message": str(exc),
                "data": {},
            }
        if not result.get("ok", False) and result.get("status") == "unsupported":
            raise HTTPException(status_code=405, detail=result.get("message") or "Aktion nicht unterstuetzt.")
        return dict(result)

    def _manifest(self, agent_id: str):
        manifest = next((item for item in discover_agent_manifests() if item.id == agent_id), None)
        if manifest is None:
            raise HTTPException(status_code=404, detail=f"Agent {agent_id} wurde nicht gefunden.")
        return manifest

    def _action(self, action: str) -> AgentControlCapability:
        clean = str(action or "").strip().lower()
        if clean not in CONTROL_ACTIONS:
            raise HTTPException(status_code=405, detail=f"Control-Aktion {action} ist unbekannt.")
        return clean  # type: ignore[return-value]
