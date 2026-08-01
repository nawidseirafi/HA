import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from backend.services.household.front_light_service import HouseholdFrontLightService


class FakeHomeAssistant:
    def __init__(self, states):
        self.states = states
        self.calls = []

    def get_states(self):
        return self.states

    def call_service(self, domain, service, payload):
        call = {"domain": domain, "service": service, "payload": payload}
        self.calls.append(call)
        return {"ok": True, **call}


def light(entity_id, value, name="", area=""):
    attributes = {}
    if name:
        attributes["friendly_name"] = name
    if area:
        attributes["area"] = area
    return {"entity_id": entity_id, "state": value, "attributes": attributes}


def context(presence="COMING_HOME", garage="READY_TO_OPEN", confidence=0.91):
    return {
        "presence": presence,
        "garage": garage,
        "house": "EVENING",
        "sleep": "DAY",
        "confidence": confidence,
    }


def config(light_entity="light.front_door", auto_discovery=True, light_entities=None):
    return {
        "household": {
            "front_light": {
                "enabled": True,
                "control_enabled": True,
                "auto_discovery": auto_discovery,
                "light_entity": light_entity,
                "light_entities": light_entities or [],
                "evening_start": "18:00",
                "morning_end": "07:00",
                "turn_off_after_minutes": 10,
                "min_confidence": 0.55,
                "arrival_states": ["COMING_HOME"],
                "arrival_garage_states": ["READY_TO_OPEN"],
            }
        }
    }


class HouseholdFrontLightServiceTests(unittest.TestCase):
    def service(self, ha, ctx, now, cfg=None):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patcher = patch("backend.services.household.front_light_service.load_global_config", return_value=cfg or config())
        patcher.start()
        self.addCleanup(patcher.stop)
        return HouseholdFrontLightService(
            ha_service=ha,
            context_provider=lambda: ctx,
            state_path=Path(tmp.name) / "front_light_state.json",
            now_provider=lambda: now,
        )

    def test_evening_arrival_turns_front_light_on(self):
        now = datetime(2026, 8, 1, 20, 30, tzinfo=timezone.utc)
        ha = FakeHomeAssistant([light("light.front_door", "off", "Front Door Light")])
        service = self.service(ha, context(), now)

        result = service.evaluate(apply=True)

        self.assertTrue(result["applied"])
        self.assertEqual(result["decision"]["action"], "turn_on")
        self.assertEqual(ha.calls[0]["domain"], "light")
        self.assertEqual(ha.calls[0]["service"], "turn_on")
        self.assertEqual(ha.calls[0]["payload"]["entity_id"], "light.front_door")

    def test_daytime_arrival_does_not_turn_light_on(self):
        now = datetime(2026, 8, 1, 12, 30, tzinfo=timezone.utc)
        ha = FakeHomeAssistant([light("light.front_door", "off", "Front Door Light")])
        service = self.service(ha, context(), now)

        result = service.evaluate(apply=True)

        self.assertFalse(result["applied"])
        self.assertEqual(result["decision"]["status"], "daytime")
        self.assertEqual(ha.calls, [])

    def test_owned_light_turns_off_after_timeout(self):
        start = datetime(2026, 8, 1, 20, 30, tzinfo=timezone.utc)
        ha = FakeHomeAssistant([light("light.front_door", "off", "Front Door Light")])
        service = self.service(ha, context(), start)
        service.evaluate(apply=True)

        ha.states = [light("light.front_door", "on", "Front Door Light")]
        service.now_provider = lambda: start + timedelta(minutes=11)
        result = service.evaluate(apply=True)

        self.assertTrue(result["applied"])
        self.assertEqual(result["decision"]["action"], "turn_off")
        self.assertEqual(ha.calls[-1]["service"], "turn_off")
        self.assertEqual(ha.calls[-1]["payload"]["entity_id"], "light.front_door")

    def test_manual_light_is_not_turned_off_without_owner_state(self):
        now = datetime(2026, 8, 1, 20, 45, tzinfo=timezone.utc)
        ha = FakeHomeAssistant([light("light.front_door", "on", "Front Door Light")])
        service = self.service(ha, context(), now)

        result = service.evaluate(apply=True)

        self.assertFalse(result["applied"])
        self.assertEqual(result["decision"]["status"], "already_on")
        self.assertEqual(ha.calls, [])

    def test_autodiscovery_prefers_entry_light(self):
        now = datetime(2026, 8, 1, 20, 30, tzinfo=timezone.utc)
        ha = FakeHomeAssistant([
            light("light.wohnzimmer", "off", "Wohnzimmer Licht"),
            light("light.eingang", "off", "Eingang Licht"),
        ])
        service = self.service(ha, context(), now, cfg=config(light_entity="", auto_discovery=True))

        result = service.evaluate(apply=True)

        self.assertTrue(result["applied"])
        self.assertEqual(ha.calls[0]["payload"]["entity_id"], "light.eingang")

    def test_configured_frontdoor_lights_turn_on_together(self):
        now = datetime(2026, 8, 1, 20, 30, tzinfo=timezone.utc)
        ha = FakeHomeAssistant([
            light("light.eingang", "off", "Eingang"),
            light("light.front_door", "off", "Front Door"),
        ])
        service = self.service(
            ha,
            context(),
            now,
            cfg=config(light_entity="", auto_discovery=True, light_entities=["light.eingang", "light.front_door"]),
        )

        result = service.evaluate(apply=True)

        self.assertTrue(result["applied"])
        self.assertEqual(ha.calls[0]["payload"]["entity_id"], ["light.eingang", "light.front_door"])

    def test_low_confidence_blocks_arrival_light(self):
        now = datetime(2026, 8, 1, 20, 30, tzinfo=timezone.utc)
        ha = FakeHomeAssistant([light("light.front_door", "off", "Front Door Light")])
        service = self.service(ha, context(confidence=0.31), now)

        result = service.evaluate(apply=True)

        self.assertFalse(result["applied"])
        self.assertEqual(result["decision"]["status"], "low_confidence")
        self.assertEqual(ha.calls, [])


if __name__ == "__main__":
    unittest.main()
