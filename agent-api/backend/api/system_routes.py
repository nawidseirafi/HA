from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from backend.services.auth_service import configured_username, user_from_request
from backend.services.update_service import UpdateService


router = APIRouter(prefix="/api/system", tags=["system"])
update_service = UpdateService()


class UpdateCheckRequest(BaseModel):
    channel: str | None = None


class UpdateInstallRequest(BaseModel):
    layer: str | None = None


@router.get("/version")
def system_version() -> dict[str, Any]:
    return update_service.current_version()


@router.get("/update/check")
def check_update(channel: str | None = None) -> dict[str, Any]:
    return update_service.check_for_updates(channel=channel)


@router.post("/update/check")
def check_update_post(payload: UpdateCheckRequest) -> dict[str, Any]:
    return update_service.check_for_updates(channel=payload.channel)


@router.get("/update/status")
def update_status() -> dict[str, Any]:
    return update_service.status()


@router.get("/update/admin/status")
def update_admin_status(request: Request) -> dict[str, Any]:
    _require_developer_access(request)
    return update_service.admin_status()


@router.post("/update/install")
def install_update(payload: UpdateInstallRequest, request: Request) -> dict[str, Any]:
    user = _require_admin(request)
    try:
        return update_service.install_update(username=user, layer=payload.layer or "auto")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/update/rollback")
def rollback_update(request: Request) -> dict[str, Any]:
    user = _require_admin(request)
    try:
        return update_service.rollback(username=user)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _require_admin(request: Request) -> str:
    user = user_from_request(request)
    username = str(user.get("username") or "")
    if username != configured_username():
        raise HTTPException(status_code=403, detail="Nur Administratoren duerfen Updates installieren.")
    return username


def _require_developer_access(request: Request) -> str:
    user = user_from_request(request)
    username = str(user.get("username") or "")
    role = str(user.get("role") or "")
    if update_service.dev_mode_enabled() or username == configured_username() or role == "admin_developer":
        return username
    raise HTTPException(status_code=403, detail="Technische Update-Details sind nur im Entwickler-Modus verfuegbar.")
