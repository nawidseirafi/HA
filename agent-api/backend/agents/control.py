from typing import Any, Literal, Protocol, TypedDict, runtime_checkable

from pydantic import BaseModel, Field


AgentControlCapability = Literal["status", "start", "stop", "enable", "disable", "toggle", "run"]
CONTROL_ACTIONS: tuple[AgentControlCapability, ...] = ("status", "start", "stop", "enable", "disable", "toggle", "run")


class AgentControlResult(TypedDict, total=False):
    agent_id: str
    action: AgentControlCapability
    ok: bool
    status: str
    message: str
    data: dict[str, Any]


class AgentControlResponse(BaseModel):
    agent_id: str
    action: AgentControlCapability
    ok: bool
    status: str = "unknown"
    message: str = ""
    data: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class BaseAgentControl(Protocol):
    agent_id: str

    def capabilities(self) -> list[AgentControlCapability]:
        ...

    def execute(self, action: AgentControlCapability, payload: dict[str, Any] | None = None) -> AgentControlResult:
        ...


class AgentControlAdapter:
    def __init__(self, agent_id: str, service: Any) -> None:
        self.agent_id = agent_id
        self.service = service

    def capabilities(self) -> list[AgentControlCapability]:
        actions: list[AgentControlCapability] = []
        if callable(getattr(self.service, "status", None)):
            actions.append("status")
        if callable(getattr(self.service, "start", None)) or callable(getattr(self.service, "start_scheduler", None)):
            actions.append("start")
        if callable(getattr(self.service, "stop", None)) or callable(getattr(self.service, "stop_scheduler", None)):
            actions.append("stop")
        for action in ("enable", "disable", "toggle"):
            if callable(getattr(self.service, action, None)):
                actions.append(action)  # type: ignore[arg-type]
        if any(callable(getattr(self.service, name, None)) for name in ("run", "run_agent", "run_action")):
            actions.append("run")
        return actions

    def execute(self, action: AgentControlCapability, payload: dict[str, Any] | None = None) -> AgentControlResult:
        payload = payload or {}
        if action not in self.capabilities():
            return self._result(action, False, "unsupported", f"Aktion {action} wird nicht unterstuetzt.", {})

        raw = self._execute_supported(action, payload)
        data = raw if isinstance(raw, dict) else {"result": raw} if raw is not None else {}
        status = self._status_from_data(data)
        ok = status not in {"error", "failed", "unsupported"}
        return self._result(action, ok, status, self._message(action, ok, data), data)

    def _execute_supported(self, action: AgentControlCapability, payload: dict[str, Any]) -> Any:
        if action == "status":
            return self.service.status()
        if action == "start":
            start = getattr(self.service, "start", None)
            if callable(start):
                return self._call_with_payload(start, payload)
            self.service.start_scheduler()
            return self._status_or_empty()
        if action == "stop":
            stop = getattr(self.service, "stop", None)
            if callable(stop):
                return self._call_with_payload(stop, payload)
            self.service.stop_scheduler()
            return self._status_or_empty()
        if action in {"enable", "disable", "toggle"}:
            return getattr(self.service, action)()
        if action == "run":
            run = getattr(self.service, "run", None)
            if callable(run):
                return self._call_with_payload(run, payload)
            run_agent = getattr(self.service, "run_agent", None)
            if callable(run_agent):
                return self._call_with_payload(run_agent, payload)
            run_action = getattr(self.service, "run_action", None)
            action_type = str(payload.get("action") or payload.get("mode") or "prepare")
            dry_run = bool(payload.get("dry_run", False))
            return run_action(action_type, dry_run=dry_run)
        return {}

    def _call_with_payload(self, method: Any, payload: dict[str, Any]) -> Any:
        if not payload:
            return method()
        try:
            return method(**payload)
        except TypeError:
            if "mode" in payload:
                return method(mode=payload["mode"])
            if "dry_run" in payload:
                return method(dry_run=bool(payload["dry_run"]))
            return method()

    def _status_or_empty(self) -> dict[str, Any]:
        status = getattr(self.service, "status", None)
        return status() if callable(status) else {}

    def _status_from_data(self, data: dict[str, Any]) -> str:
        if data.get("is_running") is True:
            return "running"

        for raw in self._status_candidates(data):
            status = self._normalize_status(raw)
            if status:
                return status
        return "active"

    def _status_candidates(self, data: dict[str, Any]) -> list[Any]:
        candidates: list[Any] = []

        # A run result is authoritative for the just executed action. Some
        # agents additionally return a full status snapshot that may contain
        # stale last_error values from previous runs.
        result = data.get("result")
        if isinstance(result, dict):
            candidates.extend((result.get("status"), result.get("current_status"), result.get("last_status")))
            if "ok" in result:
                candidates.append(result.get("ok"))

        status = data.get("status")
        candidates.extend((data.get("current_status"), data.get("last_status")))
        if isinstance(status, dict):
            candidates.extend((status.get("status"), status.get("current_status"), status.get("last_status")))
            if status.get("is_running") is True:
                candidates.append("running")
        else:
            candidates.append(status)

        nested = data.get("data") if isinstance(data.get("data"), dict) else {}
        if nested:
            nested_status = nested.get("status")
            candidates.extend((nested.get("current_status"), nested.get("last_status")))
            if isinstance(nested_status, dict):
                candidates.extend(
                    (
                        nested_status.get("status"),
                        nested_status.get("current_status"),
                        nested_status.get("last_status"),
                    )
                )
            else:
                candidates.append(nested_status)
        return candidates

    def _normalize_status(self, raw: Any) -> str:
        if raw is None:
            return ""
        if isinstance(raw, bool):
            return "active" if raw else "error"
        text = str(raw or "").strip().lower()
        if not text:
            return ""
        if text in {"unsupported"}:
            return "unsupported"
        if "error" in text or "failed" in text:
            return "error"
        if "running" in text:
            return "running"
        if "disabled" in text or "stopped" in text:
            return "disabled"
        if "pause" in text:
            return "paused"
        if text in {"ok", "completed", "success", "succeeded", "enabled", "active", "idle", "ready", "configured"}:
            return "active"
        return text

    def _message(self, action: AgentControlCapability, ok: bool, data: dict[str, Any]) -> str:
        if isinstance(data.get("message"), str):
            return str(data["message"])
        result = data.get("result")
        if isinstance(result, dict) and isinstance(result.get("message"), str):
            return str(result["message"])
        if ok:
            return f"Agent {action} ausgefuehrt."
        return f"Agent {action} fehlgeschlagen."

    def _result(
        self,
        action: AgentControlCapability,
        ok: bool,
        status: str,
        message: str,
        data: dict[str, Any],
    ) -> AgentControlResult:
        return {
            "agent_id": self.agent_id,
            "action": action,
            "ok": ok,
            "status": status,
            "message": message,
            "data": data,
        }
