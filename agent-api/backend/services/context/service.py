from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from backend.config import load_global_config
from backend.services.context.models import (
    ContextSnapshot,
    DepartureContext,
    EntitySignal,
    GarageState,
    HouseState,
    PresenceState,
    TransitionState,
    VacationState,
)
from backend.services.context.store import ContextStore
from backend.services.homeassistant_service import HomeAssistantService


HOME_STATES = {"home", "on", "true", "present", "detected", "occupied"}
AWAY_STATES = {"not_home", "away", "off", "false", "clear", "idle", "standby"}
OPEN_STATES = {"open", "opening", "on"}
CLOSED_STATES = {"closed", "closing", "off"}
ACTIVE_STATES = {"on", "playing", "home", "open", "detected", "occupied"}


class ContextService:
    _default_instance: "ContextService | None" = None

    def __init__(
        self,
        ha_service: HomeAssistantService | None = None,
        store: ContextStore | None = None,
        now_provider: Callable[[], datetime] | None = None,
        database_path: str | Path | None = None,
    ) -> None:
        self.ha_service = ha_service or HomeAssistantService()
        config = load_global_config().get("context") or {}
        self.config = config if isinstance(config, dict) else {}
        self.store = store or ContextStore(database_path or self.config.get("database_path") or "data/context/context.db")
        self.now_provider = now_provider or (lambda: datetime.now(timezone.utc))
        self.departure_window_seconds = int(self.config.get("departure_window_seconds") or 300)
        self.short_away_return_seconds = int(self.config.get("short_away_return_seconds") or 600)
        self.long_away_seconds = int(self.config.get("long_away_seconds") or 7200)
        self.garage_open_after_away_seconds = int(self.config.get("garage_open_after_away_seconds") or self.short_away_return_seconds)
        self.sleep_quiet_minutes = int(self.config.get("sleep_quiet_minutes") or 10)
        self._memory: dict[str, Any] = {}
        self._last_snapshot: ContextSnapshot | None = None

    @classmethod
    def default(cls) -> "ContextService":
        if cls._default_instance is None:
            cls._default_instance = cls()
        return cls._default_instance

    @classmethod
    def current(cls) -> ContextSnapshot:
        return cls.default().evaluate_current()

    def evaluate_current(self, persist: bool = True) -> ContextSnapshot:
        now = self._now()
        try:
            states = self.ha_service.get_states()
            ha_error = None
        except Exception as exc:
            states = []
            ha_error = str(exc)
        snapshot = self.evaluate(states, now=now, ha_error=ha_error)
        self._last_snapshot = snapshot
        if persist:
            self.store.save_snapshot(snapshot.as_dict(include_debug=True))
        return snapshot

    def status(self) -> dict[str, Any]:
        return self.evaluate_current().as_dict()

    def history(self, limit: int = 100) -> dict[str, Any]:
        return {"items": self.store.history(limit=limit)}

    def debug(self) -> dict[str, Any]:
        snapshot = self.evaluate_current()
        return {
            **snapshot.as_dict(include_debug=True),
            "database": {"path": str(self.store.path), "counts": self.store.table_counts()},
            "config": self._public_config(),
        }

    def evaluate(self, states: list[dict[str, Any]], now: datetime | None = None, ha_error: str | None = None) -> ContextSnapshot:
        now = now or self._now()
        by_entity = {str(item.get("entity_id") or ""): item for item in states if isinstance(item, dict)}
        signals = self._collect_signals(states, by_entity)
        active_rules: list[str] = []
        metrics: dict[str, Any] = {"ha_error": ha_error}

        vacation = self._vacation_state(signals, active_rules)
        departure_context = self._departure_context(signals, now, active_rules)
        presence = departure_context.presence
        departure = departure_context.departure
        garage = departure_context.garage
        departure_metrics = departure_context.as_metrics()
        house, sleep, guest, house_metrics = self._house_context(signals, now, active_rules)
        transition = self._transition_state(presence, house)
        confidence = self._confidence(signals, departure_metrics, house_metrics, ha_error)

        metrics["departure"] = departure_metrics
        metrics["house"] = house_metrics
        if ha_error:
            active_rules.append("home_assistant_unavailable")
        summary, reason = self._summary_reason(
            presence=presence,
            departure=departure,
            garage=garage,
            house=house,
            sleep=sleep,
            guest=guest,
            transition=transition,
            signals=signals,
            metrics=metrics,
        )

        return ContextSnapshot(
            presence=presence,
            departure=departure,
            garage=garage,
            house=house,
            sleep=sleep,
            vacation=vacation,
            transition=transition,
            guest=guest,
            confidence=confidence,
            updated_at=now.astimezone(timezone.utc).isoformat(timespec="seconds"),
            summary=summary,
            reason=reason,
            signals={key: self._signal_payload(value) for key, value in signals.items()},
            active_rules=active_rules,
            metrics=metrics,
        )

    def _summary_reason(
        self,
        presence: PresenceState,
        departure: PresenceState,
        garage: GarageState,
        house: HouseState,
        sleep: HouseState,
        guest: bool,
        transition: TransitionState,
        signals: dict[str, EntitySignal | list[EntitySignal] | None],
        metrics: dict[str, Any],
    ) -> tuple[str, str]:
        if garage == GarageState.READY_TO_OPEN:
            return (
                "Ich glaube, du kommst nach Hause. Die Garage ist bereit zum Oeffnen.",
                "ContextService meldet Heimkehr nach laengerer Abwesenheit und die Garage ist geschlossen.",
            )
        if garage == GarageState.READY_TO_CLOSE:
            return (
                "Ich glaube, du bist wirklich weg. Die Garage ist bereit zum Schliessen.",
                "Die Person ist nach dem Beobachtungsfenster weiter abwesend.",
            )
        if garage == GarageState.KEEP_OPEN and presence in {PresenceState.LEAVING, PresenceState.SHORT_AWAY}:
            elapsed = (metrics.get("departure") or {}).get("elapsed_seconds")
            if elapsed is not None:
                minutes = max(1, round(float(elapsed) / 60))
                return (
                    "Ich warte noch, bevor ich die Garage schliesse.",
                    f"Abfahrt wurde vor etwa {minutes} Minute(n) erkannt; das Kurzabwesenheitsfenster ist noch relevant.",
                )
            return (
                "Ich warte noch, bevor ich die Garage schliesse.",
                "Der ContextService prueft gerade, ob es nur eine Kurzabwesenheit ist.",
            )
        if guest or house == HouseState.GUESTS:
            return (
                "Ich habe Gaeste erkannt.",
                "Mehrere Aktivitaets- und Oeffnungssignale sprechen gegen eine Nachtautomatik.",
            )
        if house == HouseState.OUTSIDE:
            return (
                "Ich glaube, dass du noch draussen sitzt.",
                "Terrassenpraesenz oder Terrassentuer blockiert den Nachtkontext.",
            )
        if sleep == HouseState.SLEEPING:
            return (
                "Ich glaube, dass das Haus jetzt schlaeft.",
                "Schlafkontext ist stabil und der Rest des Hauses wirkt ruhig.",
            )
        if sleep == HouseState.PREPARING_SLEEP or house == HouseState.PREPARING_SLEEP:
            return (
                "Ich glaube, dass du gerade schlafen gehst.",
                "Schlafzimmer- und Ruhe-Signale deuten auf Schlafvorbereitung hin.",
            )
        if house == HouseState.RELAXING:
            return (
                "Das Haus befindet sich im Entspannungsmodus.",
                "Wohnzimmer, Medien oder Lichtsignale sprechen noch gegen den Schlafkontext.",
            )
        if presence == PresenceState.COMING_HOME:
            return (
                "Ich glaube, du kommst gerade nach Hause.",
                "Die Person wurde nach einer Abwesenheit wieder zuhause erkannt.",
            )
        if presence == PresenceState.AWAY:
            return (
                "Ich glaube, dass niemand zuhause ist.",
                "Die Person wirkt abwesend.",
            )
        if transition == TransitionState.TRANSITION:
            return (
                "Ich beobachte gerade einen Uebergang.",
                "Der aktuelle Kontext ist noch nicht vollstaendig stabil.",
            )
        if house == HouseState.EVENING:
            return (
                "Ich beobachte den Abendmodus.",
                "Die Uhrzeit spricht fuer Abend, aber keine staerkere Schlaf- oder Gaeste-Regel ist aktiv.",
            )
        if house == HouseState.DAY:
            return (
                "Das Haus befindet sich im Tagesmodus.",
                "Es gibt keinen Hinweis auf Schlaf, Gaeste oder Abwesenheitsuebergaenge.",
            )
        return (
            "Ich lese gerade den Hauskontext.",
            "Der ContextService hat noch keinen spezifischeren Zustand priorisiert.",
        )

    def _departure_context(
        self,
        signals: dict[str, EntitySignal | list[EntitySignal] | None],
        now: datetime,
        active_rules: list[str],
    ) -> DepartureContext:
        person_home = self._is_home(signals.get("person"))
        garage_open = self._is_open(signals.get("garage_door"))
        mobility_home = person_home
        mobility_source = "person"
        previous_mobility_home = self._memory.get("mobility_home")
        departure_started_at = self._memory.get("departure_started_at")
        away_started_at = self._memory.get("away_started_at")
        last_away_at = self._memory.get("last_away_at")

        if mobility_home and previous_mobility_home is False and last_away_at:
            away_seconds = max(0, int((now - last_away_at).total_seconds()))
            self._memory["last_return_at"] = now
            self._memory["departure_started_at"] = None
            self._memory["away_started_at"] = None
            if away_seconds <= self.short_away_return_seconds:
                active_rules.append(f"{mobility_source}_returned_within_short_away_window")
                presence = PresenceState.SHORT_AWAY
                departure = PresenceState.SHORT_AWAY
                garage = GarageState.KEEP_OPEN if garage_open else GarageState.NONE
            elif away_seconds >= self.garage_open_after_away_seconds:
                rule = "long_absence" if away_seconds >= self.long_away_seconds else "garage_open_window"
                active_rules.append(f"{mobility_source}_returned_after_{rule}")
                presence = PresenceState.COMING_HOME
                departure = PresenceState.COMING_HOME
                garage = GarageState.READY_TO_OPEN
            else:
                active_rules.append(f"{mobility_source}_returned_after_medium_absence")
                presence = PresenceState.COMING_HOME
                departure = PresenceState.COMING_HOME
                garage = GarageState.KEEP_OPEN if garage_open else GarageState.NONE
            self._memory["mobility_home"] = mobility_home
            self._memory["mobility_source"] = mobility_source
            return DepartureContext(
                presence=presence,
                departure=departure,
                garage=garage,
                away_seconds=away_seconds,
                person_home=person_home,
                garage_open=garage_open,
            )

        if mobility_home is False and previous_mobility_home is not False:
            departure_started_at = now
            last_away_at = now
            self._memory["departure_started_at"] = departure_started_at
            self._memory["last_away_at"] = last_away_at
            active_rules.append(f"{mobility_source}_left_home_departure_window_started")

        if mobility_home is False:
            if departure_started_at is None:
                departure_started_at = now
                self._memory["departure_started_at"] = departure_started_at
            elapsed = max(0, int((now - departure_started_at).total_seconds()))
            self._memory["last_away_at"] = self._memory.get("last_away_at") or departure_started_at
            if elapsed < self.departure_window_seconds:
                presence = PresenceState.LEAVING
                departure = PresenceState.LEAVING
                garage = GarageState.KEEP_OPEN if garage_open else GarageState.NONE
                active_rules.append("departure_observation_window_active")
            else:
                if away_started_at is None:
                    self._memory["away_started_at"] = now
                truly_away = person_home is False
                presence = PresenceState.AWAY if truly_away else PresenceState.LEAVING
                departure = PresenceState.AWAY if truly_away else PresenceState.LEAVING
                garage = GarageState.READY_TO_CLOSE if garage_open and truly_away else GarageState.NONE
                active_rules.append(f"departure_window_elapsed_{mobility_source}_still_away")
            self._memory["mobility_home"] = mobility_home
            self._memory["mobility_source"] = mobility_source
            return DepartureContext(
                presence=presence,
                departure=departure,
                garage=garage,
                elapsed_seconds=elapsed,
                person_home=person_home,
                garage_open=garage_open,
            )

        self._memory["mobility_home"] = mobility_home
        self._memory["mobility_source"] = mobility_source
        if person_home:
            self._memory["departure_started_at"] = None
            active_rules.append("home_presence_detected")
            return DepartureContext(
                presence=PresenceState.HOME,
                departure=PresenceState.HOME,
                garage=GarageState.KEEP_OPEN if garage_open else GarageState.NONE,
                person_home=person_home,
                garage_open=garage_open,
            )
        active_rules.append("presence_unknown")
        return DepartureContext(
            presence=PresenceState.UNKNOWN,
            departure=PresenceState.UNKNOWN,
            garage=GarageState.NONE,
            person_home=person_home,
            garage_open=garage_open,
        )

    def _house_context(
        self,
        signals: dict[str, EntitySignal | list[EntitySignal] | None],
        now: datetime,
        active_rules: list[str],
    ) -> tuple[HouseState, HouseState, bool, dict[str, Any]]:
        local = now.astimezone()
        hour = local.hour + local.minute / 60
        bedroom_active = self._is_active(signals.get("bedroom_presence")) or self._is_on(signals.get("bedroom_light"))
        living_active = self._is_active(signals.get("living_presence")) or self._is_on(signals.get("living_light"))
        terrace_active = self._is_active(signals.get("terrace_presence")) or self._is_open(signals.get("terrace_door"))
        tv_active = self._is_active(signals.get("tv"))
        music_active = self._is_active(signals.get("music"))
        nuki_locked = self._state_value(signals.get("nuki")) in {"locked", "locking"}
        motion_count = self._active_count(signals.get("motion"))
        opening_count = self._active_count(signals.get("openings"))
        active_presence_count = sum(1 for item in (bedroom_active, living_active, terrace_active) if item)

        guest_score = 0
        guest_score += 2 if active_presence_count >= 2 else 0
        guest_score += 1 if opening_count >= 2 else 0
        guest_score += 2 if living_active and hour >= 21 else 0
        guest_score += 1 if terrace_active else 0
        guest_score += 1 if self._lights_on_count(signals) >= 3 else 0
        guests = guest_score >= 4

        rest_quiet = not living_active and not terrace_active and not tv_active and not music_active and motion_count == 0
        late = hour >= 21.5 or hour < 5

        if guests:
            house = HouseState.GUESTS
            sleep = HouseState.DAY
            active_rules.append("guest_heuristic_active")
        elif terrace_active and late:
            house = HouseState.OUTSIDE
            sleep = HouseState.DAY
            active_rules.append("terrace_active_blocks_night_context")
        elif living_active or tv_active or music_active:
            house = HouseState.RELAXING if hour >= 18 or hour < 3 else HouseState.DAY
            sleep = HouseState.DAY
            active_rules.append("living_area_or_media_active")
        elif late and bedroom_active and not self._is_on(signals.get("bedroom_light")) and rest_quiet:
            house = HouseState.PREPARING_SLEEP
            sleep = HouseState.PREPARING_SLEEP
            active_rules.append("bedroom_active_house_quiet_preparing_sleep")
            quiet_since = self._memory.get("sleep_quiet_since")
            if quiet_since is None:
                self._memory["sleep_quiet_since"] = now
            elif (now - quiet_since).total_seconds() >= self.sleep_quiet_minutes * 60:
                house = HouseState.SLEEPING
                sleep = HouseState.SLEEPING
                active_rules.append("quiet_sleep_window_elapsed")
        elif late and rest_quiet and (nuki_locked or bedroom_active):
            house = HouseState.SLEEPING
            sleep = HouseState.SLEEPING
            active_rules.append("late_house_quiet_sleeping")
        elif hour >= 18:
            house = HouseState.EVENING
            sleep = HouseState.DAY
            active_rules.append("evening_time_without_sleep_signals")
        else:
            house = HouseState.DAY
            sleep = HouseState.DAY
            active_rules.append("daytime_context")

        if house not in {HouseState.PREPARING_SLEEP, HouseState.SLEEPING}:
            self._memory["sleep_quiet_since"] = None

        return house, sleep, guests, {
            "hour": hour,
            "bedroom_active": bedroom_active,
            "living_active": living_active,
            "terrace_active": terrace_active,
            "tv_active": tv_active,
            "music_active": music_active,
            "motion_count": motion_count,
            "opening_count": opening_count,
            "guest_score": guest_score,
            "rest_quiet": rest_quiet,
            "nuki_locked": nuki_locked,
        }

    def _transition_state(self, presence: PresenceState, house: HouseState) -> TransitionState:
        if presence in {PresenceState.LEAVING, PresenceState.COMING_HOME}:
            return TransitionState.TRANSITION
        if house == HouseState.PREPARING_SLEEP:
            return TransitionState.TRANSITION
        return TransitionState.STABLE

    def _vacation_state(self, signals: dict[str, EntitySignal | list[EntitySignal] | None], active_rules: list[str]) -> VacationState:
        vacation = signals.get("vacation")
        if self._is_on(vacation):
            active_rules.append("vacation_entity_active")
            return VacationState.VACATION
        return VacationState.NORMAL

    def _confidence(
        self,
        signals: dict[str, EntitySignal | list[EntitySignal] | None],
        departure_metrics: dict[str, Any],
        house_metrics: dict[str, Any],
        ha_error: str | None,
    ) -> float:
        if ha_error:
            return 0.2
        score = 0.35
        score += 0.12 if signals.get("person") else 0
        score += 0.08 if signals.get("garage_door") else 0
        score += 0.08 if departure_metrics.get("elapsed_seconds") is not None or departure_metrics.get("away_seconds") is not None else 0
        score += 0.07 if signals.get("bedroom_presence") else 0
        score += 0.07 if signals.get("living_presence") else 0
        score += 0.05 if signals.get("terrace_presence") or signals.get("terrace_door") else 0
        score += 0.04 if signals.get("tv") or signals.get("music") else 0
        score += 0.04 if signals.get("bedroom_light") or signals.get("living_light") else 0
        if house_metrics.get("guest_score", 0) >= 4 or house_metrics.get("rest_quiet"):
            score += 0.04
        return round(max(0.0, min(score, 0.99)), 2)

    def _collect_signals(self, states: list[dict[str, Any]], by_entity: dict[str, dict[str, Any]]) -> dict[str, EntitySignal | list[EntitySignal] | None]:
        entities = self.config.get("entities") if isinstance(self.config.get("entities"), dict) else {}
        signals: dict[str, EntitySignal | list[EntitySignal] | None] = {
            "person": self._configured_or_detected(entities, "person", states, by_entity, lambda item: self._domain(item) == "person"),
            "garage_door": self._configured_or_detected(
                entities,
                "garage_door",
                states,
                by_entity,
                lambda item: self._garage_door_match(item),
            ),
            "bedroom_presence": self._configured_or_detected(entities, "bedroom_presence", states, by_entity, lambda item: self._presence_match(item, ["schlaf", "bedroom"])),
            "living_presence": self._configured_or_detected(entities, "living_presence", states, by_entity, lambda item: self._presence_match(item, ["wohn", "living"])),
            "terrace_presence": self._configured_or_detected(entities, "terrace_presence", states, by_entity, lambda item: self._presence_match(item, ["terrasse", "terrace", "garten", "garden"])),
            "terrace_door": self._configured_or_detected(entities, "terrace_door", states, by_entity, lambda item: self._matches(item, ["terrasse", "terrace"]) and self._device_class(item) in {"door", "opening", "window"}),
            "living_light": self._configured_or_detected(entities, "living_light", states, by_entity, lambda item: self._domain(item) == "light" and self._matches(item, ["wohn", "living"])),
            "bedroom_light": self._configured_or_detected(entities, "bedroom_light", states, by_entity, lambda item: self._domain(item) == "light" and self._matches(item, ["schlaf", "bedroom"])),
            "tv": self._configured_or_detected(entities, "tv", states, by_entity, lambda item: self._domain(item) == "media_player" and self._matches(item, ["tv", "fernseh"])),
            "music": self._configured_or_detected(entities, "music", states, by_entity, lambda item: self._domain(item) == "media_player" and self._matches(item, ["musik", "music", "sonos", "speaker"])),
            "nuki": self._configured_or_detected(entities, "nuki", states, by_entity, lambda item: self._matches(item, ["nuki", "haustuer", "front door"]) and self._domain(item) in {"lock", "binary_sensor"}),
            "vacation": self._configured_or_detected(entities, "vacation", states, by_entity, lambda item: self._matches(item, ["vacation", "urlaub"]) and self._domain(item) in {"input_boolean", "binary_sensor"}),
            "motion": self._detect_many(states, lambda item: self._device_class(item) == "motion"),
            "openings": self._detect_many(states, lambda item: self._device_class(item) in {"door", "opening", "window"}),
        }
        return signals

    def _configured_or_detected(
        self,
        entities: dict[str, Any],
        key: str,
        states: list[dict[str, Any]],
        by_entity: dict[str, dict[str, Any]],
        predicate: Callable[[dict[str, Any]], bool],
    ) -> EntitySignal | None:
        configured = str(entities.get(key) or "").strip()
        if configured and configured in by_entity:
            return self._signal(by_entity[configured])
        detected = next((item for item in states if predicate(item)), None)
        return self._signal(detected) if detected else None

    def _garage_door_match(self, item: dict[str, Any]) -> bool:
        domain = self._domain(item)
        if domain == "cover":
            return self._matches(item, ["garage"]) or self._matches(item, ["garagen", "garagentor"]) or self._matches(item, ["tor"])
        if domain != "binary_sensor":
            return False
        if not (self._matches(item, ["garage"]) or self._matches(item, ["garagen", "garagentor"])):
            return False
        if self._device_class(item) == "problem":
            return False
        return not self._matches(item, ["problem", "diagnose", "diagnostic", "fault", "error", "battery", "batterie"])

    def _detect_many(self, states: list[dict[str, Any]], predicate: Callable[[dict[str, Any]], bool]) -> list[EntitySignal]:
        return [self._signal(item) for item in states if predicate(item)]

    def _presence_match(self, item: dict[str, Any], words: list[str]) -> bool:
        return self._domain(item) == "binary_sensor" and self._device_class(item) in {"motion", "occupancy", "presence"} and self._matches(item, words)

    def _matches(self, item: dict[str, Any], words: list[str]) -> bool:
        haystack = f"{item.get('entity_id') or ''} {item.get('attributes', {}).get('friendly_name') or ''}".lower()
        return any(word in haystack for word in words)

    def _signal(self, item: dict[str, Any]) -> EntitySignal:
        attrs = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
        return EntitySignal(
            entity_id=str(item.get("entity_id") or ""),
            state=str(item.get("state") or "").lower(),
            name=str(attrs.get("friendly_name") or item.get("entity_id") or ""),
            device_class=str(attrs.get("device_class") or "").lower(),
            updated_at=str(item.get("last_changed") or item.get("last_updated") or "") or None,
            attributes=attrs,
        )

    def _is_home(self, signal: EntitySignal | list[EntitySignal] | None) -> bool | None:
        state = self._state_value(signal)
        if state in HOME_STATES:
            return True
        if state in AWAY_STATES:
            return False
        return None

    def _is_open(self, signal: EntitySignal | list[EntitySignal] | None) -> bool:
        return self._state_value(signal) in OPEN_STATES

    def _is_on(self, signal: EntitySignal | list[EntitySignal] | None) -> bool:
        return self._state_value(signal) in ACTIVE_STATES

    def _is_active(self, signal: EntitySignal | list[EntitySignal] | None) -> bool:
        return self._state_value(signal) in ACTIVE_STATES

    def _active_count(self, value: EntitySignal | list[EntitySignal] | None) -> int:
        if not isinstance(value, list):
            return 1 if self._is_active(value) else 0
        return len([item for item in value if self._is_active(item)])

    def _lights_on_count(self, signals: dict[str, EntitySignal | list[EntitySignal] | None]) -> int:
        return sum(1 for key in ("living_light", "bedroom_light") if self._is_on(signals.get(key)))

    def _state_value(self, signal: EntitySignal | list[EntitySignal] | None) -> str:
        if signal is None or isinstance(signal, list):
            return ""
        return str(signal.state or "").lower()

    def _signal_payload(self, signal: EntitySignal | list[EntitySignal] | None) -> dict[str, Any] | list[dict[str, Any]] | None:
        if signal is None:
            return None
        if isinstance(signal, list):
            return [item.as_dict() for item in signal]
        return signal.as_dict()

    def _domain(self, item: dict[str, Any]) -> str:
        return str(item.get("entity_id") or "").split(".", 1)[0]

    def _device_class(self, item: dict[str, Any]) -> str:
        attrs = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
        return str(attrs.get("device_class") or "").lower()

    def _now(self) -> datetime:
        now = self.now_provider()
        if now.tzinfo is None:
            return now.replace(tzinfo=timezone.utc)
        return now

    def _public_config(self) -> dict[str, Any]:
        return {
            "departure_window_seconds": self.departure_window_seconds,
            "short_away_return_seconds": self.short_away_return_seconds,
            "garage_open_after_away_seconds": self.garage_open_after_away_seconds,
            "long_away_seconds": self.long_away_seconds,
            "sleep_quiet_minutes": self.sleep_quiet_minutes,
            "configured_entities": sorted((self.config.get("entities") or {}).keys()) if isinstance(self.config.get("entities"), dict) else [],
        }
