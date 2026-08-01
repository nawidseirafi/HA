import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from backend.services.household.garage_service import HouseholdGarageService
from backend.services.household.shutter_service import HouseholdShutterService


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


def cover(entity_id, value, name="", device_class="shutter"):
    attributes = {"device_class": device_class}
    if name:
        attributes["friendly_name"] = name
    return {"entity_id": entity_id, "state": value, "attributes": attributes}


def sun(value):
    return {"entity_id": "sun.sun", "state": value, "attributes": {"friendly_name": "Sun"}}


def garage_context(garage="READY_TO_OPEN", confidence=0.92):
    return {
        "presence": "COMING_HOME",
        "garage": garage,
        "house": "EVENING",
        "sleep": "DAY",
        "guest": False,
        "confidence": confidence,
    }


def sleep_context(sleep="SLEEPING", house="SLEEPING", guest=False, confidence=0.9):
    return {
        "presence": "HOME",
        "garage": "NONE",
        "house": house,
        "sleep": sleep,
        "guest": guest,
        "confidence": confidence,
    }


def config():
    return {
        "household": {
            "garage": {
                "enabled": True,
                "control_enabled": True,
                "auto_discovery": True,
                "garage_entity": "cover.garage",
                "allow_open": True,
                "allow_close": True,
                "min_confidence": 0.6,
            },
            "shutters": {
                "enabled": True,
                "control_enabled": True,
                "auto_discovery": True,
                "ground_floor_entities": ["cover.eg_wohnzimmer", "cover.eg_kueche"],
                "open_after_sunrise": True,
                "fallback_open_after": "07:30",
                "min_confidence": 0.6,
                "close_states": ["SLEEPING"],
                "block_house_states": ["OUTSIDE", "GUESTS", "RELAXING"],
            },
        }
    }


class HouseholdGarageShutterTests(unittest.TestCase):
    def patch_config(self, cfg=None):
        patcher = patch("backend.services.household.garage_service.load_global_config", return_value=cfg or config())
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher2 = patch("backend.services.household.shutter_service.load_global_config", return_value=cfg or config())
        patcher2.start()
        self.addCleanup(patcher2.stop)

    def test_garage_ready_to_open_opens_cover(self):
        self.patch_config()
        ha = FakeHomeAssistant([cover("cover.garage", "closed", "Garage")])
        service = HouseholdGarageService(ha_service=ha, context_provider=lambda: garage_context())

        result = service.evaluate(apply=True)

        self.assertTrue(result["applied"])
        self.assertEqual(result["decision"]["action"], "open_cover")
        self.assertEqual(ha.calls[0]["service"], "open_cover")
        self.assertEqual(ha.calls[0]["payload"]["entity_id"], "cover.garage")

    def test_garage_ready_to_close_closes_cover(self):
        self.patch_config()
        ha = FakeHomeAssistant([cover("cover.garage", "open", "Garage")])
        service = HouseholdGarageService(ha_service=ha, context_provider=lambda: garage_context(garage="READY_TO_CLOSE"))

        result = service.evaluate(apply=True)

        self.assertTrue(result["applied"])
        self.assertEqual(result["decision"]["action"], "close_cover")
        self.assertEqual(ha.calls[0]["service"], "close_cover")

    def test_garage_low_confidence_blocks_action(self):
        self.patch_config()
        ha = FakeHomeAssistant([cover("cover.garage", "closed", "Garage")])
        service = HouseholdGarageService(ha_service=ha, context_provider=lambda: garage_context(confidence=0.2))

        result = service.evaluate(apply=True)

        self.assertFalse(result["applied"])
        self.assertEqual(result["decision"]["status"], "low_confidence")
        self.assertEqual(ha.calls, [])

    def test_shutters_close_when_sleeping_without_guests(self):
        self.patch_config()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        ha = FakeHomeAssistant([
            cover("cover.eg_wohnzimmer", "open", "EG Wohnzimmer Rollo"),
            cover("cover.eg_kueche", "open", "EG Kueche Rollo"),
            sun("below_horizon"),
        ])
        service = HouseholdShutterService(
            ha_service=ha,
            context_provider=lambda: sleep_context(),
            state_path=Path(tmp.name) / "shutter_state.json",
            now_provider=lambda: datetime(2026, 8, 1, 22, 55, tzinfo=timezone.utc),
        )

        result = service.evaluate(apply=True)

        self.assertTrue(result["applied"])
        self.assertEqual(result["decision"]["action"], "close_cover")
        self.assertEqual(ha.calls[0]["service"], "close_cover")
        self.assertEqual(ha.calls[0]["payload"]["entity_id"], ["cover.eg_wohnzimmer", "cover.eg_kueche"])

    def test_shutters_guests_block_night_close(self):
        self.patch_config()
        ha = FakeHomeAssistant([cover("cover.eg_wohnzimmer", "open", "EG Wohnzimmer Rollo"), sun("below_horizon")])
        service = HouseholdShutterService(ha_service=ha, context_provider=lambda: sleep_context(guest=True))

        result = service.evaluate(apply=True)

        self.assertFalse(result["applied"])
        self.assertEqual(result["decision"]["status"], "guests_block_close")
        self.assertEqual(ha.calls, [])

    def test_shutters_open_after_sunrise_only_owned_entities(self):
        self.patch_config()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        ha = FakeHomeAssistant([
            cover("cover.eg_wohnzimmer", "open", "EG Wohnzimmer Rollo"),
            cover("cover.eg_kueche", "open", "EG Kueche Rollo"),
            sun("below_horizon"),
        ])
        service = HouseholdShutterService(
            ha_service=ha,
            context_provider=lambda: sleep_context(),
            state_path=Path(tmp.name) / "shutter_state.json",
            now_provider=lambda: datetime(2026, 8, 1, 22, 55, tzinfo=timezone.utc),
        )
        service.evaluate(apply=True)

        ha.states = [
            cover("cover.eg_wohnzimmer", "closed", "EG Wohnzimmer Rollo"),
            cover("cover.eg_kueche", "closed", "EG Kueche Rollo"),
            sun("above_horizon"),
        ]
        service.now_provider = lambda: datetime(2026, 8, 2, 6, 30, tzinfo=timezone.utc)
        result = service.evaluate(apply=True)

        self.assertTrue(result["applied"])
        self.assertEqual(result["decision"]["action"], "open_cover")
        self.assertEqual(ha.calls[-1]["service"], "open_cover")
        self.assertEqual(ha.calls[-1]["payload"]["entity_id"], ["cover.eg_wohnzimmer", "cover.eg_kueche"])

    def test_shutter_autodiscovery_requires_ground_floor_tokens(self):
        cfg = config()
        cfg["household"]["shutters"]["ground_floor_entities"] = []
        self.patch_config(cfg)
        ha = FakeHomeAssistant([
            cover("cover.og_schlafzimmer", "open", "OG Schlafzimmer Rollo"),
            cover("cover.eg_wohnzimmer", "open", "EG Wohnzimmer Rollo"),
            cover("cover.garage", "open", "Garage", "garage"),
            sun("below_horizon"),
        ])
        service = HouseholdShutterService(ha_service=ha, context_provider=lambda: sleep_context())

        result = service.evaluate(apply=True)

        self.assertTrue(result["applied"])
        self.assertEqual(ha.calls[0]["payload"]["entity_id"], ["cover.eg_wohnzimmer"])


if __name__ == "__main__":
    unittest.main()
