from typing import Literal, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from backend.agents.mywellness.service import MyWellnessService
from backend.services.mywellness_health_service import MyWellnessHealthService


router = APIRouter(tags=["mywellness"])
mywellness_service = MyWellnessService()
mywellness_health_service = MyWellnessHealthService()


class StartAgentPayload(BaseModel):
    mode: Optional[Literal["prepare", "book"]] = "prepare"


class CourseActionPayload(BaseModel):
    courseId: str


class RunPayload(BaseModel):
    dry_run: bool = False


class SettingsPayload(BaseModel):
    enabled: Optional[bool] = None
    prepare_enabled: Optional[bool] = None
    booking_enabled: Optional[bool] = None
    prepare_time: Optional[str] = None
    booking_time: Optional[str] = None
    days: Optional[int] = None
    desired_courses: Optional[list[str]] = None


class HealthSettingsPayload(BaseModel):
    enabled: Optional[bool] = None
    profile_birth_date: Optional[str] = None
    profile_supplements: Optional[str] = None
    profile_notes: Optional[str] = None
    ha_entity_steps: Optional[str] = None
    ha_entity_active_calories: Optional[str] = None
    ha_entity_resting_heart_rate: Optional[str] = None
    ha_entity_hrv: Optional[str] = None
    ha_entity_sleep_hours: Optional[str] = None
    ha_entity_weight: Optional[str] = None
    ha_entity_blood_pressure_systolic: Optional[str] = None
    ha_entity_blood_pressure_diastolic: Optional[str] = None
    ha_entity_withings_weight: Optional[str] = None
    ha_entity_withings_bmi: Optional[str] = None
    ha_entity_withings_fat_mass: Optional[str] = None
    ha_entity_withings_muscle_mass: Optional[str] = None
    ha_entity_withings_body_water: Optional[str] = None
    ha_entity_withings_heart_rate: Optional[str] = None
    ha_entity_withings_systolic_blood_pressure: Optional[str] = None
    ha_entity_withings_diastolic_blood_pressure: Optional[str] = None
    ha_entity_withings_sleep_score: Optional[str] = None
    ha_entity_withings_sleep_duration: Optional[str] = None
    ha_entity_withings_deep_sleep: Optional[str] = None
    ha_entity_withings_light_sleep: Optional[str] = None
    ha_entity_withings_rem_sleep: Optional[str] = None


@router.get("/api/agent/status")
def agent_status():
    return mywellness_service.status()


@router.post("/api/agent/start")
def start_agent(payload: StartAgentPayload | None = None):
    mode = payload.mode if payload else "prepare"
    return mywellness_service.start(mode=mode or "prepare")


@router.post("/api/agent/stop")
def stop_agent():
    return mywellness_service.stop()


@router.get("/api/mywellness/status")
def mywellness_status():
    return mywellness_service.status()


@router.post("/api/mywellness/run/prepare")
def mywellness_run_prepare(payload: RunPayload | None = None):
    return mywellness_service.run_action("prepare", dry_run=payload.dry_run if payload else False)


@router.post("/api/mywellness/run/book")
def mywellness_run_book(payload: RunPayload | None = None):
    return mywellness_service.run_action("book", dry_run=payload.dry_run if payload else False)


@router.post("/api/mywellness/enable")
def mywellness_enable():
    return mywellness_service.enable()


@router.post("/api/mywellness/disable")
def mywellness_disable():
    return mywellness_service.disable()


@router.post("/api/mywellness/toggle")
def mywellness_toggle():
    return mywellness_service.toggle()


@router.put("/api/mywellness/settings")
def mywellness_update_settings(payload: SettingsPayload):
    data = payload.model_dump(exclude_unset=True) if hasattr(payload, "model_dump") else payload.dict(exclude_unset=True)
    return mywellness_service.update_settings(data)


@router.get("/api/mywellness/courses")
def mywellness_courses():
    return mywellness_service.courses()


@router.get("/api/mywellness/courses/upcoming")
def mywellness_upcoming_courses():
    return mywellness_service.upcoming_courses()


@router.post("/api/mywellness/book")
def mywellness_book_course(payload: CourseActionPayload):
    return mywellness_service.book_course(payload.courseId)


@router.post("/api/mywellness/cancel")
def mywellness_cancel_course(payload: CourseActionPayload):
    return mywellness_service.cancel_course(payload.courseId)


@router.get("/api/mywellness/bookings")
def mywellness_bookings():
    return mywellness_service.bookings()


@router.get("/api/mywellness/logs")
def mywellness_logs(limit: int = Query(200, ge=1, le=1000)):
    return mywellness_service.logs(limit=limit)


@router.get("/api/mywellness/health/status")
def mywellness_health_status():
    return mywellness_health_service.status()


@router.get("/api/mywellness/health/metrics")
def mywellness_health_metrics(limit: int = Query(30, ge=1, le=365)):
    return mywellness_health_service.metrics(limit=limit)


@router.post("/api/mywellness/health/import-from-ha")
def mywellness_health_import_from_ha():
    return mywellness_health_service.import_from_ha()


@router.post("/api/mywellness/health/analyze")
def mywellness_health_analyze():
    return mywellness_health_service.analyze()


@router.get("/api/mywellness/health/latest-report")
def mywellness_health_latest_report():
    return {"report": mywellness_health_service.latest_report()}


@router.get("/api/mywellness/health/reports")
def mywellness_health_reports(limit: int = Query(30, ge=1, le=365)):
    return mywellness_health_service.reports(limit=limit)


@router.put("/api/mywellness/health/settings")
def mywellness_health_update_settings(payload: HealthSettingsPayload):
    data = payload.model_dump(exclude_unset=True) if hasattr(payload, "model_dump") else payload.dict(exclude_unset=True)
    return mywellness_health_service.update_settings(data)


@router.get("/api/mywellness/health/withings/entities")
def mywellness_health_withings_entities():
    return mywellness_health_service.withings_entities()


@router.post("/api/mywellness/health/withings/import")
def mywellness_health_withings_import():
    return mywellness_health_service.import_withings_metrics_from_ha()


@router.get("/api/mywellness/health/withings/latest")
def mywellness_health_withings_latest():
    return mywellness_health_service.latest_withings()


@router.post("/api/mywellness/health/withings/discover")
def mywellness_health_withings_discover():
    return mywellness_health_service.discover_withings_entities()
