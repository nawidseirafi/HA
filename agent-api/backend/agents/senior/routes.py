from fastapi import APIRouter

from .service import SeniorService


router = APIRouter(prefix="/api/senior", tags=["senior"])
senior_service = SeniorService()


@router.get("/status")
def senior_status():
    return senior_service.status()


@router.post("/run")
def run_senior_agent():
    return senior_service.run(dry_run=False)
