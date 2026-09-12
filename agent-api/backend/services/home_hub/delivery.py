import hashlib
import json
import threading
import time

from backend.services.home_hub.store import HubStore, now


class DeliveryService:
    _lock = threading.Lock()

    def __init__(self, store: HubStore):
        self.store = store

    def enqueue(self, key: str, channel: str, target: str, payload: dict) -> str:
        delivery_id = hashlib.sha256(f"{key}:{channel}:{target}".encode()).hexdigest()
        with self.store.connect() as db:
            db.execute("INSERT OR IGNORE INTO deliveries(id, channel, target, payload, status, created_at) VALUES (?, ?, ?, ?, 'pending', ?)",
                       (delivery_id, channel, target, json.dumps(payload), now()))
        return delivery_id

    def drain(self, sender=None, should_stop=None) -> dict:
        results = []
        with self._lock:
            with self.store.connect() as db:
                rows = db.execute("SELECT * FROM deliveries WHERE status = 'pending' AND next_attempt <= ? ORDER BY created_at LIMIT 20", (time.time(),)).fetchall()
            for row in rows:
                if should_stop and should_stop():
                    break
                payload = json.loads(row["payload"])
                try:
                    (sender or self._send)(row["channel"], row["target"], payload)
                    status, error = "sent", None
                except Exception as exc:
                    status, error = "pending", type(exc).__name__
                attempts = row["attempts"] + 1
                delay = min(3600, 15 * 2 ** min(attempts, 8))
                with self.store.connect() as db:
                    db.execute("UPDATE deliveries SET status = ?, attempts = ?, next_attempt = ?, error = ? WHERE id = ?",
                               (status, attempts, time.time() + delay, error, row["id"]))
                result = {"id": row["id"], "status": status, "attempts": attempts, "error": error}
                self.store.event("notification_delivery", row["id"], result)
                results.append(result)
        return {"items": results}

    def _send(self, channel: str, target: str, payload: dict) -> None:
        if channel == "telegram":
            from backend.agents.telegram.service import TelegramService, _effective_allowed_chat_ids
            service = TelegramService()
            config = service.config()
            if not config.enabled or target not in _effective_allowed_chat_ids(config):
                raise ValueError("Telegram target not enabled")
            service.client(config).send_message(target, payload["text"])
        elif channel == "mobile_push":
            from backend.services.homeassistant_service import HomeAssistantService
            HomeAssistantService().call_service("notify", target, payload)
        else:
            raise ValueError("Unknown delivery channel")

    def summary(self) -> dict:
        with self.store.connect() as db:
            rows = db.execute("SELECT status, count(*) AS count FROM deliveries GROUP BY status").fetchall()
        return {row["status"]: row["count"] for row in rows}
