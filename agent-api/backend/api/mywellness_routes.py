from typing import Literal, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from backend.services.mywellness_service import MyWellnessService


router = APIRouter(tags=["mywellness"])
mywellness_service = MyWellnessService()


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
