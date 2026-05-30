from typing import Any

from .service import MyWellnessService


class MyWellnessAgent:
    def __init__(self, service: MyWellnessService | None = None) -> None:
        self.service = service or MyWellnessService()

    def prepare(self, dry_run: bool = False) -> dict[str, Any]:
        return self.service.run_action("prepare", dry_run=dry_run)

    def book(self, dry_run: bool = False) -> dict[str, Any]:
        return self.service.run_action("book", dry_run=dry_run)

    def status(self) -> dict[str, Any]:
        return self.service.status()
