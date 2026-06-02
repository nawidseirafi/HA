from fastapi import APIRouter, Query

from backend.services.infrastructure_service import InfrastructureService


router = APIRouter(prefix="/api/infrastructure", tags=["infrastructure"])
infrastructure_service = InfrastructureService()


@router.get("/status")
def infrastructure_status():
    return infrastructure_service.status()


@router.get("/summary")
def infrastructure_summary():
    return infrastructure_service.summary()


@router.get("/events")
def infrastructure_events(limit: int = Query(100, ge=1, le=500)):
    return {"events": infrastructure_service.events(limit=limit)}


@router.get("/events/recent")
def infrastructure_recent_events(hours: int = Query(24, ge=1, le=720), limit: int = Query(100, ge=1, le=500)):
    return {"events": infrastructure_service.recent_events(hours=hours, limit=limit)}


@router.get("/outages")
def infrastructure_outages(hours: int = Query(24, ge=1, le=720)):
    return infrastructure_service.outages(hours=hours)


@router.post("/check")
def infrastructure_check():
    return infrastructure_service.check()
