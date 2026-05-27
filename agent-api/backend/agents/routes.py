from fastapi import APIRouter

from backend.agents.registry import discover_agent_manifests


router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.get("")
def list_agents():
    return {"agents": [manifest.public_dict() for manifest in discover_agent_manifests()]}
