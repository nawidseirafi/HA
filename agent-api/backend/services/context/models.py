from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class PresenceState(str, Enum):
    UNKNOWN = "UNKNOWN"
    HOME = "HOME"
    AWAY = "AWAY"
    SHORT_AWAY = "SHORT_AWAY"
    COMING_HOME = "COMING_HOME"
    LEAVING = "LEAVING"


class GarageState(str, Enum):
    NONE = "NONE"
    KEEP_OPEN = "KEEP_OPEN"
    READY_TO_CLOSE = "READY_TO_CLOSE"
    READY_TO_OPEN = "READY_TO_OPEN"


class HouseState(str, Enum):
    DAY = "DAY"
    EVENING = "EVENING"
    RELAXING = "RELAXING"
    OUTSIDE = "OUTSIDE"
    GUESTS = "GUESTS"
    PREPARING_SLEEP = "PREPARING_SLEEP"
    SLEEPING = "SLEEPING"


class VacationState(str, Enum):
    NORMAL = "NORMAL"
    VACATION = "VACATION"


class TransitionState(str, Enum):
    STABLE = "STABLE"
    TRANSITION = "TRANSITION"


@dataclass(frozen=True)
class EntitySignal:
    entity_id: str
    state: str
    name: str = ""
    device_class: str = ""
    updated_at: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ContextSnapshot:
    presence: PresenceState
    departure: PresenceState
    garage: GarageState
    house: HouseState
    sleep: HouseState
    vacation: VacationState
    transition: TransitionState
    guest: bool
    confidence: float
    updated_at: str
    summary: str = ""
    reason: str = ""
    signals: dict[str, Any] = field(default_factory=dict)
    active_rules: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def as_dict(self, include_debug: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "presence": self.presence.value,
            "departure": self.departure.value,
            "garage": self.garage.value,
            "house": self.house.value,
            "sleep": self.sleep.value,
            "vacation": self.vacation.value,
            "transition": self.transition.value,
            "guest": self.guest,
            "confidence": self.confidence,
            "updated_at": self.updated_at,
            "summary": self.summary,
            "reason": self.reason,
        }
        if include_debug:
            payload["signals"] = self.signals
            payload["active_rules"] = self.active_rules
            payload["metrics"] = self.metrics
        return payload


@dataclass(frozen=True)
class DepartureContext:
    presence: PresenceState
    departure: PresenceState
    garage: GarageState
    elapsed_seconds: int | None = None
    away_seconds: int | None = None
    person_home: bool | None = None
    garage_open: bool = False

    def as_metrics(self) -> dict[str, Any]:
        return {
            "elapsed_seconds": self.elapsed_seconds,
            "away_seconds": self.away_seconds,
            "person_home": self.person_home,
            "garage_open": self.garage_open,
        }
