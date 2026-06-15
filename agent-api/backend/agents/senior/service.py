from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .behavior_agent import SeniorBehaviorAgent
from .device_mapping_service import DeviceMappingService


class SeniorService:
    def __init__(self, mapping: DeviceMappingService | None = None) -> None:
        self.enabled = True
        self.mapping = mapping or DeviceMappingService()
        self.behavior = SeniorBehaviorAgent(self.mapping)

    def status(self) -> dict[str, Any]:
        latest_assessment = self.behavior.latest()
        return {
            "status": "ready" if self.enabled else "disabled",
            "enabled": self.enabled,
            "message": "SeniorBehaviorAgent ist bereit.",
            "sensor_roles": self.mapping.roles(),
            "behavior_assessment": latest_assessment,
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
        result = self.behavior.run(dry_run=dry_run)
        return {
            **self.status(),
            "action": action or "behavior_assessment",
            "dry_run": dry_run,
            "result": result,
        }

    def latest_behavior(self) -> dict[str, Any] | None:
        return self.behavior.latest()

    def behavior_history(self, limit: int = 20) -> list[dict[str, Any]]:
        return self.behavior.history(limit=limit)

    def behavior_timeline_today(self) -> dict[str, Any]:
        return self.behavior.timeline_today()
