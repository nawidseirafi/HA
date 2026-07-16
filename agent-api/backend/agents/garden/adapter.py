from __future__ import annotations

from typing import Any

from backend.services.homeassistant_service import HomeAssistantService


class GardenIrrigationAdapter:
    def __init__(self, ha_service: HomeAssistantService | None = None) -> None:
        self.ha_service = ha_service or HomeAssistantService()

    def start(self, entity_id: str) -> dict[str, Any]:
        domain, service = self._service(entity_id, start=True)
        return {
            "domain": domain,
            "service": service,
            "entity_id": entity_id,
            "result": self.ha_service.call_service(domain, service, {"entity_id": entity_id}),
        }

    def stop(self, entity_id: str) -> dict[str, Any]:
        domain, service = self._service(entity_id, start=False)
        return {
            "domain": domain,
            "service": service,
            "entity_id": entity_id,
            "result": self.ha_service.call_service(domain, service, {"entity_id": entity_id}),
        }

    def _service(self, entity_id: str, start: bool) -> tuple[str, str]:
        domain = str(entity_id or "").split(".", 1)[0]
        if domain == "switch":
            return domain, "turn_on" if start else "turn_off"
        if domain == "input_boolean":
            return domain, "turn_on" if start else "turn_off"
        if domain == "valve":
            return domain, "open_valve" if start else "close_valve"
        raise ValueError(f"Nicht unterstützte Bewässerungs-Domain: {domain}")
