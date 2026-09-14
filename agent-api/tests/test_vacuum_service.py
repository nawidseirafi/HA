import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

from backend.services.vacuum_service import VacuumService, vacuum_items, vacuum_notice


def entity(entity_id, state, **attributes):
    return {"entity_id": entity_id, "state": state, "attributes": attributes}


class VacuumTests(unittest.TestCase):
    def setUp(self):
        self.states = [entity("vacuum.robot", "docked", supported_features=8192 | 4 | 8 | 16 | 32, fan_speed_list=["quiet", "max"]),
                       entity("sensor.robot_batterie", "100"), entity("sensor.robot_reinigungsbereich", "21.4", unit_of_measurement="m²"),
                       entity("image.robot_keller", "2026-09-13T09:41:00Z", friendly_name="Keller"),
                       entity("select.robot_mode", "vacuum", options=["vacuum", "mop"]),
                       entity("button.robot_routine", "unknown"), entity("switch.robot_dnd", "on"),
                       entity("image.other", "2026-09-13T09:41:00Z")]
        self.metadata = {s["entity_id"]: {"device_id": "robot" if s["entity_id"] != "image.other" else "other"} for s in self.states}
        self.ha = Mock()
        self.ha.fetch_states.return_value = self.states
        self.ha.get_device_metadata_by_entity.return_value = self.metadata
        self.ha.call_service.return_value = {"ok": True}
        self.service = VacuumService(self.ha)

    def test_inventory_joins_only_same_device(self):
        self.states.append(entity("sensor.robot_gesamter_reinigungsbereich", "2400"))
        self.metadata["sensor.robot_gesamter_reinigungsbereich"] = {"device_id": "robot"}
        robot = vacuum_items(self.states, self.metadata)[0]
        self.assertEqual(robot["battery_level"], 100)
        self.assertEqual(robot["metrics"]["area"]["state"], "21.4")
        self.assertEqual([m["entity_id"] for m in robot["maps"]], ["image.robot_keller"])
        self.assertIn("start", robot["actions"])
        self.assertNotIn("locate", robot["actions"])

    def test_missing_metadata_and_battery_are_not_invented(self):
        robot = vacuum_items(self.states, {})[0]
        self.assertIsNone(robot["battery_level"])
        self.assertFalse(robot["metadata_available"])
        self.assertEqual(robot["maps"], [])

    def test_start_and_pause_are_explicit_targeted_services(self):
        self.assertEqual(self.service.command("vacuum.robot", "start")["status"], "accepted")
        self.ha.call_service.assert_called_once_with("vacuum", "start", {"entity_id": "vacuum.robot"})

    def test_offline_and_unsupported_commands_are_blocked(self):
        with self.assertRaises(ValueError):
            self.service.command("vacuum.robot", "locate")
        self.states[0]["state"] = "unavailable"
        with self.assertRaises(ValueError):
            self.service.command("vacuum.robot", "start")
        self.ha.call_service.assert_not_called()

    def test_related_control_and_option_validation(self):
        for action, target, option in [("select_option", "select.other", "mop"), ("select_option", "select.robot_mode", "invalid"), ("set_fan_speed", None, "invalid"), ("send_command", None, None)]:
            with self.assertRaises(ValueError):
                self.service.command("vacuum.robot", action, target, option)
        self.ha.call_service.assert_not_called()
        self.service.command("vacuum.robot", "select_option", "select.robot_mode", "mop")
        self.ha.call_service.assert_called_once_with("select", "select_option", {"entity_id": "select.robot_mode", "option": "mop"})

    def test_routine_unknown_state_is_valid_but_cannot_change_while_cleaning(self):
        self.service.command("vacuum.robot", "press", "button.robot_routine")
        self.ha.call_service.assert_called_once_with("button", "press", {"entity_id": "button.robot_routine"})
        self.states[0]["state"] = "cleaning"
        with self.assertRaises(ValueError):
            self.service.command("vacuum.robot", "select_option", "select.robot_mode", "mop")

    def test_map_cannot_access_other_device_or_arbitrary_path(self):
        for target in ["image.other", "../../secrets", "https://example.com"]:
            with self.assertRaises(ValueError):
                self.service.map_image("vacuum.robot", target)
        self.ha.get_image.assert_not_called()
        self.ha.get_image.return_value = (b"image", "image/png")
        self.assertEqual(self.service.map_image("vacuum.robot", "image.robot_keller"), (b"image", "image/png"))
        self.ha.get_image.assert_called_once_with("image.robot_keller")

    def test_map_fetch_rejects_url_before_network(self):
        from backend.services.homeassistant_service import HomeAssistantService
        with self.assertRaises(ValueError):
            HomeAssistantService().get_image("https://example.com/private")

    def test_context_notices_only_when_relevant(self):
        now = datetime(2026, 9, 14, 12, tzinfo=timezone.utc)
        device = {"name": "Roborock", "state": "docked", "metrics": {"charging": {"state": "on"}}}
        self.assertIsNone(vacuum_notice(device, now))
        for state, kind in [("cleaning", "cleaning"), ("paused", "paused"), ("returning", "returning"), ("error", "error"), ("unavailable", "unavailable")]:
            notice = vacuum_notice({**device, "state": state}, now)
            self.assertEqual(notice["kind"], kind)
        self.assertEqual(vacuum_notice({**device, "metrics": {"water_low": {"state": "on"}}}, now)["kind"], "water_low")

    def test_completion_notice_expires_and_never_uses_last_updated(self):
        now = datetime(2026, 9, 14, 12, tzinfo=timezone.utc)
        for seconds, expected in [(60, True), (1799, True), (1800, False), (86400, False), (-10, False)]:
            device = {"name": "Roborock", "state": "docked", "last_updated": now.isoformat(), "metrics": {"last_end": {"state": (now - timedelta(seconds=seconds)).isoformat()}}}
            self.assertEqual(vacuum_notice(device, now) is not None, expected)
        self.assertIsNone(vacuum_notice({"name": "Roborock", "state": "docked", "last_updated": now.isoformat(), "metrics": {}}, now))

    def test_fault_takes_priority_over_cleaning_and_finished(self):
        device = {"name": "Roborock", "state": "cleaning", "metrics": {"error": {"state": "lidar_blocked"}}}
        notice = vacuum_notice(device)
        self.assertEqual(notice["kind"], "error")
        self.assertEqual(notice["detail"], "Lasersensor blockiert")


if __name__ == "__main__":
    unittest.main()
