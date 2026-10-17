"""Steve-side control adapter. The worker is managed by systemd, not this module."""
import os
import httpx
from backend.config import load_agent_section
from .store import socket_path, Store


def runtime_request(method, path, payload=None, timeout=15):
    try:
        with httpx.Client(transport=httpx.HTTPTransport(uds=socket_path()), base_url="http://music", timeout=timeout) as client:
            response = client.request(method, path, json=payload)
            if response.is_error:
                raise ValueError(response.json().get("detail", "Music-Dienst hat die Anfrage abgelehnt."))
            return response.json()
    except (httpx.HTTPError, OSError) as exc:
        raise RuntimeError("Music-Dienst nicht erreichbar. Dienstinstallation prüfen.") from exc


class MusicService:
    def status(self):
        try:
            return runtime_request("GET", "/status", timeout=2)
        except RuntimeError:
            return {"status": "offline", "is_running": False, "settings": {}, "active_lights": [], "released": [],
                    "error": "Music-Dienst nicht erreichbar.", "session": ""}

    def start(self, **payload):
        if payload:
            raise ValueError("Start akzeptiert keine Geräteparameter. Bitte zuerst die Auswahl speichern.")
        if os.getenv("ROBOTERSTEVE_MONITOR_ONLY") == "1" or not load_agent_section("music").get("enabled", True):
            raise ValueError("Musiklicht ist deaktiviert.")
        return runtime_request("POST", "/command/start", {}, timeout=120)

    def stop(self, **payload):
        return runtime_request("POST", "/command/stop", {"reason": "manual"})

    def run(self, action="", **payload):
        if os.getenv("ROBOTERSTEVE_MONITOR_ONLY") == "1":
            raise ValueError("Beobachtungsmodus: Aktionen gesperrt.")
        if action == "configure":
            return runtime_request("POST", "/settings", payload)
        if action == "recover" and not payload:
            return runtime_request("POST", "/command/recover", {})
        raise ValueError("Erlaubte Aktionen: configure, recover.")

    def release(self, entities):
        # No worker dependency for ordinary light commands when no recovery/ownership exists.
        journal = Store().read("journal", {})
        if not set(entities).intersection(journal):
            return
        runtime_request("POST", "/command/release", {"entities": entities}, timeout=30)


music_service = MusicService()
