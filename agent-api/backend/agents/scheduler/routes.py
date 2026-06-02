from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from .service import SchedulerService


router = APIRouter(prefix="/api/scheduler", tags=["scheduler"])
scheduler_service = SchedulerService()


class SchedulerTaskPayload(BaseModel):
    name: str | None = None
    description: str | None = None
    enabled: bool | None = None
    schedule_type: str | None = None
    schedule: dict[str, Any] | None = None
    target_agent: str | None = None
    target_action: str | None = None
    action_type: str | None = None
    action_payload: dict[str, Any] | None = None


def payload_dict(payload: BaseModel) -> dict[str, Any]:
    if hasattr(payload, "model_dump"):
        return payload.model_dump(exclude_unset=True)
    return payload.dict(exclude_unset=True)


@router.get("/status")
def status():
    return scheduler_service.status()


@router.get("/summary")
def summary():
    return scheduler_service.summary()


@router.get("/tasks")
def tasks(status_filter: str | None = Query(default=None, alias="status")):
    return {"tasks": scheduler_service.tasks(status=status_filter)}


@router.post("/tasks")
def create_task(payload: SchedulerTaskPayload):
    try:
        return scheduler_service.create_task(payload_dict(payload))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/tasks/{task_id}")
def update_task(task_id: int, payload: SchedulerTaskPayload):
    try:
        return scheduler_service.update_task(task_id, payload_dict(payload))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/tasks/{task_id}/enable")
def enable_task(task_id: int):
    try:
        return scheduler_service.enable_task(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/tasks/{task_id}/disable")
def disable_task(task_id: int):
    try:
        return scheduler_service.disable_task(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/tasks/{task_id}/run")
def run_task(task_id: int):
    try:
        return scheduler_service.execute_task_by_id(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/runs")
def runs(limit: int = Query(default=100, ge=1, le=500)):
    return {"runs": scheduler_service.runs(limit=limit)}


@router.post("/run")
def run_scheduler():
    return scheduler_service.run()


@router.post("/enable")
def enable_scheduler():
    return scheduler_service.enable()


@router.post("/disable")
def disable_scheduler():
    return scheduler_service.disable()


@router.post("/toggle")
def toggle_scheduler():
    return scheduler_service.toggle()

