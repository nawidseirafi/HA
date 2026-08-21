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


_ENERGY_OUTLET_NOISE = (
    "outlet",
    "plug",
    "steckdose",
    "kaffee",
    "kaffeemaschine",
    "waschmaschine",
    "trockner",
    "spülmaschine",
    "spuelmaschine",
    "geschirrspüler",
    "geschirrspueler",
)


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
        ecotracker_api = _find_attr_state(states, ("power", "powerAvg", "energyCounterIn"))

        power = _first_number(
            _state_float(_find_state(states, ("sensor.ecotracker_power",), _is_current_power_sensor)),
            _attr_float(ecotracker_api, "power"),
        )
        power_avg = _first_number(
            _state_float(_find_state(states, ("sensor.ecotracker_power_avg",), lambda state: _is_current_power_sensor(state, average=True))),
            _attr_float(ecotracker_api, "powerAvg"),
        )
        phase_l1 = _first_number(
            _state_float(_find_state(states, ("sensor.ecotracker_power_phase1",), lambda state: _is_phase_power_sensor(state, "l1"))),
            _attr_float(ecotracker_api, "powerPhase1"),
        )
        phase_l2 = _first_number(
            _state_float(_find_state(states, ("sensor.ecotracker_power_phase2",), lambda state: _is_phase_power_sensor(state, "l2"))),
            _attr_float(ecotracker_api, "powerPhase2"),
        )
        phase_l3 = _first_number(
            _state_float(_find_state(states, ("sensor.ecotracker_power_phase3",), lambda state: _is_phase_power_sensor(state, "l3"))),
            _attr_float(ecotracker_api, "powerPhase3"),
        )
        import_state = _find_state(states, ("sensor.ecotracker_energy_in",), lambda state: _is_meter_energy_sensor(state, "import"))
        export_state = _find_state(states, ("sensor.ecotracker_energy_out",), lambda state: _is_meter_energy_sensor(state, "export"))
        import_total = _first_number(
            _state_float(import_state),
            _attr_float(ecotracker_api, "energyCounterIn", scale=0.001),
        )
        export_total = _first_number(
            _state_float(export_state),
            _attr_float(ecotracker_api, "energyCounterOut", scale=0.001),
        )
        if export_total is None and (power is not None or import_total is not None):
            export_total = 0.0
        today_import, today_export = _detect_daily_energy(states)

        status = "ok" if any(
            value is not None
            for value in (
                power,
                power_avg,
                phase_l1,
                phase_l2,
                phase_l3,
                import_total,
                export_total,
            )
        ) else "unavailable"

        return {
            "power": power,
            "power_avg": power_avg,
            "phases": {
                "l1": phase_l1,
                "l2": phase_l2,
                "l3": phase_l3,
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
                _find_state(states, ("sensor.ecotracker_power",), _is_current_power_sensor),
                _find_state(states, ("sensor.ecotracker_power_avg",), lambda state: _is_current_power_sensor(state, average=True)),
                _find_state(states, ("sensor.ecotracker_power_phase1",), lambda state: _is_phase_power_sensor(state, "l1")),
                _find_state(states, ("sensor.ecotracker_power_phase2",), lambda state: _is_phase_power_sensor(state, "l2")),
                _find_state(states, ("sensor.ecotracker_power_phase3",), lambda state: _is_phase_power_sensor(state, "l3")),
                import_state,
                export_state,
                ecotracker_api,
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


def _attr_float(state: dict[str, Any] | None, key: str, *, scale: float = 1.0) -> float | None:
    if not state:
        return None
    attrs = state.get("attributes")
    if not isinstance(attrs, dict):
        return None
    value = attrs.get(key)
    if value in {None, "", "unknown", "unavailable"}:
        return None
    try:
        return float(str(value).strip().replace(",", ".")) * scale
    except (TypeError, ValueError):
        return None


def _first_number(*values: float | None) -> float | None:
    for value in values:
        if isinstance(value, (int, float)):
            return float(value)
    return None


def _find_state(states: list[dict[str, Any]], exact_ids: tuple[str, ...], predicate: Any) -> dict[str, Any] | None:
    by_entity = {str(state.get("entity_id") or ""): state for state in states}
    for entity_id in exact_ids:
        state = by_entity.get(entity_id)
        if _state_float(state) is not None:
            return state
    candidates = [state for state in states if predicate(state) and _state_float(state) is not None and _energy_score(state) > 0]
    if not candidates:
        return None
    scored = sorted(((_energy_score(state), state) for state in candidates), key=lambda item: item[0], reverse=True)
    if len(scored) == 1 or scored[0][0] > scored[1][0]:
        return scored[0][1]
    return None


def _find_attr_state(states: list[dict[str, Any]], required_attrs: tuple[str, ...]) -> dict[str, Any] | None:
    exact = next((state for state in states if state.get("entity_id") == "sensor.ecotracker_api"), None)
    if exact:
        return exact
    for state in states:
        attrs = state.get("attributes") if isinstance(state.get("attributes"), dict) else {}
        if all(key in attrs for key in required_attrs):
            return state
    return None


def _is_current_power_sensor(state: dict[str, Any], average: bool = False) -> bool:
    if _domain(state) != "sensor":
        return False
    attrs = state.get("attributes") if isinstance(state.get("attributes"), dict) else {}
    unit = str(attrs.get("unit_of_measurement") or "").strip().lower()
    if str(attrs.get("device_class") or "").strip().lower() != "power" or unit not in {"w", "kw"}:
        return False
    haystack = _state_haystack(state)
    if _is_phase_haystack(haystack):
        return False
    if any(token in haystack for token in _ENERGY_OUTLET_NOISE):
        return False
    average_tokens = ("avg", "average", "durchschnitt", "mittelwert")
    if average:
        return any(token in haystack for token in average_tokens)
    return not any(token in haystack for token in average_tokens)


def _is_phase_power_sensor(state: dict[str, Any], phase: str) -> bool:
    if _domain(state) != "sensor":
        return False
    attrs = state.get("attributes") if isinstance(state.get("attributes"), dict) else {}
    unit = str(attrs.get("unit_of_measurement") or "").strip().lower()
    if str(attrs.get("device_class") or "").strip().lower() != "power" or unit not in {"w", "kw"}:
        return False
    haystack = _state_haystack(state)
    if any(token in haystack for token in _ENERGY_OUTLET_NOISE):
        return False
    phase_tokens = {
        "l1": ("l1", "phase1", "phase 1", "phase_1"),
        "l2": ("l2", "phase2", "phase 2", "phase_2"),
        "l3": ("l3", "phase3", "phase 3", "phase_3"),
    }
    return any(token in haystack for token in phase_tokens[phase])


def _is_meter_energy_sensor(state: dict[str, Any], direction: str) -> bool:
    if _domain(state) != "sensor":
        return False
    attrs = state.get("attributes") if isinstance(state.get("attributes"), dict) else {}
    unit = str(attrs.get("unit_of_measurement") or "").strip().lower()
    if str(attrs.get("device_class") or "").strip().lower() != "energy" or unit not in {"kwh", "kw h"}:
        return False
    haystack = _state_haystack(state)
    if any(token in haystack for token in _ENERGY_OUTLET_NOISE):
        return False
    if any(token in haystack for token in ("today", "daily", "day", "tag", "heute", "täglich", "taeglich")):
        return False
    direction_tokens = {
        "import": ("import", "in", "netzbezug", "bezug", "verbrauch"),
        "export": ("export", "out", "einspeis", "feed"),
    }
    return any(token in haystack for token in direction_tokens[direction])


def _domain(state: dict[str, Any]) -> str:
    return str(state.get("entity_id") or "").split(".", 1)[0]


def _state_haystack(state: dict[str, Any]) -> str:
    attrs = state.get("attributes") if isinstance(state.get("attributes"), dict) else {}
    return f"{state.get('entity_id') or ''} {attrs.get('friendly_name') or ''}".lower()


def _is_phase_haystack(haystack: str) -> bool:
    return any(token in haystack for token in ("l1", "l2", "l3", "phase1", "phase2", "phase3", "phase 1", "phase 2", "phase 3"))


def _energy_score(state: dict[str, Any]) -> int:
    haystack = _state_haystack(state)
    score = 0
    for token in ("ecotracker", "eco tracker", "power meter", "stromzähler", "stromzaehler", "energiezähler", "energiezaehler"):
        if token in haystack:
            score += 10
    for token in ("energy", "energie", "power", "leistung", "netz", "strom"):
        if token in haystack:
            score += 3
    return score


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
