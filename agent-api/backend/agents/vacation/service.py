import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.config import load_agent_section, resolve_api_path
from backend.services.core.ha_client import HomeAssistantClient

logger = logging.getLogger(__name__)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class VacationService:
    def __init__(self, ha_client: HomeAssistantClient | None = None) -> None:
        self._ha_client = ha_client
        self._last_run: dict[str, Any] | None = None
        self._last_error: str | None = None

    def config(self) -> dict[str, Any]:
        config = load_agent_section("vacation")
        return {
            "enabled": bool(config.get("enabled", False)),
            "mode_entity": config.get("mode_entity", "input_boolean.vacation_mode"),
            "log_path": str(self.log_path()),
        }

    def status(self) -> dict[str, Any]:
        config = self.config()
        vacation_mode = None
        current_status = "disabled" if not config["enabled"] else "idle"
        error = self._last_error
        if config["enabled"]:
            try:
                vacation_mode = self.get_vacation_mode()
            except Exception as exc:
                current_status = "error"
                error = str(exc)
        return {
            "enabled": config["enabled"],
            "current_status": current_status,
            "vacation_mode": vacation_mode,
            "mode_entity": config["mode_entity"],
            "last_run": self._last_run,
            "last_error": error,
            "log_path": config["log_path"],
        }

    def run(self, dry_run: bool = True) -> dict[str, Any]:
        config = self.config()
        started_at = utc_now()
        if not config["enabled"]:
            result = {
                "status": "disabled",
                "message": "Vacation-Agent ist deaktiviert.",
                "dry_run": dry_run,
                "started_at": started_at,
            }
            self._last_run = result
            return result

        try:
            vacation_mode = self.get_vacation_mode()
            result = {
                "status": "ok",
                "message": "Vacation-Agent bereit.",
                "dry_run": dry_run,
                "vacation_mode": vacation_mode,
                "mode_entity": config["mode_entity"],
                "started_at": started_at,
                "finished_at": utc_now(),
                "actions": [],
            }
            self._last_error = None
            self._last_run = result
            self._log(f"run dry_run={dry_run} vacation_mode={vacation_mode}")
            return result
        except Exception as exc:
            self._last_error = str(exc)
            logger.exception("Vacation-Agent-Lauf fehlgeschlagen.")
            result = {
                "status": "error",
                "message": str(exc),
                "dry_run": dry_run,
                "started_at": started_at,
                "finished_at": utc_now(),
                "actions": [],
            }
            self._last_run = result
            return result

    def get_vacation_mode(self) -> bool:
        mode_entity = self.config()["mode_entity"]
        state = self._ha().get_state(mode_entity)
        return state.get("state") == "on"

    def log_path(self) -> Path:
        config = load_agent_section("vacation")
        return resolve_api_path(config.get("log_path"), "logs/vacation.log")

    def _ha(self) -> HomeAssistantClient:
        if self._ha_client is None:
            self._ha_client = HomeAssistantClient()
        return self._ha_client

    def _log(self, message: str) -> None:
        path = self.log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"[{timestamp}] {message}\n")
