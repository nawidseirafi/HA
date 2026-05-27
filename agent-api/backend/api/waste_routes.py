from fastapi import APIRouter

from backend.services.waste_service import WasteService


router = APIRouter(prefix="/api/waste", tags=["waste"])
waste_service = WasteService()


@router.get("/status")
def waste_status():
    return waste_service.status()


@router.get("/next")
def waste_next():
    return waste_service.next()


@router.get("/reminders")
def waste_reminders():
    return waste_service.reminder_status()
