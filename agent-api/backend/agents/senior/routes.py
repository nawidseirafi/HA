from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel

from .auth_service import SenteroAuthService
from .commissioning_service import CommissioningService
from .device_mapping_service import DeviceMappingService
from .matter_service import MatterCommissioningUnavailable
from .notification_service import NotificationService
from .service import SeniorService
from .setup_service import SeniorSetupService


class SenteroRouter(APIRouter):
    def add_api_route(self, path: str, endpoint: Any, **kwargs: Any) -> None:
        if path.startswith("/api/"):
            super().add_api_route(path, endpoint, **kwargs)
            return
        super().add_api_route(f"/api/senior{path}", endpoint, **kwargs)
        super().add_api_route(f"/api/sentero{path}", endpoint, **kwargs)


router = SenteroRouter(tags=["senior"])
device_mapping_service = DeviceMappingService()
setup_service = SeniorSetupService(device_mapping_service)
senior_service = SeniorService(device_mapping_service)
commissioning_service = CommissioningService(mapping=device_mapping_service)
notification_service = NotificationService(device_mapping_service)
auth_service = SenteroAuthService(device_mapping_service)


class ProfilePayload(BaseModel):
    name: str | None = None
    age: int | None = None
    notes: str | None = None


class RoomsPayload(BaseModel):
    rooms: list[str]


class DiscoveryStartPayload(BaseModel):
    role: str
    room: str | None = None
    pairing_code: str | None = None


class ZigbeePairingStartPayload(BaseModel):
    role: str
    room: str | None = None
    duration: int | None = None


class ConfirmPayload(BaseModel):
    entity_id: str
    name: str | None = None
    room: str | None = None


class MatterStartPayload(BaseModel):
    setup_code: str | None = None
    qr_payload: str | None = None


class MatterAssignPayload(BaseModel):
    room: str
    role: str


class ContactPayload(BaseModel):
    name: str
    relationship: str | None = None
    email: str | None = None
    phone: str | None = None
    telegram_chat_id: str | None = None
    whatsapp_phone_number: str | None = None
    preferred_channels: list[str] | None = None
    notification_enabled: bool = True


class NotificationPayload(BaseModel):
    anomalies: bool = True
    critical: bool = True
    daily_summary: bool = False


class SensorRoleNamePayload(BaseModel):
    name: str


class ChannelSettingsPayload(BaseModel):
    enabled: bool = False
    config: dict[str, Any] = {}


class SenteroSetupPayload(BaseModel):
    name: str
    email: str
    password: str
    password_confirm: str


class SenteroLoginPayload(BaseModel):
    email: str
    password: str


class ForgotPasswordPayload(BaseModel):
    email: str


class ResetPasswordPayload(BaseModel):
    token: str
    password: str
    password_confirm: str


class UpdateMePayload(BaseModel):
    display_name: str | None = None
    name: str | None = None
    email: str


class ChangePasswordPayload(BaseModel):
    current_password: str
    new_password: str
    new_password_confirm: str


def model_data(model: BaseModel) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def api_error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


def is_dev_mode(dev: bool = False) -> bool:
    return dev or os.getenv("ROBOTERSTEVE_DEV_MODE", "").lower() in {"1", "true", "yes", "on"}


@router.get("/api/sentero/auth/status")
def sentero_auth_status(request: Request):
    return auth_service.status(request)


@router.post("/api/sentero/auth/setup")
def sentero_auth_setup(payload: SenteroSetupPayload, request: Request, response: Response):
    return auth_service.setup(model_data(payload), response, request)


@router.post("/api/sentero/auth/login")
def sentero_auth_login(payload: SenteroLoginPayload, request: Request, response: Response):
    return auth_service.login(model_data(payload), response, request)


@router.post("/api/sentero/auth/logout")
def sentero_auth_logout(request: Request, response: Response):
    return auth_service.logout(request, response)


@router.get("/api/sentero/auth/me")
def sentero_auth_me(request: Request):
    return auth_service.me(request)


@router.put("/api/sentero/auth/me")
def sentero_auth_update_me(payload: UpdateMePayload, request: Request):
    return auth_service.update_me(model_data(payload), request)


@router.post("/api/sentero/auth/change-password")
def sentero_auth_change_password(payload: ChangePasswordPayload, request: Request):
    return auth_service.change_password(model_data(payload), request)


@router.post("/api/sentero/auth/forgot-password")
def sentero_auth_forgot_password(payload: ForgotPasswordPayload, request: Request):
    return auth_service.forgot_password(model_data(payload), request)


@router.post("/api/sentero/auth/reset-password")
def sentero_auth_reset_password(payload: ResetPasswordPayload):
    return auth_service.reset_password(model_data(payload))


@router.get("/status")
def senior_status():
    return senior_service.status()


@router.post("/run")
def run_senior_agent():
    return senior_service.run(dry_run=False)


@router.get("/behavior/latest")
def senior_behavior_latest():
    return {"assessment": senior_service.latest_behavior()}


@router.get("/behavior/history")
def senior_behavior_history(limit: int = Query(20, ge=1, le=100)):
    return {"assessments": senior_service.behavior_history(limit=limit)}


@router.get("/behavior/timeline")
def senior_behavior_timeline():
    return senior_service.behavior_timeline_today()


@router.get("/setup/status")
def setup_status():
    return setup_service.status()


@router.post("/setup/start")
def setup_start():
    return setup_service.set_step("profile", "welcome", complete=False)


@router.post("/setup/profile")
def setup_profile(payload: ProfilePayload):
    return setup_service.profile(model_data(payload))


@router.get("/setup/rooms")
def setup_rooms():
    return {"rooms": ["living_room", "kitchen", "bathroom", "bedroom", "hallway", "entrance"]}


@router.post("/setup/rooms")
def setup_rooms_save(payload: RoomsPayload):
    return setup_service.rooms(payload.rooms)


@router.post("/setup/discovery/start")
def discovery_start(payload: DiscoveryStartPayload):
    try:
        return device_mapping_service.start_pairing(payload.role, payload.room, payload.pairing_code)
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/setup/pairing/matter/start")
def matter_pairing_start(payload: DiscoveryStartPayload):
    try:
        return device_mapping_service.start_pairing(payload.role, payload.room, payload.pairing_code)
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/setup/pairing/zigbee/start")
def zigbee_pairing_start(payload: ZigbeePairingStartPayload):
    try:
        return device_mapping_service.start_zigbee_pairing(payload.role, payload.room, duration=payload.duration or 60)
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/matter/start")
def matter_start(payload: MatterStartPayload):
    try:
        return commissioning_service.start(setup_code=payload.setup_code, qr_payload=payload.qr_payload)
    except MatterCommissioningUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/matter/capabilities")
def matter_capabilities(dev: bool = Query(False)):
    try:
        return commissioning_service.capabilities(dev=is_dev_mode(dev))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/matter/status/{commissioning_id}")
def matter_status(commissioning_id: str, dev: bool = Query(False)):
    try:
        return commissioning_service.status(commissioning_id, dev=is_dev_mode(dev))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/matter/device/{commissioning_id}")
def matter_device(commissioning_id: str, dev: bool = Query(False)):
    try:
        return commissioning_service.device(commissioning_id, dev=is_dev_mode(dev))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/matter/device/{commissioning_id}/assign")
def matter_assign(commissioning_id: str, payload: MatterAssignPayload):
    try:
        return commissioning_service.assign(commissioning_id, room=payload.room, role=payload.role)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/setup/discovery/{session_id}/candidates")
def discovery_candidates(session_id: int, dev: bool = Query(False)):
    try:
        return device_mapping_service.candidates(session_id, dev=dev)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/setup/discovery/{session_id}/confirm")
def discovery_confirm(session_id: int, payload: ConfirmPayload, dev: bool = Query(False)):
    try:
        return device_mapping_service.confirm(session_id, payload.entity_id, name=payload.name, room=payload.room, dev=dev)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/setup/sensors")
def setup_sensors():
    return setup_service.sensors()


@router.post("/setup/contact")
def setup_contact(payload: ContactPayload):
    return setup_service.contact(model_data(payload))


@router.put("/setup/contact/{contact_id}")
def setup_contact_update(contact_id: int, payload: ContactPayload):
    try:
        return setup_service.update_contact(contact_id, model_data(payload))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/setup/contact/{contact_id}")
def setup_contact_delete(contact_id: int):
    return setup_service.delete_contact(contact_id)


@router.post("/setup/notifications")
def setup_notifications(payload: NotificationPayload):
    return setup_service.notifications(model_data(payload))


@router.get("/notifications/channels")
def notification_channels():
    return notification_service.channels()


@router.post("/notifications/channels/email")
def notification_channel_email(payload: ChannelSettingsPayload):
    return notification_service.save_channel("email", True, payload.config)


@router.post("/notifications/channels/telegram")
def notification_channel_telegram(payload: ChannelSettingsPayload):
    return notification_service.save_channel("telegram", payload.enabled, payload.config)


@router.post("/notifications/channels/whatsapp")
def notification_channel_whatsapp(payload: ChannelSettingsPayload):
    return notification_service.save_channel("whatsapp", payload.enabled, payload.config)


@router.post("/notifications/test/email")
def notification_test_email(dev: bool = Query(False)):
    return notification_service.test("email", dev=is_dev_mode(dev))


@router.post("/notifications/test/telegram")
def notification_test_telegram(dev: bool = Query(False)):
    return notification_service.test("telegram", dev=is_dev_mode(dev))


@router.post("/notifications/test/whatsapp")
def notification_test_whatsapp(dev: bool = Query(False)):
    return notification_service.test("whatsapp", dev=is_dev_mode(dev))


@router.get("/notifications/logs")
def notification_logs(limit: int = Query(100, ge=1, le=500)):
    return notification_service.logs(limit=limit)


@router.post("/setup/complete")
def setup_complete():
    return setup_service.set_step("complete", "complete", complete=True)


@router.get("/sensor-roles")
def sensor_roles(dev: bool = Query(False), include_state: bool = Query(False)):
    return {"sensor_roles": device_mapping_service.roles(dev=dev, include_state=include_state)}


@router.post("/sensor-roles")
def sensor_role_save(payload: dict[str, Any]):
    try:
        return device_mapping_service.upsert_role(payload)
    except Exception as exc:
        raise api_error(exc) from exc


@router.delete("/sensor-roles/{role}")
def sensor_role_delete(role: str):
    try:
        return device_mapping_service.delete_role(role)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/sensor-roles/{role}/test")
def sensor_role_test(role: str):
    try:
        return device_mapping_service.test_role(role)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise api_error(exc) from exc


@router.put("/sensor-roles/{role}/name")
def sensor_role_rename(role: str, payload: SensorRoleNamePayload):
    try:
        return device_mapping_service.rename_role(role, payload.name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise api_error(exc) from exc
