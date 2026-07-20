from fastapi import APIRouter
from pydantic import BaseModel

from backend.agents.vacation.routes import vacation_service
from backend.services.household_service import HouseholdService


router = APIRouter(prefix="/api/household", tags=["household"])
household_service = HouseholdService(vacation_status_provider=vacation_service.status)


class BedroomFanComfortPayload(BaseModel):
    apply: bool = False
    include_ai: bool | None = None


class OpeningsCheckPayload(BaseModel):
    notify: bool = True


@router.get("/status")
def household_status():
    return household_service.status()


@router.get("/summary")
def household_summary():
    return household_service.summary()


@router.get("/reminders")
def household_reminders():
    return household_service.reminders()


@router.get("/openings")
def household_openings():
    return household_service.openings_status()


@router.post("/openings/check")
def check_household_openings(payload: OpeningsCheckPayload | None = None):
    return household_service.check_openings(notify=payload.notify if payload else True)


@router.get("/comfort/bedroom-fan")
def household_bedroom_fan_comfort(include_ai: bool = False):
    return household_service.comfort_bedroom_fan(apply=False, include_ai=include_ai)


@router.post("/comfort/bedroom-fan/evaluate")
def evaluate_household_bedroom_fan_comfort(payload: BedroomFanComfortPayload | None = None):
    return household_service.comfort_bedroom_fan(
        apply=payload.apply if payload else False,
        include_ai=payload.include_ai if payload else None,
    )
