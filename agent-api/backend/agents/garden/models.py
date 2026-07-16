from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


GardenStatus = Literal["healthy", "dry", "critically_dry", "wet", "unknown", "error"]
GardenDecision = Literal["no_action", "monitor", "irrigate", "stop_irrigation", "blocked"]
MowerStatus = Literal["parked", "mowing", "starting", "returning", "paused", "error", "unavailable", "unknown"]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class EntityBinding:
    entity_id: str = ""
    source: str = "unresolved"
    available: bool = False
    state: Any = None
    name: str = ""
    last_updated: str | None = None
    domain: str = ""

    def public_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "source": self.source,
            "available": self.available,
            "state": self.state,
            "name": self.name,
            "last_updated": self.last_updated,
            "domain": self.domain,
        }


@dataclass(frozen=True)
class GardenReason:
    code: str
    message: str

    def public_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


@dataclass(frozen=True)
class ZoneEvaluationInput:
    zone_id: str
    zone_name: str
    moisture: float | None = None
    soil_temperature: float | None = None
    battery: float | None = None
    soil_warning: bool | None = None
    moisture_available: bool = False
    moisture_last_updated: str | None = None
    irrigation_active: bool | None = None
    irrigation_available: bool = False
    mower_status: MowerStatus = "unknown"
    rain_active: bool | None = None
    rain_probability: float | None = None
    last_irrigation_ended_at: str | None = None
    open_irrigation_run: dict[str, Any] | None = None
    config: dict[str, Any] = field(default_factory=dict)
    control_enabled: bool = False
    agent_enabled: bool = True
    evaluated_at: str = field(default_factory=utc_now)


@dataclass(frozen=True)
class ZoneDecision:
    zone_id: str
    status: GardenStatus
    decision: GardenDecision
    recommended_duration_minutes: int | None
    apply_allowed: bool
    reasons: list[GardenReason]
    blocks: list[GardenReason]
    evaluated_at: str
    input_snapshot: dict[str, Any] = field(default_factory=dict)

    def public_dict(self) -> dict[str, Any]:
        return {
            "zone_id": self.zone_id,
            "status": self.status,
            "decision": self.decision,
            "recommended_duration_minutes": self.recommended_duration_minutes,
            "apply_allowed": self.apply_allowed,
            "reasons": [item.public_dict() for item in self.reasons],
            "blocks": [item.public_dict() for item in self.blocks],
            "evaluated_at": self.evaluated_at,
            "input_snapshot": self.input_snapshot,
        }


def normalize_mower_status(raw: Any) -> MowerStatus:
    text = str(raw or "").strip().lower()
    if text in {"docked", "parked", "charging", "idle"}:
        return "parked"
    if text in {"mowing", "mow", "cleaning"}:
        return "mowing"
    if text in {"starting", "start_mowing", "pending"}:
        return "starting"
    if text in {"returning", "returning_home", "return_to_base"}:
        return "returning"
    if text in {"paused", "pause"}:
        return "paused"
    if text in {"error", "problem", "fault"}:
        return "error"
    if text in {"unavailable"}:
        return "unavailable"
    return "unknown"
