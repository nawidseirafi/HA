from fastapi import APIRouter

from backend.agents.registry import discover_agent_manifests
from backend.product import active_product


router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.get("")
def list_agents():
    return {
        "product": active_product().public_dict(),
        "agents": [manifest.public_dict() for manifest in discover_agent_manifests()],
    }
