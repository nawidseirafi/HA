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
