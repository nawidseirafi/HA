from fastapi import APIRouter

from backend.services.infrastructure_service import InfrastructureService


router = APIRouter(prefix="/api/infrastructure", tags=["infrastructure"])
infrastructure_service = InfrastructureService()


@router.get("/status")
def infrastructure_status():
    return infrastructure_service.status()


@router.get("/summary")
def infrastructure_summary():
    return infrastructure_service.summary()
