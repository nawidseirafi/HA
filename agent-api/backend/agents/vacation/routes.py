from fastapi import APIRouter
from pydantic import BaseModel

from backend.agents.vacation.service import VacationService

router = APIRouter(prefix="/api/vacation", tags=["vacation"])
vacation_service = VacationService()


class RunPayload(BaseModel):
    dry_run: bool = True


@router.get("/status")
def vacation_status():
    return vacation_service.status()


@router.get("/config")
def vacation_config():
    return vacation_service.config()


@router.post("/run")
def run_vacation_agent(payload: RunPayload | None = None):
    return vacation_service.run(dry_run=payload.dry_run if payload else True)
