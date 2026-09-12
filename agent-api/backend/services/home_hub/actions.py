from __future__ import annotations

import math
import os
import threading
import time

from backend.services.home_hub.service import HomeHub


SERVICES = {
    "light": {"turn_on": "on", "turn_off": "off"},
    "switch": {"turn_on": "on", "turn_off": "off"},
    "fan": {"turn_on": "on", "turn_off": "off"},
    "input_boolean": {"turn_on": "on", "turn_off": "off"},
    "cover": {"open_cover": "open", "close_cover": "closed"},
    "climate": {"set_temperature": None},
}


class ActionService:
    _lock = threading.Lock()

    def __init__(self, hub: HomeHub, timeout: float = 20) -> None:
        self.hub = hub
        self.timeout = timeout

    def validate(self, payload: dict) -> dict:
        kind = payload.get("kind", "ha")
        if kind == "agent":
            from backend.agents.registry import get_agent_control
            agent_id = str(payload.get("agent_id") or "")
            action = str(payload.get("action") or "")
            control = get_agent_control(agent_id)
            if action not in {"enable", "disable", "start", "stop", "run"} or not control or action not in control.capabilities():
                raise ValueError("Agentenaktion nicht unterstuetzt.")
            return {"kind": "agent", "agent_id": agent_id, "action": action}
        if kind != "ha":
            raise ValueError("Unbekannter Aktionstyp.")
        entity_id = str(payload.get("entity_id") or "")
        domain = entity_id.partition(".")[0]
        service = str(payload.get("service") or "")
        if service not in SERVICES.get(domain, {}):
            raise ValueError("Diese Geraeteaktion ist nicht freigegeben.")
        state = next((item for item in self.hub.states() if item["entity_id"] == entity_id), None)
        if not state or state.get("state") in {"unavailable", "unknown"}:
            raise ValueError("Ziel fehlt oder ist nicht verfuegbar.")
        parameters = {}
        if service == "set_temperature":
            temperature = float(payload.get("temperature"))
            attrs = state.get("attributes", {})
            low, high = float(attrs.get("min_temp", 5)), float(attrs.get("max_temp", 35))
            if not math.isfinite(temperature) or not low <= temperature <= high:
                raise ValueError("Solltemperatur ausserhalb des erlaubten Bereichs.")
            parameters["temperature"] = temperature
        return {"kind": "ha", "entity_id": entity_id, "service": service, **parameters}

    def propose(self, principal: str, payload: dict, *, rule_id: str | None = None) -> dict:
        validated = self.validate(payload)
        if validated["kind"] == "ha":
            state = next(item for item in self.hub.states() if item["entity_id"] == validated["entity_id"])
            validated["expected_state"] = state.get("state")
            validated["expected_last_updated"] = state.get("last_updated")
        if rule_id:
            validated["authorization_rule"] = rule_id
        result = self.hub.store.propose(principal, validated)
        self.hub.store.event("action_proposed", result["id"], {"payload": validated})
        return result

    def confirm(self, principal: str, action_id: str) -> dict:
        if os.getenv("ROBOTERSTEVE_MONITOR_ONLY", "0") == "1":
            raise ValueError("Beobachtungsmodus: Aktionen sind deaktiviert.")
        # Serialize commands so two chat requests cannot race for the same actuator.
        with self._lock:
            action = self.hub.store.claim(action_id, principal)
            try:
                rule_id = action["payload"].get("authorization_rule")
                if rule_id:
                    rule = self.hub.store.rule(rule_id, principal)
                    trigger = rule["payload"]["trigger"]
                    trigger_state = self.hub.store.item("states", trigger["entity_id"])
                    if rule["mode"] != "active" or rule["hold_until"] > time.time() or not trigger_state or trigger_state.get("state") != trigger["to"]:
                        raise ValueError("Regelfreigabe oder Ausloesebedingung nicht mehr gueltig.")
                payload = self.validate(action["payload"])
                if payload["kind"] == "agent":
                    from backend.services.orchestrator_control_service import OrchestratorControlService
                    result = OrchestratorControlService().execute(payload["agent_id"], payload["action"])
                    status = "accepted" if result.get("ok") else "failed"
                else:
                    if not self.hub.healthy():
                        raise ValueError("HA-Verbindung nicht aktuell. Aktion wurde nicht gesendet.")
                    entity_id = payload["entity_id"]
                    before = self.hub.ha.get_state(entity_id)
                    if not before or before.get("state") in {"unknown", "unavailable"}:
                        raise ValueError("Ziel ist bei der Ausfuehrungspruefung nicht verfuegbar.")
                    expected = action["payload"]
                    if before.get("state") != expected.get("expected_state") or before.get("last_updated") != expected.get("expected_last_updated"):
                        raise ValueError("Ziel wurde seit dem Vorschlag veraendert. Bitte einen neuen Vorschlag anfordern.")
                    domain = entity_id.partition(".")[0]
                    service = payload["service"]
                    data = {"entity_id": entity_id}
                    if "temperature" in payload:
                        data["temperature"] = payload["temperature"]
                    try:
                        self.hub.begin_action(entity_id)
                        response = self.hub.ha.call_service(domain, service, data)
                    except Exception:
                        self.hub.end_action(entity_id, None)
                        self.hub.store.finish(action_id, "unknown", {"error": "Service-Antwort fehlt; nicht automatisch erneut ausfuehren."})
                        return self.hub.store.action(action_id, principal)
                    deadline = time.monotonic() + self.timeout
                    observed = None
                    verified = False
                    while time.monotonic() < deadline:
                        try:
                            observed = self.hub.ha.get_state(entity_id)
                        except Exception:
                            break
                        if observed:
                            if service == "set_temperature":
                                verified = observed.get("attributes", {}).get("temperature") == payload["temperature"]
                            else:
                                verified = observed.get("state") == SERVICES[domain][service]
                        if verified:
                            break
                        time.sleep(min(1, max(0, deadline - time.monotonic())))
                    status = "verified" if verified else "unverified"
                    self.hub.end_action(entity_id, observed)
                    result = {"before": before, "observed": observed, "service_accepted": response.get("ok", False)}
                self.hub.store.finish(action_id, status, result)
            except Exception as exc:
                self.hub.store.finish(action_id, "failed", {"error": str(exc) if isinstance(exc, ValueError) else type(exc).__name__})
            return self.hub.store.action(action_id, principal)

    def propose_rule(self, principal: str, trigger: dict, action: dict) -> dict:
        entity_id = str(trigger.get("entity_id") or "")
        value = str(trigger.get("to") or "")
        if not value or not any(item["entity_id"] == entity_id for item in self.hub.states()):
            raise ValueError("Trigger-Entity oder Zielzustand fehlt.")
        return self.hub.store.add_rule(principal, {"trigger": {"entity_id": entity_id, "to": value}, "action": self.validate(action)})

    def activate_rule(self, principal: str, rule_id: str) -> dict:
        if os.getenv("ROBOTERSTEVE_MONITOR_ONLY", "0") == "1" or not self.hub.healthy():
            raise ValueError("Aktivierung braucht eine Live-Verbindung ausserhalb des Beobachtungsmodus.")
        rule = self.hub.store.rule(rule_id, principal)
        payload = self.validate(rule["payload"]["action"])
        if payload["kind"] != "ha" or payload["entity_id"].partition(".")[0] not in {"light", "fan"}:
            raise ValueError("Automatische Freigabe ist auf Licht und Ventilator begrenzt. Andere Aktionen einzeln bestaetigen.")
        if payload["entity_id"] == rule["payload"]["trigger"]["entity_id"]:
            raise ValueError("Eine Regel darf sich nicht selbst ausloesen.")
        return self.hub.store.set_rule_mode(rule_id, principal, "active")

    def run_rule(self, rule_id: str, principal: str) -> dict:
        rule = self.hub.store.rule(rule_id, principal)
        if not self.hub.healthy() or not self.hub.store.claim_rule(rule_id, principal, cooldown=300):
            return {"status": "skipped"}
        proposal = self.propose(principal, rule["payload"]["action"], rule_id=rule_id)
        return self.confirm(principal, proposal["id"])
