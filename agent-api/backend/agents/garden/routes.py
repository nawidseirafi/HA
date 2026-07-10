from fastapi import APIRouter
from pydantic import BaseModel

from .service import GardenService


router = APIRouter(prefix="/api/garden", tags=["garden"])
garden_service = GardenService()


class RunPayload(BaseModel):
    dry_run: bool | None = None


class SettingsPayload(BaseModel):
    enabled: bool | None = None
    dry_run_default: bool | None = None
    database_path: str | None = None
    thresholds: dict | None = None
    schedule: list[str] | None = None
    entities: dict | None = None


@router.get("/status")
def garden_status():
    return garden_service.status()


@router.get("/config")
def garden_config():
    return garden_service.config()


@router.put("/settings")
def update_garden_settings(payload: SettingsPayload):
    data = payload.model_dump(exclude_unset=True) if hasattr(payload, "model_dump") else payload.dict(exclude_unset=True)
    return garden_service.update_settings(data)


@router.post("/enable")
def enable_garden_agent():
    return garden_service.enable()


@router.post("/disable")
def disable_garden_agent():
    return garden_service.disable()


@router.post("/toggle")
def toggle_garden_agent():
    return garden_service.toggle()


@router.post("/run")
def run_garden_agent(payload: RunPayload | None = None):
    return garden_service.run(dry_run=payload.dry_run if payload else None)


@router.get("/history")
def garden_history(limit: int = 100):
    return {"items": garden_service.history(limit=limit)}


@router.get("/snapshot/latest")
def garden_latest_snapshot():
    return {"snapshot": garden_service.latest_snapshot()}
