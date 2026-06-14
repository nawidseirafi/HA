from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .device_mapping_service import DeviceMappingService


class SeniorService:
    def __init__(self, mapping: DeviceMappingService | None = None) -> None:
        self.enabled = True
        self.mapping = mapping or DeviceMappingService()

    def status(self) -> dict[str, Any]:
        return {
            "status": "ready" if self.enabled else "disabled",
            "enabled": self.enabled,
            "message": "Senior-Agent Placeholder ist bereit.",
            "sensor_roles": self.mapping.roles(),
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }

    def enable(self) -> dict[str, Any]:
        self.enabled = True
        return self.status()

    def disable(self) -> dict[str, Any]:
        self.enabled = False
        return self.status()

    def toggle(self) -> dict[str, Any]:
        self.enabled = not self.enabled
        return self.status()

    def run(self, dry_run: bool = True, action: str | None = None) -> dict[str, Any]:
        return {
            **self.status(),
            "action": action or "daily_check",
            "dry_run": dry_run,
        }
