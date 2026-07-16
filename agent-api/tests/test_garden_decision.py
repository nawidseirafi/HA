import unittest
from datetime import datetime, timedelta, timezone

from backend.agents.garden.decision import GardenDecisionEngine
from backend.agents.garden.models import ZoneEvaluationInput


def base_config(**updates):
    config = {
        "moisture": {"critical_below": 15, "dry_below": 25, "target_min": 35, "wet_above": 60},
        "temperature": {"irrigation_min_c": 5, "irrigation_max_c": 32},
        "irrigation": {
            "automatic_enabled": True,
            "default_duration_minutes": 20,
            "max_duration_minutes": 30,
            "minimum_pause_hours": 12,
            "sensor_max_age_minutes": 180,
        },
        "mower": {"enabled": True, "irrigation_block_states": ["mowing", "starting", "returning"]},
        "weather": {"rain_block_enabled": True, "rain_probability_block_above": 60},
    }
    for key, value in updates.items():
        config[key].update(value)
    return config


def input_for(**updates):
    now = datetime.now(timezone.utc).isoformat()
    data = {
        "zone_id": "lawn",
        "zone_name": "Rasen",
        "moisture": 40,
        "soil_temperature": 18,
        "battery": 80,
        "moisture_available": True,
        "moisture_last_updated": now,
        "irrigation_active": False,
        "irrigation_available": True,
        "mower_status": "parked",
        "rain_active": False,
        "rain_probability": 10,
        "last_irrigation_ended_at": None,
        "open_irrigation_run": None,
        "config": base_config(),
        "control_enabled": True,
        "agent_enabled": True,
        "evaluated_at": now,
    }
    data.update(updates)
    return ZoneEvaluationInput(**data)


def codes(decision):
    return {item["code"] for item in decision.public_dict()["blocks"]}


class GardenDecisionTests(unittest.TestCase):
    def test_healthy_soil_no_action(self):
        decision = GardenDecisionEngine().evaluate_zone(input_for(moisture=42))
        self.assertEqual(decision.status, "healthy")
        self.assertEqual(decision.decision, "no_action")
        self.assertFalse(decision.apply_allowed)

    def test_dry_recommends_irrigation(self):
        decision = GardenDecisionEngine().evaluate_zone(input_for(moisture=22))
        self.assertEqual(decision.status, "dry")
        self.assertEqual(decision.decision, "irrigate")
        self.assertTrue(decision.apply_allowed)

    def test_critically_dry(self):
        decision = GardenDecisionEngine().evaluate_zone(input_for(moisture=10))
        self.assertEqual(decision.status, "critically_dry")
        self.assertEqual(decision.decision, "irrigate")

    def test_mower_active_blocks_irrigation(self):
        decision = GardenDecisionEngine().evaluate_zone(input_for(moisture=20, mower_status="mowing"))
        self.assertIn("mower_active", codes(decision))
        self.assertFalse(decision.apply_allowed)

    def test_irrigation_already_active_blocks_second_start(self):
        decision = GardenDecisionEngine().evaluate_zone(input_for(moisture=20, irrigation_active=True))
        self.assertIn("irrigation_already_active", codes(decision))

    def test_rain_active_blocks(self):
        decision = GardenDecisionEngine().evaluate_zone(input_for(moisture=20, rain_active=True))
        self.assertIn("rain_active", codes(decision))

    def test_rain_probability_blocks(self):
        decision = GardenDecisionEngine().evaluate_zone(input_for(moisture=20, rain_probability=80))
        self.assertIn("rain_expected", codes(decision))

    def test_sensor_unavailable_blocks(self):
        decision = GardenDecisionEngine().evaluate_zone(input_for(moisture=20, moisture_available=False))
        self.assertIn("soil_moisture_unavailable", codes(decision))

    def test_stale_sensor_blocks(self):
        old = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
        decision = GardenDecisionEngine().evaluate_zone(input_for(moisture=20, moisture_last_updated=old))
        self.assertIn("soil_moisture_stale", codes(decision))

    def test_temperature_too_low_blocks(self):
        decision = GardenDecisionEngine().evaluate_zone(input_for(moisture=20, soil_temperature=2))
        self.assertIn("soil_temperature_too_low", codes(decision))

    def test_temperature_too_high_blocks(self):
        decision = GardenDecisionEngine().evaluate_zone(input_for(moisture=20, soil_temperature=35))
        self.assertIn("soil_temperature_too_high", codes(decision))

    def test_minimum_pause_blocks(self):
        ended = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        decision = GardenDecisionEngine().evaluate_zone(input_for(moisture=20, last_irrigation_ended_at=ended))
        self.assertIn("minimum_pause_active", codes(decision))

    def test_automatic_disabled_blocks_apply_but_keeps_recommendation(self):
        config = base_config(irrigation={"automatic_enabled": False})
        decision = GardenDecisionEngine().evaluate_zone(input_for(moisture=20, config=config))
        self.assertEqual(decision.decision, "irrigate")
        self.assertFalse(decision.apply_allowed)
        self.assertIn("automatic_control_disabled", codes(decision))

    def test_control_disabled_blocks_apply_but_keeps_recommendation(self):
        decision = GardenDecisionEngine().evaluate_zone(input_for(moisture=20, control_enabled=False))
        self.assertEqual(decision.decision, "irrigate")
        self.assertFalse(decision.apply_allowed)
        self.assertIn("control_disabled", codes(decision))


if __name__ == "__main__":
    unittest.main()
