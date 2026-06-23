import json
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from backend.config import load_agent_section
from backend.paths import AGENTS_DIR
from backend.services.messaging import MessagingService

from .store import SchedulerStore, utc_now


class SchedulerService:
    def __init__(self, store: SchedulerStore | None = None, messaging: MessagingService | None = None) -> None:
        self.store = store or SchedulerStore()
        self.messaging = messaging or MessagingService()
        self._running = False
        self._last_error: str | None = None
        self._last_run: str | None = None
        self.scheduler_stop = threading.Event()
        self.scheduler_thread: threading.Thread | None = None

    def config(self) -> dict[str, Any]:
        config = load_agent_section("scheduler")
        return {
            "enabled": bool(config.get("enabled", True)),
            "database_path": config.get("database_path", "data/scheduler/scheduler.db"),
            "poll_interval_seconds": int(config.get("poll_interval_seconds", 30) or 30),
            "default_tasks_enabled": bool(config.get("default_tasks_enabled", True)),
        }

    def status(self) -> dict[str, Any]:
        config = self.config()
        if self._last_error:
            current_status = "error"
        elif not config["enabled"]:
            current_status = "disabled"
        elif self._running:
            current_status = "running"
        else:
            current_status = "active"
        return {
            "enabled": config["enabled"],
            "is_running": self._running,
            "current_status": current_status,
            "status": current_status,
            "last_error": self._last_error,
            "last_successful_run": self._last_run,
            "next_scheduled_run": self.store.summary().get("next_run"),
            "scheduler_running": bool(self.scheduler_thread and self.scheduler_thread.is_alive()),
            "settings": config,
            "summary": self.store.summary(),
        }

    def start_scheduler(self) -> dict[str, Any]:
        if self.scheduler_thread and self.scheduler_thread.is_alive():
            return self.status()
        self.scheduler_stop.clear()
        self.scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self.scheduler_thread.start()
        return self.status()

    def stop_scheduler(self) -> dict[str, Any]:
        self.scheduler_stop.set()
        return self.status()

    def enable(self) -> dict[str, Any]:
        self._write_config(enabled=True)
        self._last_error = None
        return self.status()

    def disable(self) -> dict[str, Any]:
        self._write_config(enabled=False)
        return self.status()

    def toggle(self) -> dict[str, Any]:
        return self.disable() if self.config()["enabled"] else self.enable()

    def run(self) -> dict[str, Any]:
        if not self.config()["enabled"]:
            return {"status": "disabled", "current_status": "disabled", "message": "Scheduler ist deaktiviert.", "executed": 0}
        return self.run_due_tasks()

    def run_due_tasks(self) -> dict[str, Any]:
        if self._running:
            return {"status": "running", "current_status": "running", "message": "Scheduler laeuft bereits.", "executed": 0}
        self._running = True
        self._last_error = None
        executed: list[dict[str, Any]] = []
        try:
            for task in self.store.due_tasks():
                executed.append(self.execute_task(task))
            self._last_run = utc_now()
            return {"status": "active", "current_status": "active", "executed": len(executed), "runs": executed}
        except Exception as exc:
            self._last_error = str(exc)
            return {"status": "error", "current_status": "error", "message": str(exc), "executed": len(executed), "runs": executed}
        finally:
            self._running = False

    def execute_task_by_id(self, task_id: int) -> dict[str, Any]:
        task = self.store.get_task(task_id)
        if not task:
            raise KeyError(f"Scheduler Task {task_id} nicht gefunden.")
        return self.execute_task(task)

    def execute_task(self, task: dict[str, Any]) -> dict[str, Any]:
        started_at = utc_now()
        try:
            skip_reason = self._target_agent_skip_reason(task)
            if skip_reason:
                message = f"Task {task.get('name')} uebersprungen: {skip_reason}."
                run = self.store.record_run(task, "skipped", message, started_at, utc_now(), {"reason": skip_reason})
                updated_task = self.store.mark_task_run(task, "skipped")
                return {**run, "task": updated_task}
            result = self._execute_action(task)
            message = f"Task {task.get('name')} erfolgreich ausgefuehrt."
            run = self.store.record_run(task, "completed", message, started_at, utc_now(), {"result": result})
            updated_task = self.store.mark_task_run(task, "completed")
            if self._should_notify_success(updated_task):
                self._notify_success(updated_task)
            return {**run, "task": updated_task}
        except Exception as exc:
            error = str(exc)
            run = self.store.record_run(task, "error", error, started_at, utc_now(), {"error": error})
            updated_task = self.store.mark_task_run(task, "error", error=error)
            self._notify_failure(updated_task, error)
            return {**run, "task": updated_task}

    def create_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.store.create_task(payload)

    def update_task(self, task_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return self.store.update_task(task_id, payload)

    def enable_task(self, task_id: int) -> dict[str, Any]:
        task = self.store.set_task_enabled(task_id, True)
        self.messaging.create_message(
            source="scheduler",
            category="orchestrator",
            severity="info",
            title="Scheduler Task aktiviert",
            message=f"{task['name']} ist aktiviert.",
            payload={"task_id": task_id},
        )
        return task

    def disable_task(self, task_id: int) -> dict[str, Any]:
        task = self.store.set_task_enabled(task_id, False)
        self.messaging.create_message(
            source="scheduler",
            category="orchestrator",
            severity="info",
            title="Scheduler Task deaktiviert",
            message=f"{task['name']} ist deaktiviert.",
            payload={"task_id": task_id},
        )
        return task

    def summary(self) -> dict[str, Any]:
        return self.store.summary()

    def tasks(self, status: str | None = None) -> list[dict[str, Any]]:
        return self.store.list_tasks(status=status)

    def runs(self, limit: int = 100) -> list[dict[str, Any]]:
        return self.store.runs(limit=limit)

    def _scheduler_loop(self) -> None:
        while not self.scheduler_stop.is_set():
            if self.config()["enabled"]:
                self.run_due_tasks()
            self.scheduler_stop.wait(max(10, self.config()["poll_interval_seconds"]))

    def _execute_action(self, task: dict[str, Any]) -> Any:
        action_type = str(task.get("action_type") or "execute_action")
        if action_type == "start_agent":
            return self._agent_control(str(task.get("target_agent") or ""), "start", task.get("action_payload") or {})
        if action_type == "stop_agent":
            return self._agent_control(str(task.get("target_agent") or ""), "stop", task.get("action_payload") or {})
        if action_type == "execute_action":
            action = str(task.get("target_action") or "run")
            if action == "analyze":
                action = "run"
            return self._agent_control(str(task.get("target_agent") or ""), action, task.get("action_payload") or {})
        if action_type == "create_message":
            payload = task.get("action_payload") or {}
            return self.messaging.create_message(
                source=str(payload.get("source") or "scheduler"),
                category=str(payload.get("category") or "orchestrator"),
                severity=str(payload.get("severity") or "info"),
                title=str(payload.get("title") or task.get("name") or "Scheduler Nachricht"),
                message=str(payload.get("message") or task.get("description") or ""),
                payload={"task_id": task.get("id"), **payload},
            )
        if action_type == "infrastructure_check":
            from backend.services.infrastructure_service import InfrastructureService

            return InfrastructureService().check()
        if action_type == "household_check":
            from backend.services.household_service import HouseholdService

            return HouseholdService().summary()
        if action_type == "update_check":
            from backend.services.update_service import UpdateService

            return UpdateService().check_for_updates(notify=True)
        if action_type in {"call_webhook", "http_request"}:
            return self._http_request(task.get("action_payload") or {})
        raise ValueError(f"Unbekannter Scheduler Action-Typ: {action_type}")

    def _agent_control(self, agent_id: str, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        from backend.agents.registry import get_agent_control

        control = get_agent_control(agent_id)
        if not control:
            raise ValueError(f"Agent {agent_id} unterstuetzt keinen Control-Vertrag.")
        if action not in control.capabilities():
            raise ValueError(f"Agent {agent_id} unterstuetzt Aktion {action} nicht.")
        if action == "run" and self._agent_is_disabled(agent_id):
            raise RuntimeError(f"Agent {agent_id} ist deaktiviert. Scheduler startet keinen Run.")
        result = control.execute(action, payload)
        if not result.get("ok", False):
            raise RuntimeError(str(result.get("message") or f"Agent {agent_id} Aktion {action} fehlgeschlagen."))
        return dict(result)

    def _target_agent_skip_reason(self, task: dict[str, Any]) -> str:
        action_type = str(task.get("action_type") or "")
        target_agent = str(task.get("target_agent") or "").strip()
        if not target_agent or action_type not in {"execute_action", "start_agent"}:
            return ""
        target_action = str(task.get("target_action") or "run")
        control_action = "run" if action_type == "execute_action" and target_action in {"run", "analyze"} else target_action
        if control_action not in {"run", "start"}:
            return ""
        from backend.agents.registry import get_agent_control

        control = get_agent_control(target_agent)
        if not control:
            return "Ziel-Agent ist in diesem Produkt nicht verfuegbar"
        if "status" in control.capabilities() and self._agent_is_disabled(target_agent):
            return "Ziel-Agent ist deaktiviert"
        return ""

    def _agent_is_disabled(self, agent_id: str) -> bool:
        from backend.agents.registry import get_agent_control

        control = get_agent_control(agent_id)
        if not control or "status" not in control.capabilities():
            return False
        status = control.execute("status", {})
        data = status.get("data") if isinstance(status.get("data"), dict) else {}
        enabled = data.get("enabled")
        current_status = str(data.get("current_status") or data.get("status") or status.get("status") or "").lower()
        return enabled is False or current_status in {"disabled", "stopped"}

    def _http_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = str(payload.get("url") or "").strip()
        if not url:
            raise ValueError("HTTP Task benoetigt eine URL.")
        method = str(payload.get("method") or "POST").upper()
        body = payload.get("body")
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(url, data=data, method=method)
        for key, value in (payload.get("headers") or {}).items():
            request.add_header(str(key), str(value))
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                text = response.read().decode("utf-8", errors="replace")
                return {"status": response.status, "body": text[:2000]}
        except urllib.error.URLError as exc:
            raise RuntimeError(str(exc)) from exc

    def _notify_success(self, task: dict[str, Any]) -> None:
        self.messaging.create_message(
            source="scheduler",
            category="orchestrator",
            severity="info",
            title="Scheduler Task ausgefuehrt",
            message=f"{task['name']} wurde erfolgreich ausgefuehrt.",
            payload={"task_id": task["id"], "target_agent": task.get("target_agent")},
        )

    def _should_notify_success(self, task: dict[str, Any]) -> bool:
        if str(task.get("source") or "") == "platform" and str(task.get("action_type") or "") in {
            "infrastructure_check",
            "household_check",
            "update_check",
        }:
            return False
        return True

    def _notify_failure(self, task: dict[str, Any], error: str) -> None:
        repeated = int(task.get("failure_count") or 0) >= 3
        self.messaging.create_message(
            source="scheduler",
            category="orchestrator",
            severity="critical" if repeated else "warning",
            title="Scheduler Task fehlgeschlagen",
            message=f"{task['name']} konnte nicht ausgefuehrt werden.",
            payload={"task_id": task["id"], "error": error, "failure_count": task.get("failure_count")},
        )

    def _write_config(self, **updates: Any) -> None:
        path = AGENTS_DIR / "scheduler" / "config.yaml"
        try:
            data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            data = {}
        section = data.get("scheduler") if isinstance(data.get("scheduler"), dict) else {}
        section.update(updates)
        data["scheduler"] = section
        Path(path).write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
