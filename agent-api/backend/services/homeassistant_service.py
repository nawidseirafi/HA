from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import datetime, timezone
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
            or _resolve_secret(config.get("url"), env_values)
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

    def get_energy_overview(self) -> dict[str, Any]:
        states = self.get_states()
        by_entity = {str(state.get("entity_id") or ""): state for state in states}

        power = _state_float(by_entity.get("sensor.ecotracker_power"))
        power_avg = _state_float(by_entity.get("sensor.ecotracker_power_avg"))
        import_total = _state_float(by_entity.get("sensor.ecotracker_energy_in"))
        export_total = _state_float(by_entity.get("sensor.ecotracker_energy_out"))
        today_import, today_export = _detect_daily_energy(states)

        status = "ok" if any(
            value is not None
            for value in (
                power,
                power_avg,
                _state_float(by_entity.get("sensor.ecotracker_power_phase1")),
                _state_float(by_entity.get("sensor.ecotracker_power_phase2")),
                _state_float(by_entity.get("sensor.ecotracker_power_phase3")),
                import_total,
                export_total,
            )
        ) else "unavailable"

        return {
            "power": power,
            "power_avg": power_avg,
            "phases": {
                "l1": _state_float(by_entity.get("sensor.ecotracker_power_phase1")),
                "l2": _state_float(by_entity.get("sensor.ecotracker_power_phase2")),
                "l3": _state_float(by_entity.get("sensor.ecotracker_power_phase3")),
            },
            "energy": {
                "meter": {
                    "import_kwh": import_total,
                    "export_kwh": export_total,
                },
                "today": (
                    {
                        "import_kwh": today_import,
                        "export_kwh": today_export,
                    }
                    if today_import is not None or today_export is not None
                    else None
                ),
            },
            "updated_at": _latest_updated_at([
                by_entity.get("sensor.ecotracker_power"),
                by_entity.get("sensor.ecotracker_power_avg"),
                by_entity.get("sensor.ecotracker_power_phase1"),
                by_entity.get("sensor.ecotracker_power_phase2"),
                by_entity.get("sensor.ecotracker_power_phase3"),
                by_entity.get("sensor.ecotracker_energy_in"),
                by_entity.get("sensor.ecotracker_energy_out"),
            ]),
            "status": status,
            "pv_power": None,
            "battery_power": None,
            "battery_soc": None,
            "grid_power": power,
            "ev_charger_power": None,
            "cost_today": None,
            "forecast": None,
        }

    def get_calendars(self) -> list[dict[str, Any]]:
        if not self.configured():
            raise RuntimeError("Home Assistant URL oder Token ist nicht konfiguriert.")
        try:
            with httpx.Client(timeout=8) as client:
                response = client.get(self._api_url("/api/calendars"), headers=self._headers())
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            raise self._runtime_error("Home Assistant Kalender konnten nicht geladen werden", exc) from exc
        return data if isinstance(data, list) else []

    def get_calendar_events(self, entity_id: str, start: str, end: str) -> list[dict[str, Any]]:
        clean_entity_id = str(entity_id or "").strip()
        if not clean_entity_id:
            return []
        if not self.configured():
            raise RuntimeError("Home Assistant URL oder Token ist nicht konfiguriert.")
        try:
            with httpx.Client(timeout=8) as client:
                response = client.get(
                    self._api_url(f"/api/calendars/{clean_entity_id}"),
                    headers=self._headers(),
                    params={"start": start, "end": end},
                )
                if response.status_code == 404:
                    return []
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            raise self._runtime_error(f"Home Assistant Kalender {clean_entity_id} konnte nicht gelesen werden", exc) from exc
        return data if isinstance(data, list) else []

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

    def websocket_command(self, command: dict[str, Any], timeout: int = 30) -> dict[str, Any]:
        """Sendet einen Command an die HA Core WebSocket API (Port 8123, mit Auth)."""
        if not self.configured():
            raise RuntimeError("Home Assistant URL oder Token ist nicht konfiguriert.")
        return asyncio.run(self._websocket_command(command, timeout=timeout))

    async def _websocket_command(self, command: dict[str, Any], timeout: int = 30) -> dict[str, Any]:
        try:
            import websockets
        except Exception as exc:
            raise RuntimeError("Python-Paket 'websockets' ist fuer Home Assistant WebSocket nicht installiert.") from exc

        websocket_url = self._websocket_url()
        async with websockets.connect(websocket_url, open_timeout=timeout) as websocket:
            auth_required = json.loads(await asyncio.wait_for(websocket.recv(), timeout=timeout))
            if auth_required.get("type") != "auth_required":
                raise RuntimeError(f"Unerwartete Home Assistant WebSocket-Antwort: {auth_required}")

            await websocket.send(json.dumps({"type": "auth", "access_token": self.token}))
            auth_result = json.loads(await asyncio.wait_for(websocket.recv(), timeout=timeout))
            if auth_result.get("type") != "auth_ok":
                raise RuntimeError(f"Home Assistant WebSocket Auth fehlgeschlagen: {auth_result}")

            payload = dict(command)
            payload["id"] = 1
            await websocket.send(json.dumps(payload))
            response = json.loads(await asyncio.wait_for(websocket.recv(), timeout=timeout))
            return response if isinstance(response, dict) else {"success": False, "response": response}

    # ------------------------------------------------------------------
    # Matter Commissioning — Matter Server WebSocket (Port 5580, kein Auth)
    # ------------------------------------------------------------------

    def matter_commission(self, code: str, network_only: bool = False, timeout: int = 60) -> dict[str, Any]:
        """
        Commissioned ein neues Matter-Geraet ueber den Matter Server Add-on.

        Verbindet sich direkt mit dem Matter Server WebSocket auf Port 5580
        (kein HA-Auth erforderlich). Der Matter Server uebernimmt das BLE-
        Commissioning selbst, sofern ein BLE-Proxy konfiguriert ist.

        Args:
            code:         Numerischer Pairing-Code oder QR-Code-Payload.
            network_only: True = nur On-Network-Commissioning (kein BLE).
            timeout:      Timeout in Sekunden (Commissioning kann laenger dauern).
        """
        return asyncio.run(self._matter_commission(code, network_only=network_only, timeout=timeout))

    async def _matter_commission(
        self, code: str, network_only: bool = False, timeout: int = 60
    ) -> dict[str, Any]:
        try:
            import websockets
        except Exception as exc:
            raise RuntimeError(
                "Python-Paket 'websockets' ist fuer Matter WebSocket nicht installiert."
            ) from exc

        url = self._matter_websocket_url()
        try:
            async with websockets.connect(url, open_timeout=10) as ws:
                await ws.send(json.dumps({
                    "message_id": "1",
                    "command": "commission_with_code",
                    "args": {
                        "code": code,
                        "network_only": network_only,
                    },
                }))
                # Matter Server schickt ggf. mehrere Statusmessages — warten auf
                # die Antwort mit passender message_id
                async for raw in ws:
                    msg = json.loads(raw)
                    if msg.get("message_id") == "1":
                        return msg
        except Exception as exc:
            raise RuntimeError(
                f"Matter Server WebSocket-Fehler ({url}): {type(exc).__name__}: {exc}"
            ) from exc
        return {"success": False, "error": "Keine Antwort vom Matter Server erhalten."}

    # ------------------------------------------------------------------
    # Interne Hilfsmethoden
    # ------------------------------------------------------------------

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

    def _websocket_url(self) -> str:
        """HA Core WebSocket auf Port 8123 — mit Token-Auth."""
        parsed = urlparse(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise RuntimeError(
                f"Home Assistant URL ist ungueltig: {self.base_url!r}. "
                "Erwartet wird z.B. http://homeassistant.local:8123"
            )
        scheme = "wss" if parsed.scheme == "https" else "ws"
        # Hostname ohne Port verwenden, damit Port 8123 aus base_url erhalten bleibt
        return f"{scheme}://{parsed.netloc}/api/websocket"

    def _matter_websocket_url(self) -> str:
        """Matter Server WebSocket auf Port 5580 — kein Auth erforderlich."""
        parsed = urlparse(self.base_url)
        if not parsed.hostname:
            raise RuntimeError(
                f"Home Assistant URL ist ungueltig: {self.base_url!r}. "
                "Hostname konnte nicht ermittelt werden."
            )
        return f"ws://{parsed.hostname}:5580/ws"

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


def _state_float(state: dict[str, Any] | None) -> float | None:
    if not state:
        return None
    value = state.get("state")
    if value in {None, "", "unknown", "unavailable"}:
        return None
    try:
        return float(str(value).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None


def _latest_updated_at(states: list[dict[str, Any] | None]) -> str:
    latest: datetime | None = None
    for state in states:
        if not state:
            continue
        raw = state.get("last_updated") or state.get("last_changed")
        if not raw:
            continue
        try:
            parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            continue
        if latest is None or parsed > latest:
            latest = parsed
    return (latest or datetime.now(timezone.utc)).isoformat(timespec="seconds")


def _detect_daily_energy(states: list[dict[str, Any]]) -> tuple[float | None, float | None]:
    import_candidates: list[tuple[int, float]] = []
    export_candidates: list[tuple[int, float]] = []
    for state in states:
        value = _state_float(state)
        if value is None:
            continue
        attrs = state.get("attributes") if isinstance(state.get("attributes"), dict) else {}
        unit = str(attrs.get("unit_of_measurement") or "").strip().lower()
        device_class = str(attrs.get("device_class") or "").strip().lower()
        if device_class != "energy" or unit not in {"kwh", "kw h"}:
            continue
        haystack = f"{state.get('entity_id') or ''} {attrs.get('friendly_name') or ''}".lower()
        if not any(token in haystack for token in ("today", "daily", "day", "tag", "heute", "täglich", "taeglich")):
            continue
        if any(token in haystack for token in ("export", "out", "einspeis", "feed")):
            export_candidates.append((_daily_energy_score(haystack), value))
        elif any(token in haystack for token in ("import", "in", "netzbezug", "bezug", "verbrauch")):
            import_candidates.append((_daily_energy_score(haystack), value))
    return _best_daily_energy(import_candidates), _best_daily_energy(export_candidates)


def _daily_energy_score(haystack: str) -> int:
    score = 0
    for token in ("ecotracker", "energy", "energie"):
        if token in haystack:
            score += 2
    for token in ("today", "heute"):
        if token in haystack:
            score += 3
    for token in ("daily", "day", "tag", "täglich", "taeglich"):
        if token in haystack:
            score += 1
    return score


def _best_daily_energy(candidates: list[tuple[int, float]]) -> float | None:
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    if len(candidates) == 1 or candidates[0][0] > candidates[1][0]:
        return candidates[0][1]
    return None
