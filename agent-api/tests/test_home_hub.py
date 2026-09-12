import asyncio
import json
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from backend.services.home_hub.store import HubStore
from backend.services.home_hub.service import HomeHub
from backend.services.home_hub.actions import ActionService
from backend.services.home_hub.assistant import HouseAssistant


def state(entity_id="light.room", value="off", updated="2026-09-12T10:00:00+00:00"):
    return {"entity_id": entity_id, "state": value, "attributes": {"friendly_name": "Room light"}, "last_updated": updated}


class HomeHubTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = HubStore(Path(self.tmp.name) / "hub.db")
        self.ha = Mock()
        self.hub = HomeHub(self.store, self.ha)
        self.hub.connected = self.hub.ready = True
        self.hub.last_received = time.monotonic()
        self.store.replace("states", [state()], "entity_id")

    def test_registry_retains_disabled_entities_and_entity_area_override(self):
        self.store.replace("entities", [{"entity_id": "light.room", "device_id": "device1", "area_id": "room2"}, {"entity_id": "sensor.disabled", "disabled_by": "user"}], "entity_id")
        self.store.replace("devices", [{"id": "device1", "area_id": "room1", "name": "Lamp"}, {"id": "orphan"}], "id")
        self.store.replace("areas", [{"area_id": "room2", "name": "Kitchen", "floor_id": "floor1"}], "area_id")
        self.store.replace("floors", [{"floor_id": "floor1", "name": "Upstairs"}], "floor_id")
        result = self.hub.inventory(limit=1)
        self.assertEqual(result["total"], 2)
        self.assertEqual(result["next_offset"], 1)
        self.assertEqual(result["items"][0]["area"], "Kitchen")
        self.assertEqual(result["items"][0]["floor"], "Upstairs")
        self.assertEqual(self.hub.inventory(offset=1)["items"][0]["state"], "missing")
        self.assertEqual(len(self.store.items("devices")), 2)

    def test_disconnect_is_stale_not_healthy(self):
        self.hub.connected = False
        self.assertEqual(self.hub.status()["quality"], "stale")
        self.assertEqual(self.hub.availability()["quality"], "stale")

    def test_availability_includes_non_zigbee_and_unknown(self):
        self.store.replace("states", [state("light.wifi", "unavailable"), state("sensor.matter", "unknown")], "entity_id")
        result = self.hub.availability()
        self.assertEqual(len(result["devices_with_issues"]), 2)

    def test_event_older_than_snapshot_does_not_overwrite(self):
        self.hub.accept_event({"event_type": "state_changed", "data": {"entity_id": "light.room", "new_state": state(value="on", updated="2026-09-12T09:59:00+00:00")}})
        self.assertEqual(self.hub.states()[0]["state"], "off")
        self.hub.accept_event({"event_type": "state_changed", "data": {"entity_id": "light.room", "new_state": state(value="on", updated="2026-09-12T10:01:00+00:00")}})
        self.assertEqual(self.hub.states()[0]["state"], "on")
        self.assertEqual(len(self.store.history("light.room")), 1)

    def test_action_needs_owner_confirmation_and_cannot_replay(self):
        actions = ActionService(self.hub, timeout=0.1)
        proposal = actions.propose("alice", {"entity_id": "light.room", "service": "turn_on"})
        self.ha.call_service.assert_not_called()
        with self.assertRaises(ValueError):
            actions.confirm("bob", proposal["id"])
        self.ha.get_state.side_effect = [state(), state(value="on")]
        self.ha.call_service.return_value = {"ok": True}
        self.assertEqual(actions.confirm("alice", proposal["id"])["status"], "verified")
        with self.assertRaises(ValueError):
            actions.confirm("alice", proposal["id"])
        self.ha.call_service.assert_called_once()

    def test_stale_action_is_not_dispatched(self):
        actions = ActionService(self.hub)
        proposal = actions.propose("alice", {"entity_id": "light.room", "service": "turn_on"})
        self.hub.connected = False
        self.assertEqual(actions.confirm("alice", proposal["id"])["status"], "failed")
        self.ha.call_service.assert_not_called()

    def test_expired_action_is_not_dispatched(self):
        proposal = ActionService(self.hub).propose("alice", {"entity_id": "light.room", "service": "turn_on"})
        with self.store.connect() as db:
            db.execute("UPDATE actions SET expires_at = '2000' WHERE id = ?", (proposal["id"],))
        with self.assertRaises(ValueError):
            ActionService(self.hub).confirm("alice", proposal["id"])
        self.ha.call_service.assert_not_called()

    def test_unconfirmed_physical_result_is_not_success(self):
        actions = ActionService(self.hub, timeout=0.01)
        proposal = actions.propose("alice", {"entity_id": "light.room", "service": "turn_on"})
        self.ha.get_state.return_value = state()
        self.ha.call_service.return_value = {"ok": True}
        self.assertEqual(actions.confirm("alice", proposal["id"])["status"], "unverified")

    def test_forbidden_service_rejected(self):
        with self.assertRaises(ValueError):
            ActionService(self.hub).propose("alice", {"entity_id": "light.room", "service": "delete"})

    def make_rule(self, principal="alice"):
        self.store.replace("states", [state(), state("binary_sensor.motion", "on")], "entity_id")
        return ActionService(self.hub).propose_rule(principal, {"entity_id": "binary_sensor.motion", "to": "on"}, {"entity_id": "light.room", "service": "turn_on"})

    def test_rule_activation_owner_and_conflict(self):
        rule = self.make_rule()
        actions = ActionService(self.hub)
        with self.assertRaises(ValueError):
            actions.activate_rule("bob", rule["id"])
        self.assertEqual(actions.activate_rule("alice", rule["id"])["mode"], "active")
        other = self.make_rule("bob")
        with self.assertRaises(ValueError):
            actions.activate_rule("bob", other["id"])
        self.ha.call_service.assert_not_called()

    def test_active_rule_executes_once_then_cooldown(self):
        rule = self.make_rule()
        actions = ActionService(self.hub, timeout=0.1)
        actions.activate_rule("alice", rule["id"])
        self.ha.get_state.side_effect = [state(), state(value="on")]
        self.ha.call_service.return_value = {"ok": True}
        self.assertEqual(actions.run_rule(rule["id"], "alice")["status"], "verified")
        self.assertEqual(actions.run_rule(rule["id"], "alice")["status"], "skipped")
        self.ha.call_service.assert_called_once()

    def test_external_change_holds_rule(self):
        rule = self.make_rule()
        actions = ActionService(self.hub)
        actions.activate_rule("alice", rule["id"])
        self.hub.accept_event({"event_type": "state_changed", "data": {"entity_id": "light.room", "old_state": state(), "new_state": state(value="on", updated="2026-09-12T11:00:00+00:00")}})
        self.assertGreater(self.store.rule(rule["id"], "alice")["hold_until"], time.time())
        self.assertEqual(actions.run_rule(rule["id"], "alice")["status"], "skipped")
        self.ha.call_service.assert_not_called()

    def test_paused_or_changed_trigger_rule_cannot_execute(self):
        rule = self.make_rule()
        actions = ActionService(self.hub)
        actions.activate_rule("alice", rule["id"])
        self.store.replace("states", [state(), state("binary_sensor.motion", "off")], "entity_id")
        self.assertEqual(actions.run_rule(rule["id"], "alice")["status"], "failed")
        text = HouseAssistant(self.hub).answer("/pause " + rule["id"], "alice")
        self.assertIn("Beobachtung", text)
        self.assertEqual(actions.run_rule(rule["id"], "alice")["status"], "skipped")
        self.ha.call_service.assert_not_called()

    def test_rule_activation_blocks_monitor_and_self_trigger(self):
        rule = self.make_rule()
        actions = ActionService(self.hub)
        with patch.dict("os.environ", {"ROBOTERSTEVE_MONITOR_ONLY": "1"}):
            with self.assertRaises(ValueError):
                actions.activate_rule("alice", rule["id"])
        loop = actions.propose_rule("alice", {"entity_id": "light.room", "to": "on"}, {"entity_id": "light.room", "service": "turn_off"})
        with self.assertRaises(ValueError):
            actions.activate_rule("alice", loop["id"])

    def test_model_has_no_rule_activation_tool(self):
        with self.assertRaises(ValueError):
            HouseAssistant(self.hub).query("activate_rule", {}, "alice")

    def test_manual_change_invalidates_proposal(self):
        actions = ActionService(self.hub)
        proposal = actions.propose("alice", {"entity_id": "light.room", "service": "turn_on"})
        self.ha.get_state.return_value = state(value="on", updated="2026-09-12T10:01:00+00:00")
        self.assertEqual(actions.confirm("alice", proposal["id"])["status"], "failed")
        self.ha.call_service.assert_not_called()

    def test_monitor_mode_blocks_confirmation(self):
        actions = ActionService(self.hub)
        proposal = actions.propose("alice", {"entity_id": "light.room", "service": "turn_on"})
        with patch.dict("os.environ", {"ROBOTERSTEVE_MONITOR_ONLY": "1"}):
            with self.assertRaises(ValueError):
                actions.confirm("alice", proposal["id"])
        self.ha.call_service.assert_not_called()

    def test_failed_notification_retries_after_restart_without_resending_success(self):
        from backend.services.home_hub.delivery import DeliveryService
        service = DeliveryService(self.store)
        service.enqueue("alert1", "telegram", "chat1", {"text": "Test"})
        service.enqueue("alert1", "telegram", "chat2", {"text": "Test"})
        service.enqueue("alert1", "telegram", "chat1", {"text": "Test"})
        def sender(channel, target, payload):
            if target == "chat2":
                raise RuntimeError("Offline")
        service.drain(sender)
        self.assertEqual(service.summary(), {"pending": 1, "sent": 1})
        with self.store.connect() as db:
            db.execute("UPDATE deliveries SET next_attempt = 0")
        restarted = DeliveryService(HubStore(self.store.path))
        record = Mock()
        restarted.drain(record)
        record.assert_called_once_with("telegram", "chat2", {"text": "Test"})
        self.assertEqual(restarted.summary(), {"sent": 2})

    def test_ha_stream_correlates_results_and_resyncs_inventory(self):
        hub = self.hub
        class Socket:
            def __init__(self):
                self.messages = [{"type": "auth_required"}]
                self.sent = []
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                pass
            async def send(self, raw):
                message = json.loads(raw)
                self.sent.append(message)
                if message["type"] == "auth":
                    self.messages.append({"type": "auth_ok"})
                    return
                result = []
                if message["type"] == "get_states":
                    self.messages.append({"id": 1, "type": "event", "event": {"event_type": "state_changed", "data": {"entity_id": "light.room", "new_state": state(value="on", updated="2026-09-12T10:01:00+00:00")}}})
                    result = [state()]
                self.messages.append({"id": message["id"], "type": "result", "success": True, "result": result})
            async def recv(self):
                if self.messages:
                    return json.dumps(self.messages.pop(0))
                hub.stop_event.set()
                return json.dumps({"type": "pong"})
        socket = Socket()
        self.ha.token = "test-token"
        self.ha._websocket_url.return_value = "ws://test/api/websocket"
        with patch("websockets.connect", return_value=socket), patch.object(hub, "_update_context"):
            asyncio.run(hub._stream())
        self.assertEqual(hub.states()[0]["state"], "on")
        self.assertEqual(hub.registry_errors, {})
        self.assertTrue(hub.ready)
        self.assertIn("config/floor_registry/list", [item["type"] for item in socket.sent])

    def test_scheduler_failure_payload_is_not_completed(self):
        from backend.agents.scheduler.service import SchedulerService
        store = Mock()
        store.record_run.side_effect = lambda task, status, *args: {"status": status}
        scheduler = SchedulerService(store=store, messaging=Mock())
        with patch.object(scheduler, "_target_agent_skip_reason", return_value=None), patch.object(scheduler, "_execute_action", return_value={"ok": False, "error": "HA offline"}), patch.object(scheduler, "_notify_failure"):
            result = scheduler.execute_task({"name": "check"})
        self.assertEqual(result["status"], "error")

    def test_agent_adapter_propagates_failure_flag(self):
        from backend.agents.control import AgentControlAdapter
        service = SimpleNamespace(run=lambda: {"ok": False, "message": "Failed"})
        result = AgentControlAdapter("test", service).execute("run")
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "error")

    def test_detected_alarm_is_not_a_scheduler_execution_failure(self):
        from backend.agents.scheduler.service import SchedulerService
        store = Mock()
        store.record_run.side_effect = lambda task, status, *args: {"status": status}
        scheduler = SchedulerService(store=store, messaging=Mock())
        with patch.object(scheduler, "_target_agent_skip_reason", return_value=None), patch.object(scheduler, "_execute_action", return_value={"ok": False, "execution_ok": True, "active_alerts": [{"severity": "critical"}]}), patch.object(scheduler, "_should_notify_success", return_value=False):
            result = scheduler.execute_task({"name": "check"})
        self.assertEqual(result["status"], "completed")

    def test_hub_api_requires_authentication(self):
        from fastapi.testclient import TestClient
        from backend.main import app
        client = TestClient(app)
        self.addCleanup(client.close)
        self.assertEqual(client.get("/api/home-hub/status").status_code, 401)
        self.assertEqual(client.post("/api/home-hub/chat", json={"message": "hi"}).status_code, 401)

    def test_history_queries_recorder_with_pagination(self):
        self.ha.get_entity_history.return_value = [state() for _ in range(35)]
        result = HouseAssistant(self.hub).query("history", {"entity_id": "light.room", "start": "2026-09-11T00:00:00+02:00", "end": "2026-09-12T00:00:00+02:00"}, "alice")
        self.assertEqual(result["source"], "home_assistant_recorder")
        self.assertEqual(result["total"], 35)
        self.assertEqual(result["next_offset"], 30)

    def test_registry_history_rejects_unbounded_time_window(self):
        from backend.services.homeassistant_service import HomeAssistantService
        with self.assertRaises(ValueError):
            HomeAssistantService().get_entity_history("light.room", "2026-01-01T00:00:00Z", "2026-09-01T00:00:00Z")

    def test_observation_rule_never_sends_command(self):
        rule = ActionService(self.hub).propose_rule("alice", {"entity_id": "light.room", "to": "on"}, {"entity_id": "light.room", "service": "turn_off"})
        self.hub.accept_event({"event_type": "state_changed", "data": {"entity_id": "light.room", "old_state": state(), "new_state": state(value="on", updated="2026-09-12T10:01:00+00:00")}})
        self.assertEqual(self.store.history(rule["id"])[0]["kind"], "automation_observation")
        self.ha.call_service.assert_not_called()

    def test_assistant_queries_tools_and_remembers_separate_conversations(self):
        llm = Mock()
        llm.generate.side_effect = [SimpleNamespace(text=json.dumps({"tool": "find_entities", "arguments": {"domain": "light"}})), SimpleNamespace(text=json.dumps({"answer": "Room light ist aus."}))]
        assistant = HouseAssistant(self.hub, llm_factory=lambda: llm)
        self.assertEqual(assistant.answer("Welche Lichter sind an?", "alice"), "Room light ist aus.")
        self.assertEqual(len(self.store.conversation("alice")), 2)
        self.assertEqual(self.store.conversation("bob"), [])
        self.assertIn("light.room", llm.generate.call_args.kwargs["prompt"])

    def test_assistant_cannot_confirm_via_tool(self):
        with self.assertRaises(ValueError):
            HouseAssistant(self.hub).query("confirm", {}, "alice")

    def test_telegram_uses_shared_assistant_and_identity(self):
        from backend.agents.telegram.service import TelegramService
        with patch("backend.services.home_hub.assistant.HouseAssistant") as factory:
            factory.return_value.answer.return_value = "Hausantwort"
            result = TelegramService(messaging=Mock()).answer("Status?", principal="telegram:1:2")
        self.assertEqual(result, "Hausantwort")
        factory.return_value.answer.assert_called_once_with("Status?", "telegram:1:2")

    def test_failed_registry_does_not_produce_all_clear(self):
        from backend.agents.telegram.service import _home_assistant_snapshot, _house_status_answer
        result = _house_status_answer("Sind alle Geraete erreichbar?", {"home_assistant": _home_assistant_snapshot([state(value="unavailable")], {})})
        self.assertNotIn("Alle Zigbee", result)
        self.assertIn("unbekannt", result)


if __name__ == "__main__":
    unittest.main()
