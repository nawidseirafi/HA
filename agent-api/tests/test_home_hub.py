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

    def vacuum_state(self, value="docked"):
        item = state("vacuum.robot", value)
        item["attributes"] = {"friendly_name": "Roborock", "supported_features": 8192 | 4 | 8 | 16}
        return item

    def test_vacuum_question_reads_device_data_before_model(self):
        self.store.replace("states", [self.vacuum_state(), state("sensor.robot_batterie", "80")], "entity_id")
        self.store.replace("entities", [{"entity_id": id, "device_id": "robot"} for id in ("vacuum.robot", "sensor.robot_batterie")], "entity_id")
        self.store.replace("devices", [{"id": "robot", "manufacturer": "Roborock"}], "id")
        llm = Mock()
        llm.generate.return_value = SimpleNamespace(text=json.dumps({"answer": "Roborock ist in der Station, Akku 80 %."}))
        assistant = HouseAssistant(self.hub, llm_factory=lambda: llm)
        assistant.answer("Wie geht es dem Saugroboter?", "alice")
        context = json.loads(llm.generate.call_args.kwargs["prompt"])
        self.assertEqual(context["tool_results"][0]["tool"], "vacuum_status")
        self.assertEqual(context["tool_results"][0]["result"]["items"][0]["battery_level"], 80)
        self.ha.call_service.assert_not_called()
        self.hub.connected = False
        self.assertEqual(assistant.query("vacuum_status", {}, "alice")["quality"], "stale")

    def test_vacuum_command_is_proposal_until_explicit_confirmation(self):
        self.store.replace("states", [self.vacuum_state()], "entity_id")
        llm = Mock()
        llm.generate.return_value = SimpleNamespace(text=json.dumps({"tool": "propose_vacuum_action", "arguments": {"entity_id": "vacuum.robot", "service": "start"}}))
        assistant = HouseAssistant(self.hub, llm_factory=lambda: llm)
        text = assistant.answer("Starte den Saugroboter", "alice")
        self.assertIn("/confirm ", text)
        self.ha.call_service.assert_not_called()
        command = text.splitlines()[-1]
        self.ha.get_state.side_effect = [self.vacuum_state(), self.vacuum_state("cleaning")]
        self.ha.call_service.return_value = {"ok": True}
        answer = assistant.answer(command, "alice")
        self.assertIn("Roboterstatus: reinigt", answer)
        self.ha.call_service.assert_called_once_with("vacuum", "start", {"entity_id": "vacuum.robot"})
        assistant.answer(command, "alice")
        self.ha.call_service.assert_called_once()

    def test_vacuum_returning_does_not_claim_arrival(self):
        self.store.replace("states", [self.vacuum_state("cleaning")], "entity_id")
        assistant = HouseAssistant(self.hub)
        proposal = assistant.query("propose_vacuum_action", {"entity_id": "vacuum.robot", "service": "return_to_base"}, "alice")
        self.ha.get_state.side_effect = [self.vacuum_state("cleaning"), self.vacuum_state("returning")]
        self.ha.call_service.return_value = {"ok": True}
        self.assertIn("noch nicht angekommen", assistant.answer("/confirm " + proposal["id"], "alice"))

    def test_vacuum_actions_check_owner_staleness_and_features(self):
        self.store.replace("states", [self.vacuum_state()], "entity_id")
        actions = ActionService(self.hub)
        proposal = actions.propose("alice", {"entity_id": "vacuum.robot", "service": "start"})
        with self.assertRaises(ValueError):
            actions.confirm("bob", proposal["id"])
        self.hub.connected = False
        self.assertEqual(actions.confirm("alice", proposal["id"])["status"], "failed")
        self.ha.call_service.assert_not_called()
        unsupported = self.vacuum_state()
        unsupported["attributes"]["supported_features"] = 0
        self.store.replace("states", [unsupported], "entity_id")
        with self.assertRaises(ValueError):
            actions.propose("alice", {"entity_id": "vacuum.robot", "service": "start"})
        with self.assertRaises(ValueError):
            actions.propose("alice", {"entity_id": "vacuum.robot", "service": "send_command"})

    def test_house_context_contains_robot_notice_and_separate_house_summary(self):
        from backend.services.context.service import ContextService
        service = ContextService(database_path=Path(self.tmp.name) / "context.db")
        snapshot = service.evaluate([self.vacuum_state("cleaning")]).as_dict()
        self.assertIn("Roborock reinigt gerade", snapshot["summary"])
        self.assertNotIn("Roborock", snapshot["house_summary"])
        self.assertEqual(snapshot["vacuums"][0]["notice"]["kind"], "cleaning")
        stale = service.evaluate([self.vacuum_state("cleaning")], ha_error="offline").as_dict()
        self.assertNotIn("Roborock reinigt gerade", stale["summary"])

    def test_calendar_reads_wall_source_with_explicit_dates(self):
        from backend.services.calendar_service import CalendarService
        ha = Mock()
        ha.get_state.return_value = {"entity_id": "calendar.devcal"}
        ha.get_calendar_events.return_value = [{"summary": "Reservation at: padelBOX", "start": "2026-09-12T19:30:00+02:00", "end": "2026-09-12T21:00:00+02:00"}]
        calendar = CalendarService(ha, "calendar.devcal")
        start, end = HouseAssistant(self.hub)._date_window({"start_date": "2026-09-12", "end_date": "2026-09-12"})
        result = calendar.events(start, end)
        self.assertTrue(result["ok"])
        self.assertEqual(result["items"][0]["title"], "Reservation at: padelBOX")
        ha.get_calendar_events.assert_called_once_with("calendar.devcal", "2026-09-12T00:00:00+02:00", "2026-09-13T00:00:00+02:00")

    def test_calendar_error_is_not_empty_agenda(self):
        from backend.services.calendar_service import CalendarService
        ha = Mock()
        ha.get_state.side_effect = RuntimeError("offline")
        start, end = HouseAssistant(self.hub)._date_window({"start_date": "2026-09-12"})
        result = CalendarService(ha, "calendar.private").events(start, end)
        self.assertFalse(result["ok"])
        self.assertIn("keine Aussage", result["message"])

    def test_calendar_is_loaded_before_first_model_answer(self):
        llm = Mock()
        llm.generate.return_value = SimpleNamespace(text=json.dumps({"answer": "PadelBOX steht um 19:30 im Kalender."}))
        assistant = HouseAssistant(self.hub, llm_factory=lambda: llm)
        result = {"ok": True, "items": [{"title": "padelBOX", "start": "2026-09-12T19:30:00+02:00"}]}
        with patch("backend.services.calendar_service.CalendarService.events", return_value=result):
            answer = assistant.answer("Kalendereintrag padelbox um 19:30 siehst du es nicht?", "alice")
        self.assertIn("19:30", answer)
        context = json.loads(llm.generate.call_args.kwargs["prompt"])
        self.assertEqual(context["tool_results"][0]["tool"], "calendar_events")
        self.assertEqual(context["tool_results"][0]["result"]["items"][0]["title"], "padelBOX")
        self.assertEqual(context["time_context"]["timezone"], "Europe/Berlin")

    def test_mywellness_prepared_is_separate_from_bookings_and_offers(self):
        service = Mock()
        service.prepared_courses.return_value = {"courses": [{"title": "Body Workout", "startTime": "2026-09-14T17:00:00", "booked": False}]}
        service.bookings.return_value = {"bookings": []}
        service.upcoming_courses.return_value = {"courses": [{"title": "Another course", "startTime": "2026-09-14T18:00:00"}]}
        assistant = HouseAssistant(self.hub)
        args = {"agent_id": "mywellness", "start_date": "2026-09-14", "end_date": "2026-09-14"}
        with patch("backend.agents.registry.get_agent_control", return_value=SimpleNamespace(service=service)):
            prepared = assistant.query("agent_data", {**args, "view": "prepared"}, "alice")
            bookings = assistant.query("agent_data", {**args, "view": "bookings"}, "alice")
            offers = assistant.query("agent_data", {**args, "view": "courses"}, "alice")
        self.assertEqual(prepared["items"][0]["start_local"], "2026-09-14T17:00:00+02:00")
        self.assertIn("keine bestaetigte Buchung", prepared["meaning"])
        self.assertEqual(bookings["total"], 0)
        self.assertEqual(offers["items"][0]["title"], "Another course")
        service.courses.assert_not_called()

    def test_prepared_service_reads_all_target_days(self):
        from backend.agents.mywellness.service import MyWellnessService
        service = object.__new__(MyWellnessService)
        with patch("backend.agents.mywellness.service.list_prepared_courses", return_value=[{"title": "Monday"}]) as prepared:
            result = service.prepared_courses()
        prepared.assert_called_once_with()
        self.assertFalse(result["booking_confirmed"])

    def test_mywellness_errors_and_paging_preserved(self):
        service = Mock()
        service.bookings.return_value = {"stale": True, "error": "offline", "bookings": [{"startTime": "2026-09-14T17:00:00"}] * 25}
        with patch("backend.agents.registry.get_agent_control", return_value=SimpleNamespace(service=service)):
            result = HouseAssistant(self.hub).query("agent_data", {"agent_id": "mywellness", "view": "bookings", "start_date": "2026-09-14", "end_date": "2026-09-14"}, "alice")
        self.assertFalse(result["ok"])
        self.assertTrue(result["stale"])
        self.assertEqual(result["total"], 25)
        self.assertEqual(result["next_offset"], 20)
        self.assertEqual(len(result["items"]), 20)

    def test_media_reads_domain_not_german_device_name(self):
        self.store.replace("states", [state("media_player.living_room", "playing"), state("media_player.bedroom", "unavailable"), state("media_player.speaker", "idle")], "entity_id")
        result = HouseAssistant(self.hub).query("media_status", {}, "alice")
        self.assertEqual(result["total"], 3)
        self.assertEqual(result["state_counts"], {"idle": 1, "playing": 1, "unavailable": 1})
        self.assertEqual(HouseAssistant._required_reads("Läuft im Haus irgendwo der Fernseher?"), [("media_status", {})])

    def test_sports_question_checks_both_bookings_and_prepared(self):
        reads = HouseAssistant._required_reads("Wann ist mein nächster Sport Kurs?")
        self.assertEqual({args["view"] for _, args in reads}, {"bookings", "prepared", "courses"})

    def test_date_window_crosses_dst_with_local_midnight(self):
        start, end = HouseAssistant(self.hub)._date_window({"start_date": "2026-10-25", "end_date": "2026-10-25"})
        self.assertEqual(start.isoformat(), "2026-10-25T00:00:00+02:00")
        self.assertEqual(end.isoformat(), "2026-10-26T00:00:00+01:00")
        with self.assertRaises(ValueError):
            HouseAssistant(self.hub)._date_window({"start_date": "2026-09-14", "end_date": "2026-09-12"})

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
