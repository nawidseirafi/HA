from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .service import TelegramService, config_public


router = APIRouter(prefix="/api/telegram", tags=["telegram"])
telegram_service = TelegramService()


class TelegramTestPayload(BaseModel):
    text: str | None = None


class TelegramSettingsPayload(BaseModel):
    enabled: bool | None = None
    bot_token: str | None = None
    allowed_chat_ids: list[str] | None = None
    auto_pair_first_chat: bool | None = None
    default_chat_id: str | None = None
    poll_interval_seconds: int | None = None
    timeout_seconds: int | None = None
    hourly_limit: int | None = None
    daily_limit: int | None = None


@router.get("/status")
def status():
    return telegram_service.status()


@router.get("/config")
def config():
    return config_public(telegram_service.config())


@router.put("/settings")
def update_settings(payload: TelegramSettingsPayload):
    try:
        data = payload.model_dump(exclude_unset=True) if hasattr(payload, "model_dump") else payload.dict(exclude_unset=True)
        return telegram_service.update_settings(data)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/bot")
def bot_info():
    try:
        return telegram_service.bot_info()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/setup")
def setup_info():
    return telegram_service.setup_info()


@router.get("/discover-chats")
def discover_chats():
    try:
        return telegram_service.discover_chats()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/poll")
def poll_once():
    try:
        return telegram_service.poll_once()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/test")
def test_send(payload: TelegramTestPayload | None = None):
    try:
        text = payload.text if payload and payload.text else "Roboter Steve Telegram ist verbunden."
        return telegram_service.test_send(text)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/start")
def start():
    return telegram_service.start()


@router.post("/stop")
def stop():
    return telegram_service.stop()


@router.post("/enable")
def enable():
    return telegram_service.enable()


@router.post("/disable")
def disable():
    return telegram_service.disable()


@router.post("/toggle")
def toggle():
    return telegram_service.toggle()
