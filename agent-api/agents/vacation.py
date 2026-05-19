import logging
from typing import Any, Optional


logger = logging.getLogger("agent-api.vacation")


class VacationAgent:
    def __init__(self, config: Optional[dict[str, Any]] = None):
        self.config = config or {}

    def run(self) -> dict[str, Any]:
        logger.info("VacationAgent triggered.")
        return {
            "triggered": True,
            "message": "VacationAgent.run() wurde ausgelöst. Noch keine Vacation-Logik implementiert.",
        }
