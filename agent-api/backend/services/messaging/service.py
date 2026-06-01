from typing import Any

from .store import MessagingStore


VALID_SEVERITIES = {"info", "warning", "critical"}


class MessagingService:
    def __init__(self, store: MessagingStore | None = None) -> None:
        self.store = store or MessagingStore()

    def create_message(
        self,
        source: str,
        category: str,
        severity: str,
        title: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        severity = severity if severity in VALID_SEVERITIES else "info"
        return self.store.create_message(
            source=str(source or "system"),
            category=str(category or source or "system"),
            severity=severity,
            title=str(title or "Nachricht"),
            message=str(message or ""),
            payload=payload or {},
        )

    def mark_read(self, message_id: int) -> dict[str, Any] | None:
        return self.store.mark_read(message_id)

    def mark_all_read(self) -> int:
        return self.store.mark_all_read()

    def delete_message(self, message_id: int) -> bool:
        return self.store.delete_message(message_id)

    def delete_all_messages(self) -> int:
        return self.store.delete_all_messages()

    def get_messages(self, limit: int = 100, unread_only: bool = False) -> list[dict[str, Any]]:
        return self.store.get_messages(limit=limit, unread_only=unread_only)

    def get_unread_count(self) -> int:
        return self.store.get_unread_count()

    def get_messages_by_source(self, source: str, limit: int = 100) -> list[dict[str, Any]]:
        return self.store.get_messages_by_source(source=source, limit=limit)
