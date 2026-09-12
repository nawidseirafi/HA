from __future__ import annotations

import asyncio
import json
import os
import queue
import threading
import time
from datetime import datetime, timezone
from typing import Any

from backend.services.home_hub.store import HubStore, now


REGISTRIES = {"entities": "entity", "devices": "device", "areas": "area", "floors": "floor"}


def public_data(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: public_data(item) for key, item in value.items()
                if not any(part in key.lower() for part in ("token", "secret", "password", "api_key", "headers", "cookie"))}
    if isinstance(value, (list, tuple)):
        return [public_data(item) for item in value]
    return value


class HomeHub:
    _instance: "HomeHub | None" = None
    _instance_lock = threading.Lock()

    def __init__(self, store: HubStore | None = None, ha=None) -> None:
        from backend.services.homeassistant_service import HomeAssistantService

        self.store = store or HubStore()
        self.ha = ha or HomeAssistantService()
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.delivery_thread: threading.Thread | None = None
        self.agent_thread: threading.Thread | None = None
        self.rule_thread: threading.Thread | None = None
        self.rule_queue: queue.Queue = queue.Queue(maxsize=100)
        self.command_lock = threading.Lock()
        self.command_targets: set[str] = set()
        self.command_updates: dict[str, str | None] = {}
        self.connected = False
        self.ready = False
        self.last_received = 0.0
        self.error: str | None = None
        self.context_snapshot = None
        self.context_updated_at = 0.0
        self.registry_errors: dict[str, str] = {kind: "not_synced" for kind in REGISTRIES}

    @classmethod
    def default(cls) -> "HomeHub":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
        return cls._instance

    def start(self, dispatch_notifications: bool = True) -> None:
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.store.recover()
        self.thread = threading.Thread(target=self._run, name="home-hub", daemon=True)
        self.thread.start()
        self.agent_thread = threading.Thread(target=self._agent_health, name="home-hub-agent-health", daemon=True)
        self.agent_thread.start()
        if dispatch_notifications:
            self.delivery_thread = threading.Thread(target=self._deliveries, name="home-hub-deliveries", daemon=True)
            self.delivery_thread.start()
            self.rule_thread = threading.Thread(target=self._rules, name="home-hub-rules", daemon=True)
            self.rule_thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=12)
        if self.delivery_thread:
            self.delivery_thread.join(timeout=2)
        if self.agent_thread:
            self.agent_thread.join(timeout=2)
        if self.rule_thread:
            self.rule_thread.join(timeout=2)
        self.ready = False

    def healthy(self) -> bool:
        return self.connected and self.ready and time.monotonic() - self.last_received < 45

    def _deliveries(self) -> None:
        from backend.services.home_hub.delivery import DeliveryService
        while not self.stop_event.is_set():
            try:
                DeliveryService(self.store).drain(should_stop=self.stop_event.is_set)
            except Exception as exc:
                self.store.event("notification_worker", "delivery", {"error": type(exc).__name__})
            self.stop_event.wait(15)

    def _agent_health(self) -> None:
        while not self.stop_event.is_set():
            try:
                for item in self.agents()["items"]:
                    runtime = item.get("runtime", {})
                    data = runtime.get("data", {})
                    health = {"enabled": item["enabled"], "status": runtime.get("status"),
                              "last_error": data.get("last_error") or runtime.get("error"),
                              "last_successful_run": data.get("last_successful_run"),
                              "scheduler_running": data.get("scheduler_running", data.get("is_running"))}
                    key = "agent:" + item["id"]
                    if self.store.meta(key) != health:
                        self.store.meta(key, health)
                        self.store.event("agent_health", item["id"], health)
            except Exception as exc:
                self.store.event("agent_health", "registry", {"error": type(exc).__name__})
            self.stop_event.wait(60)

    def begin_action(self, entity_id: str) -> None:
        with self.command_lock:
            self.command_targets.add(entity_id)

    def end_action(self, entity_id: str, state: dict | None) -> None:
        with self.command_lock:
            self.command_updates[entity_id] = (state or {}).get("last_updated")
            self.command_targets.discard(entity_id)

    def _rules(self) -> None:
        from backend.services.home_hub.actions import ActionService
        while not self.stop_event.is_set():
            try:
                rule_id, principal, queued_at = self.rule_queue.get(timeout=1)
            except queue.Empty:
                continue
            try:
                if time.monotonic() - queued_at <= 30 and not self.stop_event.is_set():
                    result = ActionService(self).run_rule(rule_id, principal)
                    self.store.event("automation_execution", rule_id, {"status": result["status"], "action_id": result.get("id")})
                else:
                    self.store.event("automation_execution", rule_id, {"status": "expired_trigger"})
            except Exception as exc:
                self.store.event("automation_execution", rule_id, {"status": "failed", "error": type(exc).__name__})
            finally:
                self.rule_queue.task_done()

    def status(self) -> dict:
        from backend.services.home_hub.delivery import DeliveryService
        counts = self.store.counts()
        return {"source": "home_assistant", "connected": self.connected,
                "monitor_only": os.getenv("ROBOTERSTEVE_MONITOR_ONLY", "0") == "1",
                "deliveries": DeliveryService(self.store).summary(),
                "quality": "live" if self.healthy() else "stale" if counts.get("states") else "unknown",
                "last_sync": self.store.meta("last_sync"), "error": self.error,
                "registry_errors": self.registry_errors,
                "counts": {kind: counts.get(kind, 0) for kind in ("states", *REGISTRIES)}}

    def states(self) -> list[dict]:
        return self.store.items("states")

    def _inventory_items(self) -> list[dict]:
        states = {item["entity_id"]: item for item in self.states()}
        entities = {item["entity_id"]: item for item in self.store.items("entities")}
        devices = {item["id"]: item for item in self.store.items("devices")}
        areas = {item["area_id"]: item for item in self.store.items("areas")}
        floors = {item["floor_id"]: item for item in self.store.items("floors")}
        items = []
        for entity_id in sorted(states.keys() | entities.keys()):
            entity = entities.get(entity_id, {})
            state = states.get(entity_id, {})
            device = devices.get(entity.get("device_id"), {})
            area_id = entity.get("area_id") or device.get("area_id")
            room = areas.get(area_id, {})
            floor = floors.get(room.get("floor_id"), {})
            item = {"entity_id": entity_id, "name": entity.get("name") or state.get("attributes", {}).get("friendly_name") or entity.get("original_name") or entity_id,
                    "device_id": entity.get("device_id"), "device_name": device.get("name_by_user") or device.get("name"),
                    "area_id": area_id, "area": room.get("name"), "floor": floor.get("name"),
                    "disabled_by": entity.get("disabled_by"), "platform": entity.get("platform"),
                    "state": state.get("state", "missing"), "attributes": state.get("attributes", {}),
                    "last_updated": state.get("last_updated"), "last_changed": state.get("last_changed")}
            items.append(public_data(item))
        return items

    def inventory(self, query: str = "", domain: str = "", area: str = "", offset: int = 0, limit: int = 50) -> dict:
        items = []
        for item in self._inventory_items():
            haystack = " ".join(str(item.get(key) or "") for key in ("entity_id", "name", "device_name", "area", "floor")).casefold()
            if query.casefold() not in haystack or (domain and not item["entity_id"].startswith(domain + ".")):
                continue
            if area and area.casefold() not in {str(item["area_id"]).casefold(), str(item["area"]).casefold()}:
                continue
            items.append(item)
        offset, limit = max(0, offset), max(1, min(limit, 100))
        return {"quality": self.status()["quality"], "total": len(items), "offset": offset,
                "next_offset": offset + limit if offset + limit < len(items) else None, "items": items[offset:offset + limit]}

    def availability(self) -> dict:
        items = self._inventory_items()
        by_device: dict[str, list] = {}
        for item in items:
            if item["disabled_by"]:
                continue
            key = item["device_id"] or item["entity_id"]
            by_device.setdefault(key, []).append(item)
        result = []
        for key, entities in by_device.items():
            unknown = [item for item in entities if item["state"] in {"unavailable", "unknown", "missing"}]
            if unknown:
                result.append({"id": key, "name": entities[0]["device_name"] or entities[0]["name"],
                               "status": "unavailable" if all(item["state"] == "unavailable" for item in entities) else "partial_or_unknown",
                               "affected_entities": [item["entity_id"] for item in unknown]})
        return {"quality": self.status()["quality"], "registry_errors": self.registry_errors, "devices_with_issues": result,
                "checked_devices_or_entities": len(by_device)}

    def agents(self, agent_id: str = "") -> dict:
        from backend.agents.registry import discover_agent_manifests, get_agent_control
        items = []
        for manifest in discover_agent_manifests():
            if agent_id and manifest.id != agent_id:
                continue
            item = {"id": manifest.id, "name": manifest.name, "enabled": manifest.enabled}
            try:
                control = get_agent_control(manifest.id)
                item["capabilities"] = control.capabilities() if control else []
                item["runtime"] = public_data(control.execute("status")) if control and "status" in item["capabilities"] else {"status": "unknown"}
            except Exception as exc:
                item["runtime"] = {"status": "error", "error": type(exc).__name__}
            items.append(item)
        return {"observed_at": now(), "items": items}

    def context(self) -> dict:
        snapshot = self.context_snapshot.as_dict() if self.context_snapshot else self.store.meta("context")
        return {**snapshot, "quality": self.status()["quality"], "current_state_confirmed": self.healthy()}

    def _update_context(self) -> None:
        from backend.services.context import ContextService
        service = ContextService.default()
        snapshot = service.evaluate(self.states(), ha_error=None if self.healthy() else "HA snapshot is stale")
        self.context_snapshot = snapshot
        self.context_updated_at = time.monotonic()
        self.store.meta("context", snapshot.as_dict())
        service.store.save_snapshot(snapshot.as_dict(include_debug=True))

    def _run(self) -> None:
        backoff = 1
        while not self.stop_event.is_set():
            try:
                asyncio.run(self._stream())
                backoff = 1
            except Exception as exc:
                self.error = type(exc).__name__
                self.store.event("connection", "home_assistant", {"status": "disconnected", "error": self.error})
            finally:
                self.connected = self.ready = False
            self.stop_event.wait(backoff)
            backoff = min(backoff * 2, 30)

    async def _stream(self) -> None:
        import websockets

        if not self.ha.configured():
            raise RuntimeError("Home Assistant is not configured")
        async with websockets.connect(self.ha._websocket_url(), open_timeout=5, close_timeout=1) as ws:
            async def receive():
                result = json.loads(await asyncio.wait_for(ws.recv(), timeout=8))
                self.last_received = time.monotonic()
                return result

            if (await receive()).get("type") != "auth_required":
                raise RuntimeError("Unexpected HA handshake")
            await ws.send(json.dumps({"type": "auth", "access_token": self.ha.token}))
            if (await receive()).get("type") != "auth_ok":
                raise RuntimeError("HA authentication failed")
            self.connected = True
            self.ready = False
            command_id = 0
            pending_events: list[dict] = []

            async def command(payload):
                nonlocal command_id
                command_id += 1
                await ws.send(json.dumps({**payload, "id": command_id}))
                while not self.stop_event.is_set():
                    response = await receive()
                    if response.get("id") == command_id and response.get("type") in {"result", "pong"}:
                        if response.get("success") is False:
                            raise RuntimeError("HA command rejected: " + str(payload.get("type")))
                        return response.get("result")
                    if response.get("type") == "event":
                        pending_events.append(response["event"])
                raise RuntimeError("Stopping")

            await command({"type": "subscribe_events", "event_type": "state_changed"})
            for name in REGISTRIES.values():
                await command({"type": "subscribe_events", "event_type": f"{name}_registry_updated"})

            async def sync():
                self.ready = False
                states = await command({"type": "get_states"})
                self.store.replace("states", states, "entity_id")
                errors = {}
                for kind, registry in REGISTRIES.items():
                    try:
                        rows = await command({"type": f"config/{registry}_registry/list"})
                        key = {"entities": "entity_id", "devices": "id", "areas": "area_id", "floors": "floor_id"}[kind]
                        self.store.replace(kind, rows, key)
                    except RuntimeError:
                        errors[kind] = "registry_unavailable"
                self.registry_errors = errors
                self.store.meta("last_sync", {"at": now(), "registry_errors": errors})
                self.error = None
                # Apply only changes newer than the fetched state; queued events may precede the snapshot.
                buffered = list(pending_events)
                pending_events.clear()
                for event in buffered:
                    self.accept_event(event)
                self.ready = True
                self._update_context()

            await sync()
            self.store.event("connection", "home_assistant", {"status": "connected"})
            synced_at = time.monotonic()
            while not self.stop_event.is_set():
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=3)
                    self.last_received = time.monotonic()
                    message = json.loads(raw)
                    event = message.get("event", {})
                    if event.get("event_type", "").endswith("registry_updated"):
                        await sync()
                    elif message.get("type") == "event":
                        self.accept_event(event)
                except asyncio.TimeoutError:
                    await command({"type": "ping"})
                for event in pending_events:
                    self.accept_event(event)
                pending_events.clear()
                if time.monotonic() - self.context_updated_at >= 5:
                    self._update_context()
                if time.monotonic() - synced_at > 300:
                    await sync()
                    self.store.prune()
                    synced_at = time.monotonic()

    def accept_event(self, event: dict) -> None:
        if event.get("event_type") != "state_changed":
            return
        data = event.get("data", {})
        entity_id = data.get("entity_id")
        if not entity_id:
            return
        state = data.get("new_state")
        current = self.store.item("states", entity_id)
        incoming_time = (state or {}).get("last_updated") or event.get("time_fired")
        if current and incoming_time and current.get("last_updated"):
            if datetime.fromisoformat(incoming_time.replace("Z", "+00:00")) < datetime.fromisoformat(current["last_updated"].replace("Z", "+00:00")):
                return
        self.store.state_event(entity_id, state, public_data(event))
        for rule in self.store.rules():
            payload = rule["payload"]
            trigger = payload["trigger"]
            if rule["mode"] == "active" and payload["action"].get("entity_id") == entity_id:
                def control_values(item):
                    return [(item or {}).get("state"), *((item or {}).get("attributes", {}).get(key) for key in ("brightness", "percentage", "temperature", "current_position"))]
                with self.command_lock:
                    own_change = entity_id in self.command_targets or (state and state.get("last_updated") and state.get("last_updated") == self.command_updates.get(entity_id))
                if not own_change and control_values(data.get("old_state")) != control_values(state):
                    self.store.hold_rule(rule["id"])
            old_state = (data.get("old_state") or {}).get("state")
            if trigger["entity_id"] == entity_id and state and state.get("state") == trigger["to"] and old_state != trigger["to"]:
                self.store.event("automation_observation", rule["id"], {"mode": rule["mode"], "would_propose": payload["action"], "trigger": data})
                if rule["mode"] == "active" and self.healthy() and not os.getenv("ROBOTERSTEVE_MONITOR_ONLY", "0") == "1":
                    try:
                        self.rule_queue.put_nowait((rule["id"], rule["principal"], time.monotonic()))
                    except queue.Full:
                        self.store.event("automation_execution", rule["id"], {"status": "queue_full"})
