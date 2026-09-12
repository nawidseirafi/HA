from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from backend.services.auth_service import user_from_request
from backend.services.home_hub.actions import ActionService
from backend.services.home_hub.assistant import HouseAssistant
from backend.services.home_hub.service import HomeHub, public_data


router = APIRouter(prefix="/api/home-hub", tags=["home-hub"])


class ChatPayload(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


def principal(request: Request) -> str:
    return "web:" + user_from_request(request)["username"]


@router.get("/status")
def status():
    return HomeHub.default().status()


@router.get("/entities")
def entities(query: str = "", domain: str = "", area: str = "", offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)):
    return HomeHub.default().inventory(query, domain, area, offset, limit)


@router.get("/inventory/{kind}")
def inventory(kind: str, offset: int = Query(0, ge=0)):
    try:
        return HouseAssistant().query("inventory", {"kind": kind, "offset": offset}, "")
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/availability")
def availability():
    return HomeHub.default().availability()


@router.get("/agents")
def agents(agent_id: str = ""):
    return HomeHub.default().agents(agent_id)


@router.get("/context")
def context():
    return HomeHub.default().context()


@router.get("/history")
def history(subject: str = "", before: int | None = None, limit: int = Query(50, ge=1, le=200)):
    return {"items": public_data(HomeHub.default().store.history(subject, limit, before))}


@router.post("/chat")
def chat(payload: ChatPayload, request: Request):
    return {"answer": HouseAssistant().answer(payload.message, principal(request))}


@router.get("/conversation")
def conversation(request: Request):
    return {"items": HomeHub.default().store.conversation(principal(request))}


@router.delete("/conversation")
def forget(request: Request):
    HomeHub.default().store.forget(principal(request))
    return {"ok": True}


@router.get("/actions/{action_id}")
def action_status(action_id: str, request: Request):
    try:
        return public_data(HomeHub.default().store.action(action_id, principal(request)))
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/actions/{action_id}/confirm")
def confirm(action_id: str, request: Request):
    try:
        return public_data(ActionService(HomeHub.default()).confirm(principal(request), action_id))
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/automations")
def automations(request: Request):
    return {"items": HomeHub.default().store.rules(principal(request))}


@router.post("/automations/{rule_id}/activate")
def activate_rule(rule_id: str, request: Request):
    try:
        return ActionService(HomeHub.default()).activate_rule(principal(request), rule_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/automations/{rule_id}/pause")
def pause_rule(rule_id: str, request: Request):
    try:
        return HomeHub.default().store.set_rule_mode(rule_id, principal(request), "observe")
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
