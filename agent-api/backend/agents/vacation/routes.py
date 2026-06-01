from fastapi import APIRouter
from pydantic import BaseModel

from .service import VacationService

router = APIRouter(prefix="/api/vacation", tags=["vacation"])
vacation_service = VacationService()


class RunPayload(BaseModel):
    dry_run: bool = True
    action: str | None = None
    start_date: str | None = None
    end_date: str | None = None


class VacationPeriodPayload(BaseModel):
    start_date: str | None = None
    end_date: str | None = None


class SettingsPayload(BaseModel):
    enabled: bool | None = None
    calendar_entity: str | None = None


@router.get("/status")
def vacation_status():
    return vacation_service.get_status()


@router.get("/reminders")
def vacation_reminders():
    return {"reminders": vacation_service.get_reminders(status="open")}


@router.get("/profiles")
def vacation_profiles(limit: int = 100):
    return vacation_service.get_profiles(limit=limit)


@router.get("/history")
def vacation_history(limit: int = 100):
    return vacation_service.history(limit=limit)


@router.get("/config")
def vacation_config():
    return vacation_service.config()


@router.post("/enable")
def enable_vacation_agent():
    return vacation_service.enable()


@router.post("/disable")
def disable_vacation_agent():
    return vacation_service.disable()


@router.post("/toggle")
def toggle_vacation_agent():
    return vacation_service.toggle()


@router.put("/settings")
def update_vacation_settings(payload: SettingsPayload):
    data = payload.model_dump(exclude_unset=True) if hasattr(payload, "model_dump") else payload.dict(exclude_unset=True)
    return vacation_service.update_settings(data)


@router.post("/run")
def run_vacation_agent(payload: RunPayload | None = None):
    return vacation_service.run(
        dry_run=payload.dry_run if payload else True,
    )


@router.post("/mode/enable")
def enable_vacation_mode():
    return vacation_service.enable_vacation_mode()


@router.post("/mode/disable")
def disable_vacation_mode():
    return vacation_service.disable_vacation_mode()


@router.post("/mode/toggle")
def toggle_vacation_mode():
    return vacation_service.toggle_vacation_mode()


@router.post("/start")
def start_vacation(payload: VacationPeriodPayload | None = None):
    return vacation_service.start_vacation(
        start_date=payload.start_date if payload else None,
        end_date=payload.end_date if payload else None,
    )


@router.post("/end")
def end_vacation(payload: VacationPeriodPayload | None = None):
    return vacation_service.end_vacation(end_date=payload.end_date if payload else None)
