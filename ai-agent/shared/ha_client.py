import requests
import yaml
import logging
import os
import re
from pathlib import Path
from urllib.parse import urlparse
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent


def _resolve_config_value(value: str | None) -> str:
    if not value:
        return ""
    text = str(value).strip()
    resolved = os.getenv(text) or os.getenv(text.upper())
    if resolved:
        return resolved.strip()
    if re.fullmatch(r"[A-Z0-9_-]+", text):
        return ""
    return text


class HomeAssistantClient:
    def __init__(self, config_path="config.yaml"):
        load_dotenv(BASE_DIR / ".env")
        config_file = Path(config_path)
        if not config_file.is_absolute():
            config_file = BASE_DIR / config_file

        with config_file.open("r") as f:
            config = yaml.safe_load(f)

        if not config:
            raise ValueError("config.yaml ist leer oder ungültig")

        self.base_url = _resolve_config_value(config["home_assistant"].get("url", "")).rstrip("/")
        self.token = _resolve_config_value(config["home_assistant"].get("token", ""))
        self._validate_config()

        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def _validate_config(self):
        if not self.base_url:
            raise ValueError("Home Assistant URL fehlt. Setze HA_URL in ai-agent/.env oder eine echte URL in config.yaml.")
        parsed = urlparse(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(
                f"Home Assistant URL ist ungueltig: {self.base_url!r}. "
                "Erwartet wird z.B. http://homeassistant.local:8123"
            )
        if not self.token:
            raise ValueError("Home Assistant Token fehlt. Setze HA_TOKEN in ai-agent/.env oder eine echte Token-Referenz in config.yaml.")

    def get_states(self):
        url = f"{self.base_url}/api/states"
        r = requests.get(url, headers=self.headers, timeout=10)
        r.raise_for_status()
        return r.json()

    def get_state(self, entity_id):
        url = f"{self.base_url}/api/states/{entity_id}"
        r = requests.get(url, headers=self.headers, timeout=10)
        r.raise_for_status()
        return r.json()

    def call_service(self, domain, service, data):
        url = f"{self.base_url}/api/services/{domain}/{service}"
        r = requests.post(url, headers=self.headers, json=data, timeout=10)
        r.raise_for_status()
        return r.json()

    def persistent_notification(self, title, message, notification_id=None):
        data = {
            "title": title,
            "message": message,
        }
        if notification_id:
            data["notification_id"] = notification_id
        logging.info("Sende Home-Assistant-Benachrichtigung: %s", title)
        return self.call_service("persistent_notification", "create", data)

    def notify(self, service, title, message, data=None):
        service_name = service.replace("notify.", "")
        payload = {
            "title": title,
            "message": message,
        }
        if data:
            payload["data"] = data
        logging.info("Sende Home-Assistant-Mobile-Notification: %s", title)
        return self.call_service("notify", service_name, payload)

    def turn_on(self, entity_id):
        domain = entity_id.split(".")[0]
        logging.info(f"Schalte ein: {entity_id}")
        return self.call_service(domain, "turn_on", {"entity_id": entity_id})

    def turn_off(self, entity_id):
        domain = entity_id.split(".")[0]
        logging.info(f"Schalte aus: {entity_id}")
        return self.call_service(domain, "turn_off", {"entity_id": entity_id})

    def set_cover_position(self, entity_id, position):
        logging.info(f"Setze Jalousie: {entity_id} auf {position}%")
        return self.call_service(
            "cover",
            "set_cover_position",
            {
                "entity_id": entity_id,
                "position": position,
            },
        )
