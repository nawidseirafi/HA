from fastapi import APIRouter

from backend.agents.vacation.routes import vacation_service
from backend.services.household_service import HouseholdService


router = APIRouter(prefix="/api/household", tags=["household"])
household_service = HouseholdService(vacation_status_provider=vacation_service.status)


@router.get("/status")
def household_status():
    return household_service.status()


@router.get("/summary")
def household_summary():
    return household_service.summary()


@router.get("/reminders")
def household_reminders():
    return household_service.reminders()
