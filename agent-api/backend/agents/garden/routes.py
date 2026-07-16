from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .service import GardenNotFound, GardenSafetyBlocked, GardenService


router = APIRouter(prefix="/api/garden", tags=["garden"])
garden_service = GardenService()


class RunPayload(BaseModel):
    dry_run: bool | None = None
    action: str | None = None
    zone_id: str | None = None
    source: str | None = None


class SettingsPayload(BaseModel):
    enabled: bool | None = None
    control_enabled: bool | None = None
    auto_discovery: bool | None = None
    dry_run_default: bool | None = None
    database_path: str | None = None
    schedule: list[str] | None = None
    zones: dict[str, Any] | None = None


class EvaluatePayload(BaseModel):
    save: bool = True


class IrrigationStartPayload(BaseModel):
    duration_minutes: int | None = Field(default=None, ge=1)
    source: str = "manual"


class IrrigationStopPayload(BaseModel):
    source: str = "manual"
    stop_reason: str = "manual"


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
    return garden_service.run(
        dry_run=payload.dry_run if payload else None,
        action=payload.action if payload else None,
        zone_id=payload.zone_id if payload else None,
        source=payload.source if payload and payload.source else "manual",
    )


@router.get("/zones")
def garden_zones():
    return {"zones": garden_service.zones()}


@router.get("/zones/{zone_id}")
def garden_zone(zone_id: str):
    try:
        return garden_service.zone(zone_id)
    except GardenNotFound as exc:
        raise HTTPException(status_code=404, detail=f"Garden-Zone {zone_id} wurde nicht gefunden.") from exc


@router.post("/evaluate")
def evaluate_garden(payload: EvaluatePayload | None = None):
    return garden_service.evaluate_all(save=payload.save if payload else True, apply=False, source="manual")


@router.post("/zones/{zone_id}/evaluate")
def evaluate_garden_zone(zone_id: str, payload: EvaluatePayload | None = None):
    try:
        return garden_service.evaluate_zone(zone_id, save=payload.save if payload else True)
    except GardenNotFound as exc:
        raise HTTPException(status_code=404, detail=f"Garden-Zone {zone_id} wurde nicht gefunden.") from exc


@router.post("/zones/{zone_id}/irrigation/start")
def start_garden_irrigation(zone_id: str, payload: IrrigationStartPayload | None = None):
    try:
        return garden_service.start_irrigation(
            zone_id,
            duration_minutes=payload.duration_minutes if payload else None,
            source=payload.source if payload else "manual",
        )
    except GardenNotFound as exc:
        raise HTTPException(status_code=404, detail=f"Garden-Zone {zone_id} wurde nicht gefunden.") from exc
    except GardenSafetyBlocked as exc:
        raise HTTPException(status_code=409, detail={"message": str(exc), "decision": exc.decision}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Home-Assistant-Service konnte Bewässerung nicht starten: {exc}") from exc


@router.post("/zones/{zone_id}/irrigation/stop")
def stop_garden_irrigation(zone_id: str, payload: IrrigationStopPayload | None = None):
    try:
        return garden_service.stop_irrigation(
            zone_id,
            source=payload.source if payload else "manual",
            stop_reason=payload.stop_reason if payload else "manual",
        )
    except GardenNotFound as exc:
        raise HTTPException(status_code=404, detail=f"Garden-Zone {zone_id} wurde nicht gefunden.") from exc
    except GardenSafetyBlocked as exc:
        raise HTTPException(status_code=409, detail={"message": str(exc), "decision": exc.decision}) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Home-Assistant-Service konnte Bewässerung nicht stoppen: {exc}") from exc


@router.get("/zones/{zone_id}/decisions")
def garden_zone_decisions(zone_id: str, limit: int = Query(default=100, ge=1, le=500)):
    try:
        return {"items": garden_service.decisions(zone_id, limit)}
    except GardenNotFound as exc:
        raise HTTPException(status_code=404, detail=f"Garden-Zone {zone_id} wurde nicht gefunden.") from exc


@router.get("/zones/{zone_id}/irrigation-runs")
def garden_zone_irrigation_runs(zone_id: str, limit: int = Query(default=100, ge=1, le=500)):
    try:
        return {"items": garden_service.irrigation_runs(zone_id, limit)}
    except GardenNotFound as exc:
        raise HTTPException(status_code=404, detail=f"Garden-Zone {zone_id} wurde nicht gefunden.") from exc


@router.get("/history")
def garden_history(limit: int = 100):
    return {"items": garden_service.history(limit=limit)}


@router.get("/snapshot/latest")
def garden_latest_snapshot():
    return {"snapshot": garden_service.latest_snapshot()}
