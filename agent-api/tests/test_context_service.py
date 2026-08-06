import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.services.context.models import GarageState, HouseState, PresenceState, TransitionState
from backend.services.context.service import ContextService
from backend.services.context.store import ContextStore


class FakeHomeAssistant:
    def __init__(self, states):
        self.states = states

    def get_states(self):
        return self.states


def state(entity_id, value, name="", device_class=""):
    attributes = {}
    if name:
        attributes["friendly_name"] = name
    if device_class:
        attributes["device_class"] = device_class
    return {"entity_id": entity_id, "state": value, "attributes": attributes}


def base_states(person="home", garage="closed"):
    return [
        state("person.nawid", person, "Nawid"),
        state("cover.garage", garage, "Garage"),
        state("binary_sensor.schlafzimmer_presence", "off", "Schlafzimmer Presence", "presence"),
        state("binary_sensor.wohnzimmer_presence", "off", "Wohnzimmer Presence", "presence"),
        state("binary_sensor.terrasse_presence", "off", "Terrasse Presence", "presence"),
        state("binary_sensor.terrassentuer", "off", "Terrassentuer", "door"),
        state("light.wohnzimmer", "off", "Wohnzimmer Licht"),
        state("light.schlafzimmer", "off", "Schlafzimmer Licht"),
        state("media_player.tv", "off", "TV"),
        state("media_player.sonos", "off", "Musik"),
        state("lock.nuki", "locked", "Nuki"),
    ]


def with_states(states, *updates):
    by_entity = {item["entity_id"]: dict(item) for item in states}
    for item in updates:
        by_entity[item["entity_id"]] = item
    return list(by_entity.values())


class ContextServiceTests(unittest.TestCase):
    def service(self, start):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        current = {"now": start}
        service = ContextService(
            ha_service=FakeHomeAssistant([]),
            store=ContextStore(Path(tmp.name) / "context.db"),
            now_provider=lambda: current["now"],
        )
        return service, current

    def test_real_departure_closes_observation_window_before_ready_to_close(self):
        now = datetime(2026, 7, 31, 18, 0, tzinfo=timezone.utc)
        service, _ = self.service(now)
        service.evaluate(base_states(), now=now)

        leaving = service.evaluate(base_states(person="not_home", garage="open"), now=now + timedelta(minutes=1))
        self.assertEqual(leaving.presence, PresenceState.LEAVING)
        self.assertEqual(leaving.garage, GarageState.KEEP_OPEN)

        away = service.evaluate(base_states(person="not_home", garage="open"), now=now + timedelta(minutes=6))
        self.assertEqual(away.presence, PresenceState.AWAY)
        self.assertEqual(away.garage, GarageState.READY_TO_CLOSE)
        self.assertEqual(away.transition, TransitionState.STABLE)

    def test_short_away_keeps_garage_open(self):
        now = datetime(2026, 7, 31, 18, 0, tzinfo=timezone.utc)
        service, _ = self.service(now)
        service.evaluate(base_states(), now=now)
        service.evaluate(base_states(person="not_home", garage="open"), now=now + timedelta(minutes=1))

        snapshot = service.evaluate(base_states(person="home", garage="open"), now=now + timedelta(minutes=3))

        self.assertEqual(snapshot.presence, PresenceState.SHORT_AWAY)
        self.assertEqual(snapshot.garage, GarageState.KEEP_OPEN)

    def test_garage_detection_prefers_cover_over_problem_sensor(self):
        now = datetime(2026, 7, 31, 18, 0, tzinfo=timezone.utc)
        service, _ = self.service(now)
        states = [
            state("person.nawid", "home", "Nawid"),
            state("binary_sensor.garage_problem", "off", "Garage Problem", "problem"),
            state("cover.garagentor", "open", "Garagentor"),
        ]

        snapshot = service.evaluate(states, now=now)

        self.assertEqual(snapshot.signals["garage_door"]["entity_id"], "cover.garagentor")
        self.assertEqual(snapshot.garage, GarageState.KEEP_OPEN)

    def test_coming_home_after_long_absence_ready_to_open(self):
        now = datetime(2026, 7, 31, 8, 0, tzinfo=timezone.utc)
        service, _ = self.service(now)
        service.evaluate(base_states(), now=now)
        service.evaluate(base_states(person="not_home", garage="closed"), now=now + timedelta(minutes=1))

        snapshot = service.evaluate(base_states(person="home", garage="closed"), now=now + timedelta(hours=4))

        self.assertEqual(snapshot.presence, PresenceState.COMING_HOME)
        self.assertEqual(snapshot.garage, GarageState.READY_TO_OPEN)
        self.assertEqual(snapshot.transition, TransitionState.TRANSITION)

    def test_person_departure_can_ready_to_close(self):
        now = datetime(2026, 7, 31, 18, 0, tzinfo=timezone.utc)
        service, _ = self.service(now)
        service.evaluate(base_states(), now=now)

        leaving = service.evaluate(base_states(person="not_home", garage="open"), now=now + timedelta(minutes=1))
        self.assertEqual(leaving.presence, PresenceState.LEAVING)
        self.assertEqual(leaving.garage, GarageState.KEEP_OPEN)
        self.assertIn("person_left_home_departure_window_started", leaving.active_rules)

        away = service.evaluate(base_states(person="not_home", garage="open"), now=now + timedelta(minutes=6))
        self.assertEqual(away.presence, PresenceState.AWAY)
        self.assertEqual(away.garage, GarageState.READY_TO_CLOSE)
        self.assertIn("departure_window_elapsed_person_still_away", away.active_rules)

    def test_person_short_away_keeps_garage_open(self):
        now = datetime(2026, 7, 31, 18, 0, tzinfo=timezone.utc)
        service, _ = self.service(now)
        service.evaluate(base_states(), now=now)
        service.evaluate(base_states(person="not_home", garage="open"), now=now + timedelta(minutes=1))

        snapshot = service.evaluate(base_states(person="home", garage="open"), now=now + timedelta(minutes=3))

        self.assertEqual(snapshot.presence, PresenceState.SHORT_AWAY)
        self.assertEqual(snapshot.garage, GarageState.KEEP_OPEN)
        self.assertIn("person_returned_within_short_away_window", snapshot.active_rules)

    def test_person_coming_home_ready_to_open(self):
        now = datetime(2026, 7, 31, 8, 0, tzinfo=timezone.utc)
        service, _ = self.service(now)
        service.evaluate(base_states(), now=now)
        service.evaluate(base_states(person="not_home", garage="closed"), now=now + timedelta(minutes=1))

        snapshot = service.evaluate(base_states(person="home", garage="closed"), now=now + timedelta(hours=4))

        self.assertEqual(snapshot.presence, PresenceState.COMING_HOME)
        self.assertEqual(snapshot.garage, GarageState.READY_TO_OPEN)
        self.assertGreaterEqual(snapshot.confidence, 0.6)
        self.assertIn("person_returned_after_long_absence", snapshot.active_rules)

    def test_person_coming_home_after_non_short_absence_ready_to_open(self):
        now = datetime(2026, 7, 31, 18, 0, tzinfo=timezone.utc)
        service, _ = self.service(now)
        service.evaluate(base_states(), now=now)
        service.evaluate(base_states(person="not_home", garage="closed"), now=now + timedelta(minutes=1))

        snapshot = service.evaluate(base_states(person="home", garage="closed"), now=now + timedelta(minutes=31))

        self.assertEqual(snapshot.presence, PresenceState.COMING_HOME)
        self.assertEqual(snapshot.garage, GarageState.READY_TO_OPEN)
        self.assertIn("person_returned_after_garage_open_window", snapshot.active_rules)

    def test_guests_prevent_sleep_context(self):
        now = datetime(2026, 7, 31, 21, 30, tzinfo=timezone.utc)
        service, _ = self.service(now)
        states = with_states(
            base_states(),
            state("binary_sensor.wohnzimmer_presence", "on", "Wohnzimmer Presence", "presence"),
            state("binary_sensor.terrasse_presence", "on", "Terrasse Presence", "presence"),
            state("binary_sensor.haustuer", "on", "Haustuer", "door"),
            state("binary_sensor.kuechenfenster", "on", "Kuechenfenster", "window"),
            state("light.wohnzimmer", "on", "Wohnzimmer Licht"),
            state("light.schlafzimmer", "on", "Schlafzimmer Licht"),
        )

        snapshot = service.evaluate(states, now=now)

        self.assertTrue(snapshot.guest)
        self.assertEqual(snapshot.house, HouseState.GUESTS)
        self.assertNotEqual(snapshot.sleep, HouseState.SLEEPING)

    def test_terrace_at_night_blocks_sleeping(self):
        now = datetime(2026, 7, 31, 22, 0, tzinfo=timezone.utc)
        service, _ = self.service(now)
        states = with_states(base_states(), state("binary_sensor.terrasse_presence", "on", "Terrasse Presence", "presence"))

        snapshot = service.evaluate(states, now=now)

        self.assertEqual(snapshot.house, HouseState.OUTSIDE)
        self.assertNotEqual(snapshot.sleep, HouseState.SLEEPING)

    def test_living_room_active_is_relaxing_not_sleep(self):
        now = datetime(2026, 7, 31, 22, 15, tzinfo=timezone.utc)
        service, _ = self.service(now)
        states = with_states(
            base_states(),
            state("binary_sensor.wohnzimmer_presence", "on", "Wohnzimmer Presence", "presence"),
            state("media_player.tv", "playing", "TV"),
        )

        snapshot = service.evaluate(states, now=now)

        self.assertEqual(snapshot.house, HouseState.RELAXING)
        self.assertNotEqual(snapshot.sleep, HouseState.SLEEPING)

    def test_sleep_begin_then_sleeping_after_quiet_window(self):
        now = datetime(2026, 7, 31, 22, 45, tzinfo=timezone.utc)
        service, _ = self.service(now)
        states = with_states(base_states(), state("binary_sensor.schlafzimmer_presence", "on", "Schlafzimmer Presence", "presence"))

        preparing = service.evaluate(states, now=now)
        sleeping = service.evaluate(states, now=now + timedelta(minutes=11))

        self.assertEqual(preparing.sleep, HouseState.PREPARING_SLEEP)
        self.assertEqual(sleeping.sleep, HouseState.SLEEPING)

    def test_confidence_uses_available_signal_weighting(self):
        now = datetime(2026, 7, 31, 20, 0, tzinfo=timezone.utc)
        service, _ = self.service(now)
        rich = service.evaluate(base_states(), now=now)
        poor = service.evaluate([], now=now, ha_error="unavailable")

        self.assertGreaterEqual(rich.confidence, 0.8)
        self.assertEqual(poor.confidence, 0.2)

    def test_summary_text_is_returned_for_ui(self):
        now = datetime(2026, 7, 31, 22, 15, tzinfo=timezone.utc)
        service, _ = self.service(now)
        snapshot = service.evaluate(
            with_states(
                base_states(),
                state("binary_sensor.wohnzimmer_presence", "on", "Wohnzimmer Presence", "presence"),
                state("media_player.tv", "playing", "TV"),
            ),
            now=now,
        )
        payload = snapshot.as_dict()

        self.assertIn("summary", payload)
        self.assertTrue(payload["summary"])
        self.assertNotIn("ContextService liefert noch keinen", payload["summary"])

    def test_transition_state_for_preparing_sleep(self):
        now = datetime(2026, 7, 31, 22, 45, tzinfo=timezone.utc)
        service, _ = self.service(now)
        states = with_states(base_states(), state("binary_sensor.schlafzimmer_presence", "on", "Schlafzimmer Presence", "presence"))

        snapshot = service.evaluate(states, now=now)

        self.assertEqual(snapshot.transition, TransitionState.TRANSITION)

    def test_history_is_stored_in_all_context_tables(self):
        now = datetime(2026, 7, 31, 20, 0, tzinfo=timezone.utc)
        service, current = self.service(now)
        service.ha_service.states = base_states()
        current["now"] = now

        snapshot = service.evaluate_current()

        self.assertEqual(snapshot.presence, PresenceState.HOME)
        counts = service.store.table_counts()
        self.assertEqual(counts["context_history"], 1)
        self.assertEqual(counts["presence_history"], 1)
        self.assertEqual(counts["house_state_history"], 1)
        self.assertEqual(counts["garage_context"], 1)
        self.assertEqual(counts["sleep_context"], 1)
        self.assertEqual(service.history()["items"][0]["presence"], "HOME")


if __name__ == "__main__":
    unittest.main()
