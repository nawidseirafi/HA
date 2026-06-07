from fastapi import APIRouter

from backend.agents.registry import discover_agent_manifests
from backend.editions import active_edition


router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.get("")
def list_agents():
    edition = active_edition()
    return {
        "edition": edition.public_dict(),
        "agents": [manifest.public_dict() for manifest in discover_agent_manifests()],
    }
