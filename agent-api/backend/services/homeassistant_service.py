import os
import re
from pathlib import Path
from typing import Any

import httpx
import yaml

from backend.paths import AI_AGENT_DIR


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


def _resolve_secret(value: Any, env_values: dict[str, str]) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    resolved = os.getenv(text) or env_values.get(text) or os.getenv(text.upper()) or env_values.get(text.upper())
    if resolved:
        return resolved
    if re.fullmatch(r"[A-Z0-9_-]+", text):
        return ""
    return text


class HomeAssistantService:
    def __init__(self) -> None:
        env_values = _read_env_file(AI_AGENT_DIR / ".env")
        config = _read_yaml(AI_AGENT_DIR / "config.yaml").get("home_assistant", {})
        self.base_url = (
            os.getenv("HOME_ASSISTANT_URL")
            or env_values.get("HOME_ASSISTANT_URL")
            or str(config.get("url") or "").strip()
        ).rstrip("/")
        self.token = (
            os.getenv("HOME_ASSISTANT_TOKEN")
            or env_values.get("HOME_ASSISTANT_TOKEN")
            or _resolve_secret(config.get("token"), env_values)
        )

    def configured(self) -> bool:
        return bool(self.base_url and self.token)

    def get_states(self) -> list[dict[str, Any]]:
        if not self.configured():
            raise RuntimeError("Home Assistant URL oder Token ist nicht konfiguriert.")
        with httpx.Client(timeout=8) as client:
            response = client.get(f"{self.base_url}/api/states", headers=self._headers())
            response.raise_for_status()
            data = response.json()
        return data if isinstance(data, list) else []

    def get_state(self, entity_id: str | None) -> dict[str, Any] | None:
        entity = (entity_id or "").strip()
        if not entity:
            return None
        if not self.configured():
            raise RuntimeError("Home Assistant URL oder Token ist nicht konfiguriert.")
        try:
            with httpx.Client(timeout=8) as client:
                response = client.get(f"{self.base_url}/api/states/{entity}", headers=self._headers())
                if response.status_code == 404:
                    return None
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Home Assistant konnte {entity} nicht lesen: {exc}") from exc
        return data if isinstance(data, dict) else None

    def fetch_entity_state(self, entity_id: str | None) -> dict[str, Any] | None:
        try:
            state = self.get_state(entity_id)
        except Exception:
            return None
        if not state:
            return None
        value = state.get("state")
        if value in (None, "", "unknown", "unavailable"):
            return None
        return state

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
        }
