import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import yaml

from backend.paths import BACKEND_DIR, API_DIR, PROJECT_DIR, API_CONFIG_PATH, FRONTEND_DIST, LOG_DIR, ENV_PATH



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
    keys = [
        text,
        text.upper(),
        text.replace("-", "_"),
        text.replace("-", "_").upper(),
    ]
    for key in keys:
        resolved = os.getenv(key) or env_values.get(key)
        if resolved:
            return resolved
    if re.fullmatch(r"[A-Z0-9_-]+", text):
        return ""
    return text


class HomeAssistantService:
    def __init__(self) -> None:
        env_values = _read_env_file(API_DIR / ".env")
        config = _read_yaml(API_DIR / "config.yaml").get("home_assistant", {})
        self.base_url = (
            os.getenv("HA_URL")
            or env_values.get("HA_URL")
            or str(config.get("url") or "").strip()
        ).rstrip("/")
        self.token = (
            os.getenv("HA_TOKEN")
            or env_values.get("HA_TOKEN")
            or _resolve_secret(config.get("token"), env_values)
        )

    def configured(self) -> bool:
        return bool(self.base_url and self.token)

    def get_states(self) -> list[dict[str, Any]]:
        if not self.configured():
            raise RuntimeError("Home Assistant URL oder Token ist nicht konfiguriert.")
        try:
            with httpx.Client(timeout=8) as client:
                response = client.get(self._api_url("/api/states"), headers=self._headers())
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            raise self._runtime_error("Home Assistant States konnten nicht geladen werden", exc) from exc
        return data if isinstance(data, list) else []

    def render_template(self, template: str) -> str:
        if not self.configured():
            raise RuntimeError("Home Assistant URL oder Token ist nicht konfiguriert.")
        try:
            with httpx.Client(timeout=8) as client:
                response = client.post(
                    self._api_url("/api/template"),
                    headers={**self._headers(), "Content-Type": "application/json"},
                    json={"template": template},
                )
                response.raise_for_status()
                return response.text
        except Exception as exc:
            raise self._runtime_error("Home Assistant Template konnte nicht gerendert werden", exc) from exc

    def get_state(self, entity_id: str | None) -> dict[str, Any] | None:
        entity = (entity_id or "").strip()
        if not entity:
            return None
        if not self.configured():
            raise RuntimeError("Home Assistant URL oder Token ist nicht konfiguriert.")
        try:
            with httpx.Client(timeout=8) as client:
                response = client.get(self._api_url(f"/api/states/{entity}"), headers=self._headers())
                if response.status_code == 404:
                    return None
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            raise self._runtime_error(f"Home Assistant konnte {entity} nicht lesen", exc) from exc
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

    def call_service(self, domain: str, service: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.configured():
            raise RuntimeError("Home Assistant URL oder Token ist nicht konfiguriert.")
        clean_domain = str(domain or "").strip()
        clean_service = str(service or "").strip()
        if not clean_domain or not clean_service:
            raise RuntimeError("Home Assistant Service ist unvollstaendig.")
        try:
            with httpx.Client(timeout=8) as client:
                response = client.post(
                    self._api_url(f"/api/services/{clean_domain}/{clean_service}"),
                    headers={**self._headers(), "Content-Type": "application/json"},
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            raise self._runtime_error("Home Assistant Service-Aufruf fehlgeschlagen", exc) from exc
        return {"ok": True, "result": data}

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
        }

    def _api_url(self, path: str) -> str:
        parsed = urlparse(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise RuntimeError(
                f"Home Assistant URL ist ungueltig: {self.base_url!r}. "
                "Erwartet wird z.B. http://homeassistant.local:8123"
            )
        return f"{self.base_url}{path}"

    def _runtime_error(self, message: str, exc: Exception) -> RuntimeError:
        if isinstance(exc, RuntimeError):
            return RuntimeError(f"{message}: {exc}")
        if isinstance(exc, httpx.HTTPStatusError):
            status = exc.response.status_code
            body = exc.response.text[:200]
            return RuntimeError(f"{message}: HTTP {status} von {self.base_url}. {body}")
        if isinstance(exc, httpx.InvalidURL):
            return RuntimeError(f"{message}: Home Assistant URL ist ungueltig ({self.base_url!r}).")
        if isinstance(exc, httpx.HTTPError):
            return RuntimeError(f"{message}: {type(exc).__name__}: {exc}")
        return RuntimeError(f"{message}: {type(exc).__name__}: {exc}")
