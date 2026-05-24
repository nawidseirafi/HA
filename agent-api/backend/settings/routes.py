from fastapi import APIRouter

from backend.settings.service import get_settings


router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
def settings():
    return get_settings()
