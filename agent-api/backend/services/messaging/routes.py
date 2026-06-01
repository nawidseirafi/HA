from fastapi import APIRouter, HTTPException, Query

from .models import MessageCreate
from .service import MessagingService


router = APIRouter(prefix="/api/messages", tags=["messages"])
messaging_service = MessagingService()


@router.get("")
def messages(limit: int = Query(default=100, ge=1, le=500), unread_only: bool = False):
    return {"messages": messaging_service.get_messages(limit=limit, unread_only=unread_only)}


@router.get("/unread-count")
def unread_count():
    return {"unread_count": messaging_service.get_unread_count()}


@router.get("/source/{source}")
def messages_by_source(source: str, limit: int = Query(default=100, ge=1, le=500)):
    return {"messages": messaging_service.get_messages_by_source(source=source, limit=limit)}


@router.post("")
def create_message(payload: MessageCreate):
    return messaging_service.create_message(
        source=payload.source,
        category=payload.category,
        severity=payload.severity,
        title=payload.title,
        message=payload.message,
        payload=payload.payload,
    )


@router.post("/{message_id}/read")
def mark_read(message_id: int):
    message = messaging_service.mark_read(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Nachricht nicht gefunden.")
    return message


@router.post("/read-all")
def mark_all_read():
    return {"updated": messaging_service.mark_all_read()}


@router.delete("")
def delete_all_messages():
    return {"deleted": messaging_service.delete_all_messages()}


@router.delete("/{message_id}")
def delete_message(message_id: int):
    if not messaging_service.delete_message(message_id):
        raise HTTPException(status_code=404, detail="Nachricht nicht gefunden.")
    return {"ok": True}
