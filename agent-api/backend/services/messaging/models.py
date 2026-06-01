from typing import Any, Literal

from pydantic import BaseModel


Severity = Literal["info", "warning", "critical"]


class MessageCreate(BaseModel):
    source: str
    category: str
    severity: Severity = "info"
    title: str
    message: str
    payload: dict[str, Any] | None = None


class Message(MessageCreate):
    id: int
    read: bool = False
    created_at: str
    read_at: str | None = None


class MessageList(BaseModel):
    messages: list[Message]


class UnreadCount(BaseModel):
    unread_count: int
