from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from .commissioning_service import CommissioningService
from .device_mapping_service import DeviceMappingService
from .matter_service import MatterCommissioningUnavailable
from .service import SeniorService
from .setup_service import SeniorSetupService


router = APIRouter(prefix="/api/senior", tags=["senior"])
device_mapping_service = DeviceMappingService()
setup_service = SeniorSetupService(device_mapping_service)
senior_service = SeniorService(device_mapping_service)
commissioning_service = CommissioningService(mapping=device_mapping_service)


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


class NotificationPayload(BaseModel):
    anomalies: bool = True
    critical: bool = True
    daily_summary: bool = False


def model_data(model: BaseModel) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def api_error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


def is_dev_mode(dev: bool = False) -> bool:
    return dev or os.getenv("ROBOTERSTEVE_DEV_MODE", "").lower() in {"1", "true", "yes", "on"}


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
        return device_mapping_service.confirm(session_id, payload.entity_id, dev=dev)
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
    return device_mapping_service.delete_role(role)
