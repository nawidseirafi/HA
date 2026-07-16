import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.agents.garden import routes
from backend.agents.garden.service import GardenNotFound, GardenSafetyBlocked


class FakeGardenService:
    def start_irrigation(self, zone_id, duration_minutes=None, source="manual"):
        if zone_id == "missing":
            raise GardenNotFound(zone_id)
        if duration_minutes and duration_minutes > 30:
            raise ValueError("Dauer muss zwischen 1 und 30 Minuten liegen.")
        if zone_id == "blocked":
            raise GardenSafetyBlocked("blockiert", {"zone_id": zone_id, "blocks": [{"code": "mower_active"}]})
        return {"ok": True, "zone_id": zone_id, "duration_minutes": duration_minutes, "source": source}

    def stop_irrigation(self, zone_id, source="manual", stop_reason="manual"):
        if zone_id == "missing":
            raise GardenNotFound(zone_id)
        return {"ok": True, "zone_id": zone_id, "source": source, "stop_reason": stop_reason}

    def evaluate_zone(self, zone_id, save=True):
        if zone_id == "missing":
            raise GardenNotFound(zone_id)
        return {"zone_id": zone_id, "decision": {"status": "dry"}}


class GardenApiTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(routes.router)
        self.client = TestClient(app)

    def test_start_with_valid_release(self):
        with patch.object(routes, "garden_service", FakeGardenService()):
            response = self.client.post("/api/garden/zones/lawn/irrigation/start", json={"duration_minutes": 15})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])

    def test_start_safety_block_returns_409(self):
        with patch.object(routes, "garden_service", FakeGardenService()):
            response = self.client.post("/api/garden/zones/blocked/irrigation/start", json={"duration_minutes": 15})
        self.assertEqual(response.status_code, 409)

    def test_duration_above_max_returns_422(self):
        with patch.object(routes, "garden_service", FakeGardenService()):
            response = self.client.post("/api/garden/zones/lawn/irrigation/start", json={"duration_minutes": 99})
        self.assertEqual(response.status_code, 422)

    def test_unknown_zone_returns_404(self):
        with patch.object(routes, "garden_service", FakeGardenService()):
            response = self.client.post("/api/garden/zones/missing/evaluate", json={})
        self.assertEqual(response.status_code, 404)

    def test_stop_without_open_run_is_idempotent_service_result(self):
        with patch.object(routes, "garden_service", FakeGardenService()):
            response = self.client.post("/api/garden/zones/lawn/irrigation/stop", json={})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])


if __name__ == "__main__":
    unittest.main()
