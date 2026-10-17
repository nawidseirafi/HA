import asyncio
import anyio
import json
import os
import secrets
import time
from urllib.parse import urlsplit
from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from backend.services.auth_service import verify_token, enforce_presence_reauth
from backend.services.homeassistant_service import HomeAssistantService
from .protocol import Frame
from .service import music_service, runtime_request

router = APIRouter(prefix="/api/music", tags=["music"])
_tickets = {}
_connections = set()


@router.get("/status")
def status():
    return music_service.status()


@router.get("/inventory")
def inventory():
    from backend.services.home_hub.service import HomeHub
    hub = HomeHub.default()
    def collect(domain):
        entries, offset = [], 0
        while True:
            page = hub.inventory(domain=domain, offset=offset, limit=100)
            for state in page["items"]:
                attrs = state.get("attributes", {})
                modes = attrs.get("supported_color_modes", [])
                dimmable = any(m in modes for m in ("brightness", "color_temp", "hs", "xy", "rgb", "rgbw", "rgbww", "white"))
                entries.append({"entity_id": state["entity_id"], "name": state["name"], "state": state["state"],
                    "area": state.get("area") or "Weitere Geräte", "floor": state.get("floor") or "Ohne Etage",
                    "selectable": dimmable and not attrs.get("entity_id") and not attrs.get("is_hue_group") and not state.get("disabled_by") and state["state"] in {"on", "off"}})
            if page["next_offset"] is None:
                return entries
            offset = page["next_offset"]
    return {"lights": collect("light"), "players": collect("media_player")}



@router.post("/ticket")
def ticket(request: Request):
    if os.getenv("ROBOTERSTEVE_MONITOR_ONLY") == "1":
        raise HTTPException(403, "Beobachtungsmodus")
    token = request.headers.get("authorization", "").partition(" ")[2]
    verify_token(token)
    now = time.monotonic()
    for key, value in list(_tickets.items()):
        if value[0] < now:
            _tickets.pop(key, None)
    if len(_tickets) >= 100:
        raise HTTPException(429, "Zu viele Verbindungsanfragen")
    value = secrets.token_urlsafe(32)
    _tickets[value] = (now + 30, token)
    return {"ticket": value}


def valid_origin(ws):
    origin = ws.headers.get("origin", "")
    expected = os.getenv("MUSIC_ALLOWED_ORIGIN") or os.getenv("ROBOTERSTEVE_PASSKEY_ORIGIN")
    if expected:
        return origin.rstrip("/") == expected.rstrip("/")
    parsed = urlsplit(origin)
    return parsed.scheme == "https" and parsed.netloc == ws.headers.get("host")


@router.websocket("/audio")
async def audio(ws: WebSocket):
    if os.getenv("ROBOTERSTEVE_MONITOR_ONLY") == "1" or not valid_origin(ws):
        await ws.close(code=1008)
        return
    await ws.accept()
    session = None
    claimed = False
    try:
        raw = await asyncio.wait_for(ws.receive_text(), timeout=5)
        if len(raw) > 512:
            raise ValueError("Nachricht zu groß")
        hello = json.loads(raw)
        if not isinstance(hello, dict) or set(hello) != {"ticket", "session"} or not isinstance(hello["ticket"], str):
            raise ValueError("Ungültiger Verbindungsaufbau")
        expiry, token = _tickets.pop(hello.get("ticket", ""), (0, ""))
        if expiry < time.monotonic():
            raise ValueError("Ticket abgelaufen")
        payload = verify_token(token)
        await asyncio.to_thread(enforce_presence_reauth, payload)
        current = await asyncio.to_thread(runtime_request, "GET", "/status")
        session = hello.get("session")
        if not session or current["session"] != session or session in _connections:
            raise ValueError("Sitzung nicht verfügbar")
        _connections.add(session)
        claimed = True
        await ws.send_json({"ready": True})
        window = checked = time.monotonic()
        count = 0
        while True:
            raw = await asyncio.wait_for(ws.receive_text(), timeout=3)
            now = time.monotonic()
            if len(raw) > 512:
                raise ValueError("Nachricht zu groß")
            if now - window >= 1:
                window, count = now, 0
            count += 1
            if count > 30:
                raise ValueError("Zu viele Nachrichten")
            if now - checked > 10:
                payload = verify_token(token)
                await asyncio.to_thread(enforce_presence_reauth, payload)
                checked = now
            verify_token(token)
            frame = Frame.model_validate_json(raw)
            if frame.session != session:
                raise ValueError("Falsche Sitzung")
            await asyncio.to_thread(runtime_request, "POST", "/frame", frame.model_dump())
    except (WebSocketDisconnect, asyncio.TimeoutError, ValueError, ValidationError, RuntimeError, HTTPException):
        try:
            await ws.close(code=1008)
        except RuntimeError:
            pass
    finally:
        if claimed:
            _connections.discard(session)
            with anyio.CancelScope(shield=True):
                try:
                    await asyncio.to_thread(runtime_request, "POST", "/command/stop", {"reason": "audio_disconnected", "session": session})
                except (ValueError, RuntimeError):
                    pass  # independent runtime watchdog remains authoritative
